"""Standardized error handling for mock servers."""

from fastapi import HTTPException, status
from typing import Optional, Dict, Any


class MockError(HTTPException):
    """Base exception for mock server errors.

    Provides consistent error responses across all mock servers.
    """

    def __init__(
        self,
        status_code: int,
        error_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize mock error.

        Args:
            status_code: HTTP status code
            error_type: Error type identifier
            message: Human-readable error message
            details: Additional error context
        """
        super().__init__(
            status_code=status_code,
            detail={
                "error": error_type,
                "message": message,
                "details": details or {}
            }
        )


class NotFoundError(MockError):
    """Resource not found error (404)."""

    def __init__(self, resource: str, identifier: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            error_type="NotFound",
            message=f"{resource} not found: {identifier}",
            details=details
        )


class ValidationError(MockError):
    """Validation error (400)."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_type="ValidationError",
            message=message,
            details=details
        )


class UnauthorizedError(MockError):
    """Authentication/authorization error (401)."""

    def __init__(self, message: str = "Invalid or missing authentication", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_type="Unauthorized",
            message=message,
            details=details
        )


class ConflictError(MockError):
    """Resource conflict error (409)."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            error_type="Conflict",
            message=message,
            details=details
        )


class RateLimitError(MockError):
    """Rate limit exceeded error (429)."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 3600, details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        error_details["retry_after"] = retry_after
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_type="RateLimitExceeded",
            message=message,
            details=error_details
        )


class InternalServerError(MockError):
    """Internal server error (500)."""

    def __init__(self, message: str = "Internal server error", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_type="InternalServerError",
            message=message,
            details=details
        )
