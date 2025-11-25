"""
Security Event Logging Module

Provides structured logging for security-related events including:
- Validation failures
- XXE/injection attempt detection
- Suspicious patterns
- Access control events

SECURITY: Ensures sensitive data is sanitized before logging.
"""

import logging
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field as dataclass_field


@dataclass
class SecurityEvent:
    """Structured security event for logging"""
    event_type: str  # e.g., VALIDATION_FAILED, XXE_ATTEMPT, INJECTION_BLOCKED
    severity: str  # WARNING, ERROR, CRITICAL
    field_name: str = ""  # Field that triggered the event
    error_code: str = ""
    sanitized_input: str = ""  # First 50 chars, sanitized
    source: str = ""  # Module/function that detected the event
    request_id: str = ""
    user_id: str = ""
    source_ip: str = ""
    additional_context: Dict[str, Any] = dataclass_field(default_factory=dict)
    timestamp: str = dataclass_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'timestamp': self.timestamp,
            'event_type': self.event_type,
            'severity': self.severity,
            'field': self.field_name,
            'error_code': self.error_code,
            'sanitized_input': self.sanitized_input,
            'source': self.source,
            'request_id': self.request_id,
            'user_id': self.user_id,
            'source_ip': self.source_ip,
            'context': self.additional_context
        }
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), ensure_ascii=False)


