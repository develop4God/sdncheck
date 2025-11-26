"""
FastAPI Middleware for Sanctions Screening API

Provides CORS configuration, request logging, and global error handling.
"""

import os
import re
import time
import logging
import json
from datetime import datetime, timezone
from typing import Callable, List
from pathlib import Path
from collections import deque

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from xml_utils import sanitize_for_logging

logger = logging.getLogger(__name__)

# ============================================================================
# CONNECTION LOG - Sistema de logging propio para depuración frontend-backend
# ============================================================================

# Directorio de logs
LOG_DIR = Path("/app/python/logs") if Path("/app").exists() else Path("./logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
CONNECTION_LOG_FILE = LOG_DIR / "connection_debug.log"

# Buffer en memoria para los últimos N logs (acceso rápido vía endpoint)
MAX_LOG_ENTRIES = 100
connection_log_buffer: deque = deque(maxlen=MAX_LOG_ENTRIES)


def log_connection(event_type: str, data: dict) -> None:
    """Registra un evento de conexión frontend-backend en archivo y memoria."""
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = {
        "timestamp": timestamp,
        "event": event_type,
        **data
    }
    
    # Guardar en buffer de memoria
    connection_log_buffer.append(entry)
    
    # Guardar en archivo
    try:
        with open(CONNECTION_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Error writing connection log: {e}")


def get_recent_connection_logs(limit: int = 50) -> list:
    """Retorna los últimos N logs de conexión."""
    logs = list(connection_log_buffer)
    return logs[-limit:] if len(logs) > limit else logs


def get_connection_log_file_content(lines: int = 100) -> str:
    """Lee las últimas N líneas del archivo de log."""
    try:
        if CONNECTION_LOG_FILE.exists():
            with open(CONNECTION_LOG_FILE, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
                return "".join(all_lines[-lines:])
        return "Log file not found"
    except Exception as e:
        return f"Error reading log: {e}"

# Default allowed origins for localhost development
DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",  # Common Electron dev port
    "http://localhost:5173",  # Vite dev port
    "http://localhost:8080",  # Common dev port
    "http://localhost:8000",  # FastAPI default port
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8000",
]


def _build_cors_regex_pattern(allowed_origins: List[str]) -> tuple:
    """Build regex pattern for CORS from allowed origins list.

    Args:
        allowed_origins: List of allowed origins (may include wildcards like *.railway.app)

    Returns:
        Tuple of (combined_regex_pattern or None, exact_origins list)
    """
    regex_patterns = []
    exact_origins = []

    for origin in allowed_origins:
        if "*.up.railway.app" in origin:
            # Convert wildcard to regex pattern for Railway subdomains
            regex_patterns.append(r"https://[\w-]+\.up\.railway\.app")
        elif "*.railway.app" in origin:
            regex_patterns.append(r"https://[\w-]+\.railway\.app")
        else:
            exact_origins.append(origin)

    if not regex_patterns:
        return None, exact_origins

    # Combine regex patterns
    combined_regex = "|".join(f"({p})" for p in regex_patterns)
    if exact_origins:
        exact_escaped = "|".join(re.escape(o) for o in exact_origins)
        combined_regex = f"({combined_regex})|({exact_escaped})"

    return combined_regex, exact_origins


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
    has_wildcard = any("*" in origin for origin in allowed_origins)

    if has_wildcard:
        combined_regex, exact_origins = _build_cors_regex_pattern(allowed_origins)

        if combined_regex:
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

        # Capturar información de la petición
        origin = request.headers.get("origin", "<no origin>")
        user_agent = request.headers.get("user-agent", "<no user-agent>")
        referer = request.headers.get("referer", "<no referer>")
        host = request.headers.get("host", "<no host>")
        
        # Log de conexión propio (archivo + memoria)
        request_data = {
            "request_id": request_id,
            "method": request.method,
            "path": str(request.url.path),
            "query_params": dict(request.query_params),
            "origin": origin,
            "host": host,
            "user_agent": user_agent,
            "referer": referer,
            "all_headers": {k: v for k, v in request.headers.items()},
            "client_ip": request.client.host if request.client else "<unknown>",
        }
        log_connection("REQUEST", request_data)
        
        # También loguear a consola (para Railway)
        logger.info(f"[CONN] REQUEST: origin={origin} method={request.method} path={request.url.path}")
        logger.info(f"[CONN] Headers: {dict(request.headers)}")

        # Store request ID for later use
        request.state.request_id = request_id
        request.state.start_time = start_time

        # Log incoming request (sanitize path to prevent log injection)
        sanitized_path = sanitize_for_logging(str(request.url.path))
        logger.info(
            "Request: method=%s path=%s request_id=%s",
            request.method,
            sanitized_path,
            request_id,
        )

        try:
            response = await call_next(request)

            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)

            # Add custom headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Processing-Time-MS"] = str(processing_time_ms)

            # Log de conexión propio (respuesta)
            response_data = {
                "request_id": request_id,
                "status_code": response.status_code,
                "processing_time_ms": processing_time_ms,
                "response_headers": {k: v for k, v in response.headers.items()},
                "cors_origin": response.headers.get("access-control-allow-origin", "<not set>"),
            }
            log_connection("RESPONSE", response_data)
            
            # También loguear a consola
            logger.info(f"[CONN] RESPONSE: status={response.status_code} cors_origin={response_data['cors_origin']} time={processing_time_ms}ms")

            # Log response
            logger.info(
                "Response: status=%d processing_time_ms=%d request_id=%s",
                response.status_code,
                processing_time_ms,
                request_id,
            )

            return response

        except Exception as exc:
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Log de error de conexión
            error_data = {
                "request_id": request_id,
                "error": str(exc),
                "processing_time_ms": processing_time_ms,
            }
            log_connection("ERROR", error_data)
            
            logger.error(
                "Request failed: error=%s processing_time_ms=%d request_id=%s",
                sanitize_for_logging(str(exc)),
                processing_time_ms,
                request_id,
            )
            raise


def create_error_response(
    code: str,
    message: str,
    status_code: int = 500,
    field: str = None,
    suggestion: str = None,
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if field:
        error_detail["field"] = field
    if suggestion:
        error_detail["suggestion"] = suggestion

    return JSONResponse(status_code=status_code, content={"error": error_detail})


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
    request_id = getattr(request.state, "request_id", "unknown")

    # Log the full error for debugging
    logger.error(
        "Unhandled exception: type=%s message=%s request_id=%s",
        type(exc).__name__,
        sanitize_for_logging(str(exc)),
        request_id,
    )

    # Handle specific exception types
    if isinstance(exc, InputValidationError):
        return create_error_response(
            code=exc.code,
            message=str(exc),
            status_code=422,
            field=exc.field,
            suggestion=exc.suggestion,
        )

    if isinstance(exc, ConfigurationError):
        return create_error_response(
            code="CONFIGURATION_ERROR",
            message="Service configuration is invalid. Please contact administrator.",
            status_code=503,
        )

    if isinstance(exc, HTTPException):
        return create_error_response(
            code=f"HTTP_{exc.status_code}",
            message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            status_code=exc.status_code,
        )

    # Generic error - sanitize message to prevent info leakage
    return create_error_response(
        code="INTERNAL_ERROR",
        message="An unexpected error occurred. Please try again later.",
        status_code=500,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handler for HTTP exceptions.

    Args:
        request: FastAPI request object
        exc: HTTPException that was raised

    Returns:
        Standardized error response
    """
    request_id = getattr(request.state, "request_id", "unknown")

    logger.warning(
        "HTTP exception: status=%d detail=%s request_id=%s",
        exc.status_code,
        sanitize_for_logging(str(exc.detail)),
        request_id,
    )

    return create_error_response(
        code=f"HTTP_{exc.status_code}",
        message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        status_code=exc.status_code,
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Configure exception handlers for the application."""
    app.add_exception_handler(Exception, global_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
