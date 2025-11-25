"""
FastAPI Sanctions Screening API Server

Provides REST API endpoints for sanctions screening functionality.
Wraps the existing Python screening engine for Electron frontend integration.

Usage:
    uvicorn api.server:app --reload --port 8000
"""

import os
import sys
import time
import uuid
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.models import (
    ScreeningRequest,
    ScreeningResponse,
    MatchDetail,
    ConfidenceBreakdownResponse,
    EntityDetail,
    BulkScreeningResponse,
    BulkScreeningItem,
    HealthResponse,
    DataFileInfo,
    DataUpdateResponse,
    ErrorResponse
)
from api.middleware import (
    setup_cors,
    setup_exception_handlers,
    RequestLoggingMiddleware
)
from screener import (
    EnhancedSanctionsScreener,
    InputValidationError
)
from config_manager import get_config, ConfigManager, ConfigurationError
from downloader import EnhancedSanctionsDownloader

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables with defaults
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
DATA_DIR = os.getenv("DATA_DIR", "sanctions_data")
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
CONFIG_PATH = os.getenv("CONFIG_PATH", "config.yaml")

# Global state
_screener: Optional[EnhancedSanctionsScreener] = None
_config: Optional[ConfigManager] = None
_startup_time: Optional[datetime] = None


def get_screener() -> EnhancedSanctionsScreener:
    """Dependency to get the screener instance."""
    global _screener
    if _screener is None:
        raise HTTPException(
            status_code=503,
            detail="Screener not initialized. Service is starting up."
        )
    return _screener


def get_config_instance() -> ConfigManager:
    """Dependency to get the config instance."""
    global _config
    if _config is None:
        _config = get_config(CONFIG_PATH)
    return _config


