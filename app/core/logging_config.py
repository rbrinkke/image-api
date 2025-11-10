"""
Professional Logging Configuration for image-api

Features:
- JSON structured logs via structlog for production
- Pretty console output for development
- Granular log level control per logger
- Request correlation IDs for request tracing
- Third-party library noise filtering
- Zero log duplication
- Container-ready stdout/stderr streams
- Comprehensive debug information for troubleshooting

Architecture:
- structlog: Structured logging with context
- python-json-logger: JSON formatting for log aggregation
- Standard library logging: Backend compatibility
- Dual streams: INFO/DEBUG → stdout, ERROR/CRITICAL → stderr
"""

import logging
import logging.config
import sys
from typing import Any, Dict, Optional
import structlog
from structlog.types import EventDict, Processor
from pythonjsonlogger import jsonlogger


# Trace ID context variable (set by middleware)
# Note: We use "trace_id" for observability stack compatibility
# while maintaining "correlation_id" as an alias for backward compatibility
_trace_id_context: Optional[str] = None


def set_trace_id(trace_id: str) -> None:
    """Set the trace ID for the current request context.

    Called by middleware to inject request tracking ID.
    """
    global _trace_id_context
    _trace_id_context = trace_id


def get_trace_id() -> Optional[str]:
    """Get the current trace ID.

    Returns:
        Trace ID if set, None otherwise
    """
    return _trace_id_context


def clear_trace_id() -> None:
    """Clear the trace ID after request completes."""
    global _trace_id_context
    _trace_id_context = None


# Backward compatibility aliases
set_correlation_id = set_trace_id
get_correlation_id = get_trace_id
clear_correlation_id = clear_trace_id


def add_app_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add application context to all log records.

    Injects:
    - service: Service name
    - version: Application version
    - trace_id: Request tracking ID (if available)
    - correlation_id: Alias for trace_id (backward compatibility)
    """
    from app.core.config import settings

    event_dict["service"] = settings.SERVICE_NAME
    event_dict["version"] = settings.VERSION
    event_dict["environment"] = settings.ENVIRONMENT

    # Add trace ID if available (primary field for observability stack)
    trace_id = get_trace_id()
    if trace_id:
        event_dict["trace_id"] = trace_id
        # Also add as correlation_id for backward compatibility
        event_dict["correlation_id"] = trace_id

    return event_dict


def add_log_level(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add log level to event dict for consistency."""
    event_dict["level"] = method_name.upper()
    return event_dict