class SecurityLogger:
    """Handles security event logging with structured output
    
    Features:
    - Separate security.log file
    - JSON-formatted events for easy parsing
    - Automatic sanitization of sensitive data
    - Request ID correlation
    - Log rotation support (via external log rotation tools)
    """
    
    def __init__(
        self, 
        log_dir: str = "logs",
        log_level: int = logging.WARNING,
        enable_console: bool = False,
        enable_file: bool = True
    ):
        """Initialize security logger
        
        Args:
            log_dir: Directory for log files
            log_level: Minimum log level to record
            enable_console: Also output to console
            enable_file: Write to security.log file
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create dedicated security logger
        self.logger = logging.getLogger('security')
        self.logger.setLevel(log_level)
        self.logger.handlers.clear()  # Remove any existing handlers
        
        # Create formatter for structured logging
        formatter = logging.Formatter(
            '%(asctime)s - SECURITY - %(levelname)s - %(message)s'
        )
        
        if enable_file:
            # File handler for security events
            security_log_path = self.log_dir / "security.log"
            file_handler = logging.FileHandler(security_log_path, encoding='utf-8')
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        
        if enable_console:
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(log_level)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        # Track current request context
        self._request_id: str = ""
        self._user_id: str = ""
        self._source_ip: str = ""
    
    def set_request_context(
        self, 
        request_id: Optional[str] = None,
        user_id: str = "",
        source_ip: str = ""
    ) -> str:
        """Set context for the current request
        
        Args:
            request_id: Unique request identifier (auto-generated if None)
            user_id: User identifier if available
            source_ip: Source IP address if available
            
        Returns:
            The request ID being used
        """
        self._request_id = request_id or f"REQ-{uuid.uuid4().hex[:8]}"
        self._user_id = user_id
        self._source_ip = source_ip
        return self._request_id
    
    def clear_request_context(self) -> None:
        """Clear the current request context"""
        self._request_id = ""
        self._user_id = ""
        self._source_ip = ""
    
    def _sanitize_input(self, text: str, max_length: int = 50) -> str:
        """Sanitize input for safe logging
        
        Uses the shared sanitize_for_logging function from xml_utils for
        consistent sanitization behavior.
        
        Args:
            text: Input text to sanitize
            max_length: Maximum length to include
            
        Returns:
            Sanitized text safe for logging
        """
        from xml_utils import sanitize_for_logging
        
        if not text:
            return ""
        # Use shared sanitization logic
        sanitized = sanitize_for_logging(text)
        # Apply additional length truncation for security logs
        if len(sanitized) > max_length:
            return sanitized[:max_length] + "...(truncated)"
        return sanitized
    
    def _sanitize_context(self, context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Sanitize all values in a context dictionary for safe logging
        
        Prevents JSON injection by sanitizing all string values in the dict.
        Non-string values are converted to strings and sanitized.
        
        Args:
            context: Dictionary with context data
            
        Returns:
            Sanitized dictionary safe for JSON logging
        """
        if not context:
            return {}
        
        sanitized = {}
        for key, value in context.items():
            # Sanitize the key as well (defense in depth)
            safe_key = self._sanitize_input(str(key), max_length=100) if key else "unknown"
            
            # Sanitize the value
            if value is None:
                sanitized[safe_key] = None
            elif isinstance(value, bool):
                sanitized[safe_key] = value
            elif isinstance(value, (int, float)):
                sanitized[safe_key] = value
            elif isinstance(value, str):
                sanitized[safe_key] = self._sanitize_input(value, max_length=200)
            elif isinstance(value, dict):
                # Recursively sanitize nested dicts
                sanitized[safe_key] = self._sanitize_context(value)
            elif isinstance(value, (list, tuple)):
                # Sanitize list/tuple items
                sanitized[safe_key] = [
                    self._sanitize_input(str(item), max_length=200) if isinstance(item, str)
                    else item if isinstance(item, (bool, int, float, type(None)))
                    else self._sanitize_input(str(item), max_length=200)
                    for item in value
                ]
            else:
                # For other types, convert to string and sanitize
                sanitized[safe_key] = self._sanitize_input(str(value), max_length=200)
        
        return sanitized
    
    def log_validation_failure(
        self,
        field: str,
        error_code: str,
        input_value: str,
        source: str = "",
        additional_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log a validation failure event
        
        Args:
            field: Field name that failed validation
            error_code: Error code for the failure
            input_value: The input that failed (will be sanitized)
            source: Source module/function
            additional_context: Additional context data (will be sanitized)
        """
        event = SecurityEvent(
            event_type="VALIDATION_FAILED",
            severity="WARNING",
            field_name=field,
            error_code=error_code,
            sanitized_input=self._sanitize_input(input_value),
            source=source,
            request_id=self._request_id,
            user_id=self._user_id,
            source_ip=self._source_ip,
            additional_context=self._sanitize_context(additional_context)
        )
        
        self.logger.warning(event.to_json())
    
    def log_security_event(
        self,
        event_type: str,
        severity: str = "ERROR",
        field: str = "",
        error_code: str = "",
        input_value: str = "",
        source: str = "",
        blocked: bool = True,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log a security event (XXE attempt, injection, etc.)
        
        Args:
            event_type: Type of security event (XXE_ATTEMPT, SQL_INJECTION, etc.)
            severity: WARNING, ERROR, or CRITICAL
            field: Related field if applicable
            error_code: Error code
            input_value: Suspicious input (will be sanitized)
            source: Source module/function
            blocked: Whether the attempt was blocked
            additional_context: Additional context (will be sanitized)
        """
        # Sanitize context first, then add blocked status
        context = self._sanitize_context(additional_context)
        context['blocked'] = blocked
        
        event = SecurityEvent(
            event_type=event_type,
            severity=severity,
            field_name=field,
            error_code=error_code,
            sanitized_input=self._sanitize_input(input_value),
            source=source,
            request_id=self._request_id,
            user_id=self._user_id,
            source_ip=self._source_ip,
            additional_context=context
        )
        
        if severity == "CRITICAL":
            self.logger.critical(event.to_json())
        elif severity == "ERROR":
            self.logger.error(event.to_json())
        else:
            self.logger.warning(event.to_json())
    
    def log_xxe_attempt(
        self,
        source: str = "XML parsing",
        file_name: str = "",
        blocked: bool = True
    ) -> None:
        """Log an XXE attack attempt
        
        Args:
            source: Where the attempt was detected
            file_name: Name of the XML file
            blocked: Whether the attempt was blocked
        """
        self.log_security_event(
            event_type="XXE_ATTEMPT",
            severity="ERROR",
            source=source,
            blocked=blocked,
            additional_context={"file": file_name}
        )
    
    def log_injection_attempt(
        self,
        injection_type: str,  # SQL, LOG, COMMAND
        field: str,
        input_value: str,
        source: str = "",
        blocked: bool = True
    ) -> None:
        """Log an injection attack attempt
        
        Args:
            injection_type: Type of injection (SQL, LOG, COMMAND)
            field: Field where injection was attempted
            input_value: The malicious input (will be sanitized)
            source: Source module/function
            blocked: Whether the attempt was blocked
        """
        self.log_security_event(
            event_type=f"{injection_type.upper()}_INJECTION_ATTEMPT",
            severity="ERROR",
            field=field,
            input_value=input_value,
            source=source,
            blocked=blocked
        )


# Global security logger instance
_security_logger: Optional[SecurityLogger] = None


def get_security_logger(
    log_dir: str = "logs",
    enable_console: bool = False
) -> SecurityLogger:
    """Get or create the global security logger instance
    
    Args:
        log_dir: Directory for log files
        enable_console: Also output to console
        
    Returns:
        SecurityLogger instance
    """
    global _security_logger
    if _security_logger is None:
        _security_logger = SecurityLogger(
            log_dir=log_dir,
            enable_console=enable_console
        )
    return _security_logger


def reset_security_logger() -> None:
    """Reset the global security logger (for testing)"""
    global _security_logger
    _security_logger = None
