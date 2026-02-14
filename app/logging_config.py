"""Structured logging configuration for production."""
from __future__ import annotations

import logging
import sys
import json
import uuid
from datetime import datetime, timezone
from contextvars import ContextVar

# Context variable for request ID
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Get the current request ID from context."""
    return request_id_ctx.get()


def set_request_id(request_id: str) -> None:
    """Set the request ID in context."""
    request_id_ctx.set(request_id)


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return uuid.uuid4().hex[:12]


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging.
    
    Uses 'severity' instead of 'level' for Google Cloud Logging compatibility.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": record.levelname,  # Cloud Logging expects 'severity'
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add request ID if available
        request_id = get_request_id()
        if request_id:
            log_data["request_id"] = request_id
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)
        
        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """Human-readable log formatter for development."""
    
    def format(self, record: logging.LogRecord) -> str:
        request_id = get_request_id()
        request_id_str = f"[{request_id}] " if request_id else ""
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        base = f"{timestamp} {record.levelname:8} {request_id_str}{record.name}: {record.getMessage()}"
        
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        
        return base


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configure application logging."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    
    # Set formatter based on format type
    if log_format.lower() == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(TextFormatter())
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = [handler]
    
    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if log_level.upper() == "DEBUG" else logging.WARNING
    )
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    # Create app logger
    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)
    
    app_logger.info(f"Logging configured: level={log_level}, format={log_format}")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(f"app.{name}")