def filter_by_level(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Filter logs based on configured log level.

    This processor ensures log levels are respected in structlog.
    """
    from app.core.config import settings

    configured_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    event_level = getattr(logging, method_name.upper(), logging.INFO)

    if event_level < configured_level:
        raise structlog.DropEvent

    return event_dict


def configure_structlog(debug: bool = False, json_logs: bool = True) -> None:
    """Configure structlog for structured logging.

    Args:
        debug: Enable debug mode with pretty console output
        json_logs: Use JSON formatting (True) or console (False)
    """
    # Shared processors for all configurations
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        add_app_context,
        add_log_level,
    ]

    if debug and not json_logs:
        # Development mode: Pretty console output with colors
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            )
        ]
    else:
        # Production mode: JSON structured logs
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields.

    Ensures consistent JSON structure across all log entries.
    """

    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        """Add custom fields to JSON log record."""
        super().add_fields(log_record, record, message_dict)

        # Ensure timestamp is always present (ISO 8601 with timezone)
        if not log_record.get('timestamp'):
            log_record['timestamp'] = self.formatTime(record, self.datefmt)

        # Ensure level is always present and uppercase
        if not log_record.get('level'):
            log_record['level'] = record.levelname.upper()
        else:
            log_record['level'] = log_record['level'].upper()

        # Add logger name
        log_record['logger'] = record.name

        # Add trace ID if available (primary for observability stack)
        trace_id = get_trace_id()
        if trace_id:
            if 'trace_id' not in log_record:
                log_record['trace_id'] = trace_id
            # Also add as correlation_id for backward compatibility
            if 'correlation_id' not in log_record:
                log_record['correlation_id'] = trace_id


def get_logging_config(debug: bool = False, json_logs: bool = True) -> Dict[str, Any]:
    """Generate logging dictConfig.

    Creates dual-stream logging configuration:
    - stdout: INFO and DEBUG level logs
    - stderr: ERROR and CRITICAL level logs

    Args:
        debug: Enable debug mode
        json_logs: Use JSON formatting

    Returns:
        Dictionary configuration for logging.config.dictConfig
    """
    from app.core.config import settings

    log_level = settings.LOG_LEVEL.upper()

    # Determine formatter
    if debug and not json_logs:
        formatter_class = "logging.Formatter"
        formatter_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    else:
        formatter_class = "app.core.logging_config.CustomJsonFormatter"
        formatter_format = "%(timestamp)s %(level)s %(name)s %(message)s"

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": formatter_class,
                "format": formatter_format,
            },
            "console": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            # stdout handler for INFO and DEBUG
            "stdout": {
                "class": "logging.StreamHandler",
                "level": "DEBUG",
                "formatter": "json" if json_logs else "console",
                "stream": "ext://sys.stdout",
                "filters": ["info_and_below"],
            },
            # stderr handler for ERROR and CRITICAL
            "stderr": {
                "class": "logging.StreamHandler",
                "level": "ERROR",
                "formatter": "json" if json_logs else "console",
                "stream": "ext://sys.stderr",
            },
        },
        "filters": {
            "info_and_below": {
                "()": "app.core.logging_config.InfoAndBelowFilter",
            },
        },
        "loggers": {
            # Root logger
            "": {
                "handlers": ["stdout", "stderr"],
                "level": log_level,
                "propagate": False,
            },
            # Application loggers
            "app": {
                "handlers": ["stdout", "stderr"],
                "level": log_level,
                "propagate": False,
            },
            "uvicorn": {
                "handlers": ["stdout", "stderr"],
                "level": "INFO",
                "propagate": False,
            },
            "fastapi": {
                "handlers": ["stdout", "stderr"],
                "level": "INFO",
                "propagate": False,
            },
            # Uvicorn loggers - CRITICAL: Set propagate=False to prevent duplicates
            "uvicorn": {
                "handlers": ["stdout", "stderr"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": [],  # Disabled - we use custom RequestLoggingMiddleware
                "level": "CRITICAL",  # Effectively disabled
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["stderr"],
                "level": "INFO",
                "propagate": False,
            },
            "celery": {
                "handlers": ["stdout", "stderr"],
                "level": "INFO",
                "propagate": False,
            },
            "celery.worker": {
                "handlers": ["stdout", "stderr"],
                "level": "INFO",
                "propagate": False,
            },
            "celery.task": {
                "handlers": ["stdout", "stderr"],
                "level": "INFO",
                "propagate": False,
            },
            # Redis/asyncio noise reduction
            "asyncio": {
                "handlers": ["stderr"],
                "level": "WARNING",
                "propagate": False,
            },
            "aioredis": {
                "handlers": ["stdout", "stderr"],
                "level": "WARNING",
                "propagate": False,
            },
            # HTTP client libraries
            "httpx": {
                "handlers": ["stdout", "stderr"],
                "level": "WARNING",
                "propagate": False,
            },
            "httpcore": {
                "handlers": ["stdout", "stderr"],
                "level": "WARNING",
                "propagate": False,
            },
            # AWS/boto libraries
            "botocore": {
                "handlers": ["stdout", "stderr"],
                "level": "WARNING",
                "propagate": False,
            },
            "boto3": {
                "handlers": ["stdout", "stderr"],
                "level": "WARNING",
                "propagate": False,
            },
            "aiobotocore": {
                "handlers": ["stdout", "stderr"],
                "level": "WARNING",
                "propagate": False,
            },
            # PIL/Pillow
            "PIL": {
                "handlers": ["stdout", "stderr"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }

    return config


class InfoAndBelowFilter(logging.Filter):
    """Filter that only allows INFO and below (DEBUG) to pass.

    Used to separate INFO/DEBUG logs to stdout from ERROR/CRITICAL to stderr.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Return True if log level is INFO or below."""
        return record.levelno <= logging.INFO


def setup_logging(debug: bool = False, json_logs: bool = True) -> None:
    """Initialize the complete logging system.

    This is the main entry point for logging configuration.
    Call this once at application startup.

    Args:
        debug: Enable debug mode with pretty console output
        json_logs: Use JSON formatting for log aggregation

    Example:
        >>> from app.core.config import settings
        >>> from app.core.logging_config import setup_logging
        >>> setup_logging(debug=settings.is_debug_mode, json_logs=settings.use_json_logs)
    """
    # Configure standard library logging
    logging_config = get_logging_config(debug=debug, json_logs=json_logs)
    logging.config.dictConfig(logging_config)

    # Configure structlog
    configure_structlog(debug=debug, json_logs=json_logs)

    # Log initialization
    logger = get_logger(__name__)
    logger.info(
        "logging_system_initialized",
        debug_mode=debug,
        json_logs=json_logs,
        log_level=logging.getLevelName(logging.root.level),
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("user_registered", user_id="123", email="user@example.com")
        >>> logger.error("processing_failed", job_id="abc", error="timeout")
    """
    return structlog.get_logger(name)
