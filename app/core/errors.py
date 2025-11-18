"""
Enterprise Error Handling System

Provides standardized error codes and exceptions for the entire application.
Makes debugging easier and API responses predictable for clients.
"""
from enum import Enum
from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class ErrorCode(str, Enum):
    """Standardized error codes for the entire application."""

    # Upload errors (UPLOAD_xxx)
    UPLOAD_FILE_TOO_LARGE = "UPLOAD_001"
    UPLOAD_INVALID_TYPE = "UPLOAD_002"
    UPLOAD_RATE_LIMIT = "UPLOAD_003"

    # Processing errors (JOB_xxx)
    JOB_CREATION_FAILED = "JOB_001"
    STAGING_FAILED = "JOB_002"
    TASK_QUEUE_FAILED = "JOB_003"
    JOB_NOT_FOUND = "JOB_004"

    # Auth errors (AUTH_xxx)
    AUTH_INVALID_TOKEN = "AUTH_001"
    AUTH_PERMISSION_DENIED = "AUTH_002"
    AUTH_ORG_MISMATCH = "AUTH_003"

    # Validation errors (VAL_xxx)
    VAL_INVALID_BUCKET = "VAL_001"
    VAL_INVALID_METADATA = "VAL_002"
    VAL_MISSING_PARAMETER = "VAL_003"

    # Storage errors (STORAGE_xxx)
    STORAGE_WRITE_FAILED = "STORAGE_001"
    STORAGE_READ_FAILED = "STORAGE_002"
    STORAGE_DELETE_FAILED = "STORAGE_003"


class ServiceError(HTTPException):
    """
    Base class for business logic errors.

    This exception is caught by FastAPI's exception handler and converted
    to a clean JSON response with standardized structure:

    {
        "code": "UPLOAD_001",
        "message": "File size exceeds maximum allowed",
        "details": {"max_size_mb": 10, "actual_size_mb": 15}
    }

    Benefits:
    - Frontend can check specific error codes
    - Consistent error format across all endpoints
    - Details provide debugging context without exposing internals
    """

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status_code,
            detail={
                "code": code,
                "message": message,
                "details": details or {}
            }
        )
        self.code = code
        self.user_message = message
        self.error_details = details or {}


# Convenience functions for common errors
def upload_error(code: ErrorCode, message: str, details: Optional[Dict[str, Any]] = None) -> ServiceError:
    """Create an upload-related error (400 Bad Request)."""
    return ServiceError(status.HTTP_400_BAD_REQUEST, code, message, details)


def processing_error(code: ErrorCode, message: str, details: Optional[Dict[str, Any]] = None) -> ServiceError:
    """Create a processing-related error (500 Internal Server Error)."""
    return ServiceError(status.HTTP_500_INTERNAL_SERVER_ERROR, code, message, details)


def auth_error(code: ErrorCode, message: str, details: Optional[Dict[str, Any]] = None) -> ServiceError:
    """Create an authentication-related error (403 Forbidden)."""
    return ServiceError(status.HTTP_403_FORBIDDEN, code, message, details)


def not_found_error(code: ErrorCode, message: str, details: Optional[Dict[str, Any]] = None) -> ServiceError:
    """Create a not-found error (404 Not Found)."""
    return ServiceError(status.HTTP_404_NOT_FOUND, code, message, details)