# Create FastAPI application
app = FastAPI(
    title="Sanctions Screening API",
    description="API for screening individuals against OFAC and UN sanctions lists",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# Setup middleware
setup_cors(app)
app.add_middleware(RequestLoggingMiddleware)
setup_exception_handlers(app)


@app.on_event("startup")
async def startup():
    """Initialize screener and load sanctions data on startup."""
    global _screener, _config, _startup_time
    
    logger.info("🚀 Starting Sanctions Screening API...")
    start_time = time.time()
    
    try:
        # Load configuration
        _config = get_config(CONFIG_PATH)
        logger.info(f"✓ Configuration loaded from {CONFIG_PATH}")
        
        # Initialize screener
        _screener = EnhancedSanctionsScreener(config=_config, data_dir=DATA_DIR)
        
        # Load OFAC data
        ofac_count = _screener.load_ofac()
        logger.info(f"✓ Loaded {ofac_count} OFAC entities")
        
        # Load UN data
        un_count = _screener.load_un()
        logger.info(f"✓ Loaded {un_count} UN entities")
        
        total_entities = len(_screener.entities)
        elapsed = time.time() - start_time
        
        _startup_time = datetime.now(timezone.utc)
        
        logger.info(
            "✓ API ready: %d entities loaded in %.2f seconds",
            total_entities,
            elapsed
        )
        
    except ConfigurationError as e:
        logger.error(f"✗ Configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"✗ Startup error: {e}")
        raise


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    logger.info("Shutting down Sanctions Screening API...")


def _transform_match_to_response(match_dict: dict) -> MatchDetail:
    """Transform screener match dict to API response model."""
    entity_data = match_dict.get('entity', {})
    confidence_data = match_dict.get('confidence', {})
    
    # Build EntityDetail
    entity = EntityDetail(
        id=entity_data.get('id', ''),
        source=entity_data.get('source', ''),
        type=entity_data.get('type', 'unknown'),
        name=entity_data.get('name', ''),
        all_names=entity_data.get('all_names', []),
        aliases=entity_data.get('aliases', []),
        firstName=entity_data.get('firstName'),
        lastName=entity_data.get('lastName'),
        countries=entity_data.get('countries', []),
        identity_documents=entity_data.get('identity_documents', []),
        program=entity_data.get('program'),
        dateOfBirth=entity_data.get('dateOfBirth'),
        nationality=entity_data.get('nationality')
    )
    
    # Build ConfidenceBreakdownResponse
    confidence = ConfidenceBreakdownResponse(
        overall=confidence_data.get('overall', 0.0),
        name=confidence_data.get('name', 0.0),
        document=confidence_data.get('document', 0.0),
        dob=confidence_data.get('dob', 0.0),
        nationality=confidence_data.get('nationality', 0.0),
        address=confidence_data.get('address', 0.0)
    )
    
    return MatchDetail(
        entity=entity,
        confidence=confidence,
        flags=match_dict.get('flags', []),
        recommendation=match_dict.get('recommendation', 'MANUAL_REVIEW'),
        match_layer=match_dict.get('match_layer', 4),
        matched_name=match_dict.get('matched_name', ''),
        matched_document=match_dict.get('matched_document')
    )


@app.post(
    "/api/v1/screen",
    response_model=ScreeningResponse,
    responses={
        200: {"model": ScreeningResponse, "description": "Screening completed successfully"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Screen an individual",
    description="Screen an individual against OFAC and UN sanctions lists"
)
async def screen_individual(
    request: ScreeningRequest,
    screener: EnhancedSanctionsScreener = Depends(get_screener)
):
    """Screen an individual against sanctions lists.
    
    This endpoint validates input, calls the screener, and returns matches.
    """
    start_time = time.time()
    
    try:
        # Call screener
        result = screener.screen_individual(
            name=request.name,
            document=request.document_number,
            document_type=request.document_type,
            date_of_birth=request.date_of_birth,
            nationality=request.nationality,
            country=request.country,
            analyst=request.analyst,
            generate_report=False  # Don't generate files for API calls
        )
        
        # Transform matches to response format
        matches = [
            _transform_match_to_response(m) 
            for m in result.get('matches', [])
        ]
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        return ScreeningResponse(
            screening_id=result.get('screening_id', str(uuid.uuid4())),
            screening_date=result.get('screening_date', datetime.now(timezone.utc).isoformat()),
            is_hit=result.get('is_hit', False),
            hit_count=result.get('hit_count', 0),
            matches=matches,
            processing_time_ms=processing_time_ms,
            algorithm_version=result.get('algorithm_version', '2.0.0')
        )
        
    except InputValidationError:
        # Re-raise to be handled by exception handler
        raise
    except Exception as e:
        logger.error(f"Screening error: {e}")
        raise HTTPException(status_code=500, detail="Screening failed")


@app.post(
    "/api/v1/screen/bulk",
    response_model=BulkScreeningResponse,
    responses={
        200: {"model": BulkScreeningResponse, "description": "Bulk screening completed"},
        400: {"model": ErrorResponse, "description": "Invalid CSV format"},
        413: {"model": ErrorResponse, "description": "File too large"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Bulk screen from CSV",
    description="Upload a CSV file for bulk screening. Required headers: nombre, cedula, pais"
)
async def bulk_screen(
    file: UploadFile = File(..., description="CSV file with columns: nombre, cedula, pais"),
    screener: EnhancedSanctionsScreener = Depends(get_screener)
):
    """Bulk screen individuals from a CSV file.
    
    The CSV must have headers: nombre (name), cedula (document), pais (country).
    """
    start_time = time.time()
    screening_id = str(uuid.uuid4())
    
    # Validate file size
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    
    if size_mb > MAX_UPLOAD_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE_MB}MB"
        )
    
    # Validate content type
    if file.content_type and 'csv' not in file.content_type.lower():
        # Allow text/plain and application/octet-stream as well
        if file.content_type not in ['text/plain', 'application/octet-stream']:
            raise HTTPException(
                status_code=400,
                detail="File must be a CSV"
            )
    
    temp_path = None
    try:
        # Save to temp file
        temp_dir = Path(tempfile.gettempdir()) / "sanctions_bulk"
        temp_dir.mkdir(exist_ok=True)
        temp_path = temp_dir / f"{screening_id}.csv"
        
        with open(temp_path, 'wb') as f:
            f.write(content)
        
        # Validate CSV headers
        import csv
        with open(temp_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
            except StopIteration:
                raise HTTPException(status_code=400, detail="CSV file is empty")
            
            headers_lower = [h.lower().strip() for h in headers]
            
            if 'nombre' not in headers_lower:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required header: 'nombre'. Found: {headers}"
                )
        
        # Call bulk screen
        summary = screener.bulk_screen(
            csv_file=str(temp_path),
            analyst=None,
            generate_individual_reports=False
        )
        
        # Transform results
        results = []
        for r in summary.get('results', []):
            matches = [
                _transform_match_to_response(m)
                for m in r.get('matches', [])
            ]
            results.append(BulkScreeningItem(
                screening_id=r.get('screening_id', ''),
                input=r.get('input', {}),
                is_hit=r.get('is_hit', False),
                hit_count=r.get('hit_count', 0),
                matches=matches
            ))
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        screening_info = summary.get('screening_info', {})
        
        return BulkScreeningResponse(
            screening_id=screening_id,
            total_processed=screening_info.get('total_screened', len(results)),
            hits=screening_info.get('total_hits', 0),
            hit_rate=screening_info.get('hit_rate', '0%'),
            results=results,
            processing_time_ms=processing_time_ms
        )
        
    finally:
        # Cleanup temp file
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file: {e}")


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check service health and data status"
)
async def health_check(
    screener: EnhancedSanctionsScreener = Depends(get_screener),
    config: ConfigManager = Depends(get_config_instance)
):
    """Return health status including entity counts and data freshness."""
    global _startup_time
    
    # Get entity count
    entities_loaded = len(screener.entities)
    
    # Get data file info
    data_dir = Path(DATA_DIR)
    data_files = []
    oldest_file_time = None
    
    for pattern in ["*.xml", "*.zip"]:
        for f in data_dir.glob(pattern):
            try:
                stat = f.stat()
                modified_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                data_files.append(DataFileInfo(
                    filename=f.name,
                    last_modified=modified_time.isoformat(),
                    size_bytes=stat.st_size
                ))
                
                if oldest_file_time is None or modified_time < oldest_file_time:
                    oldest_file_time = modified_time
            except Exception:
                pass
    
    # Calculate data age
    data_age_days = None
    if oldest_file_time:
        age = datetime.now(timezone.utc) - oldest_file_time
        data_age_days = age.days
    
    # Calculate memory usage
    memory_usage_mb = None
    try:
        import psutil
        process = psutil.Process()
        memory_usage_mb = round(process.memory_info().rss / (1024 * 1024), 2)
    except ImportError:
        pass
    except Exception:
        pass
    
    # Calculate uptime
    uptime_seconds = None
    if _startup_time:
        uptime = datetime.now(timezone.utc) - _startup_time
        uptime_seconds = int(uptime.total_seconds())
    
    return HealthResponse(
        status="healthy",
        entities_loaded=entities_loaded,
        data_files=data_files,
        data_age_days=data_age_days,
        algorithm_version=config.algorithm.version,
        memory_usage_mb=memory_usage_mb,
        uptime_seconds=uptime_seconds
    )


@app.post(
    "/api/v1/data/update",
    response_model=DataUpdateResponse,
    responses={
        200: {"model": DataUpdateResponse, "description": "Data updated successfully"},
        500: {"model": ErrorResponse, "description": "Update failed"}
    },
    summary="Update sanctions data",
    description="Download and reload OFAC and UN sanctions data"
)
async def update_data(
    config: ConfigManager = Depends(get_config_instance)
):
    """Download fresh sanctions data and reload the screener."""
    global _screener
    
    start_time = time.time()
    
    try:
        # Create downloader
        downloader = EnhancedSanctionsDownloader(config=config)
        
        # Download and parse all data
        entities, validation = downloader.download_and_parse_all()
        
        # Count by source
        ofac_count = len([e for e in entities if e.source == 'OFAC'])
        un_count = len([e for e in entities if e.source == 'UN'])
        
        # Reinitialize screener with new data
        _screener = EnhancedSanctionsScreener(config=config, data_dir=DATA_DIR)
        _screener.load_ofac()
        _screener.load_un()
        
        total_entities = len(_screener.entities)
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        return DataUpdateResponse(
            success=validation.is_valid,
            ofac_entities=ofac_count,
            un_entities=un_count,
            total_entities=total_entities,
            validation_errors=validation.errors,
            validation_warnings=validation.warnings,
            processing_time_ms=processing_time_ms
        )
        
    except Exception as e:
        logger.error(f"Data update failed: {e}")
        raise HTTPException(status_code=500, detail="Data update failed")


# Root redirect to docs
@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to API documentation."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/api/docs")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
