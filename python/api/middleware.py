"""
FastAPI Middleware for Sanctions Screening API

Provides CORS configuration, request logging, and global error handling.
"""

import os
import re
import time
import logging
from datetime import datetime, timezone
from typing import Callable, List

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from xml_utils import sanitize_for_logging

logger = logging.getLogger(__name__)

# Default allowed origins for localhost development
DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",   # Common Electron dev port
    "http://localhost:5173",   # Vite dev port
    "http://localhost:8080",   # Common dev port
    "http://localhost:8000",   # FastAPI default port
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8000",
]

# Railway subdomain pattern for wildcard matching
RAILWAY_PATTERN = re.compile(r'^https://[\w-]+\.up\.railway\.app$')


def is_origin_allowed(origin: str, allowed_origins: List[str]) -> bool:
    """Check if origin is allowed, supporting wildcards for Railway domains.
    
    Args:
        origin: The origin to check
        allowed_origins: List of allowed origins (may include wildcards like *.railway.app)
    
    Returns:
        True if origin is allowed
    """
    for allowed in allowed_origins:
        # Exact match
        if origin == allowed:
            return True
        # Wildcard match for Railway subdomains
        if '*.up.railway.app' in allowed or '*.railway.app' in allowed:
            if RAILWAY_PATTERN.match(origin):
                return True
    return False


def setup_cors(app: FastAPI) -> None:
    """Configure CORS middleware for the application.
    
    Restricts origins to localhost for security.
    Origins can be customized via CORS_ORIGINS environment variable
    (comma-separated list of allowed origins).
    Supports wildcard patterns for Railway subdomains (*.up.railway.app).
    """
    # Allow customization via environment variable
    cors_origins_env = os.getenv("CORS_ORIGINS", "")
    if cors_origins_env:
        allowed_origins = [origin.strip() for origin in cors_origins_env.split(",")]
    else:
        allowed_origins = DEFAULT_CORS_ORIGINS
    
    # Check if any wildcard patterns are present
    has_wildcard = any('*' in origin for origin in allowed_origins)
    
    if has_wildcard:
        # For wildcard support, we need to use allow_origin_regex or a custom validator
        # Create regex pattern for Railway domains
        regex_patterns = []
        exact_origins = []
        
        for origin in allowed_origins:
            if '*.up.railway.app' in origin:
                # Convert wildcard to regex pattern for Railway subdomains
                regex_patterns.append(r'https://[\w-]+\.up\.railway\.app')
            elif '*.railway.app' in origin:
                regex_patterns.append(r'https://[\w-]+\.railway\.app')
            else:
                exact_origins.append(origin)
        
        # Combine patterns
        if regex_patterns:
            combined_regex = '|'.join(f'({p})' for p in regex_patterns)
            if exact_origins:
                exact_escaped = '|'.join(re.escape(o) for o in exact_origins)
                combined_regex = f'({combined_regex})|({exact_escaped})'
            
            app.add_middleware(
                CORSMiddleware,
                allow_origin_regex=combined_regex,
                allow_credentials=True,
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["*"],
                expose_headers=["X-Request-ID", "X-Processing-Time-MS"],
            )
        else:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=exact_origins,
                allow_credentials=True,
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["*"],
                expose_headers=["X-Request-ID", "X-Processing-Time-MS"],
            )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "X-Processing-Time-MS"],
        )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging all requests with sanitized inputs.
    
    Follows security patterns from security_logger.py.
    """
    
    async def dispatch(self, request: Request, call_next: Callable):
        """Process request and log details."""
        start_time = time.time()
        request_id = request.headers.get("X-Request-ID", str(time.time_ns()))
        
        # Store request ID for later use
        request.state.request_id = request_id
        request.state.start_time = start_time
        
        # Log incoming request (sanitize path to prevent log injection)
        sanitized_path = sanitize_for_logging(str(request.url.path))
        logger.info(
            "Request: method=%s path=%s request_id=%s",
            request.method,
            sanitized_path,
            request_id
        )
        
        try:
            response = await call_next(request)
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Add custom headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Processing-Time-MS"] = str(processing_time_ms)
            
            # Log response
            logger.info(
                "Response: status=%d processing_time_ms=%d request_id=%s",
                response.status_code,
                processing_time_ms,
                request_id
            )
            
            return response
            
        except Exception as exc:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Request failed: error=%s processing_time_ms=%d request_id=%s",
                sanitize_for_logging(str(exc)),
                processing_time_ms,
                request_id
            )
            raise


def create_error_response(
    code: str,
    message: str,
    status_code: int = 500,
    field: str = None,
    suggestion: str = None
) -> JSONResponse:
    """Create a standardized error response.
    
    Args:
        code: Error code for programmatic handling
        message: Human-readable message
        status_code: HTTP status code
        field: Field that caused the error (optional)
        suggestion: How to fix the error (optional)
    
    Returns:
        JSONResponse with standardized error format
    """
    error_detail = {
        "code": code,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    if field:
        error_detail["field"] = field
    if suggestion:
        error_detail["suggestion"] = suggestion
    
    return JSONResponse(
        status_code=status_code,
        content={"error": error_detail}
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler for unhandled errors.
    
    Sanitizes error messages to prevent information leakage.
    
    Args:
        request: FastAPI request object
        exc: Exception that was raised
    
    Returns:
        Standardized error response
    """
    # Import here to avoid circular imports
    from screener import InputValidationError
    from config_manager import ConfigurationError
    
    # Get request ID for correlation
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    # Log the full error for debugging
    logger.error(
        "Unhandled exception: type=%s message=%s request_id=%s",
        type(exc).__name__,
        sanitize_for_logging(str(exc)),
        request_id
    )
    
    # Handle specific exception types
    if isinstance(exc, InputValidationError):
        return create_error_response(
            code=exc.code,
            message=str(exc),
            status_code=422,
            field=exc.field,
            suggestion=exc.suggestion
        )
    
    if isinstance(exc, ConfigurationError):
        return create_error_response(
            code="CONFIGURATION_ERROR",
            message="Service configuration is invalid. Please contact administrator.",
            status_code=503
        )
    
    if isinstance(exc, HTTPException):
        return create_error_response(
            code=f"HTTP_{exc.status_code}",
            message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            status_code=exc.status_code
        )
    
    # Generic error - sanitize message to prevent info leakage
    return create_error_response(
        code="INTERNAL_ERROR",
        message="An unexpected error occurred. Please try again later.",
        status_code=500
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handler for HTTP exceptions.
    
    Args:
        request: FastAPI request object
        exc: HTTPException that was raised
    
    Returns:
        Standardized error response
    """
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    logger.warning(
        "HTTP exception: status=%d detail=%s request_id=%s",
        exc.status_code,
        sanitize_for_logging(str(exc.detail)),
        request_id
    )
    
    return create_error_response(
        code=f"HTTP_{exc.status_code}",
        message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        status_code=exc.status_code
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Configure exception handlers for the application."""
    app.add_exception_handler(Exception, global_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
