"""
Custom FastAPI exception handlers for structured error logging.

Ensures all exceptions are logged with full context for debugging.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging_config import get_logger


logger = get_logger(__name__)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle HTTP exceptions with structured logging.

    Args:
        request: FastAPI request object
        exc: HTTP exception

    Returns:
        JSON response with error details
    """
    logger.warning(
        "http_exception",
        method=request.method,
        path=str(request.url.path),
        status_code=exc.status_code,
        detail=exc.detail if hasattr(exc, 'detail') else str(exc),
        client_host=request.client.host if request.client else "unknown",
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail if hasattr(exc, 'detail') else "An error occurred",
            "status_code": exc.status_code,
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request validation errors with structured logging.

    Args:
        request: FastAPI request object
        exc: Validation exception

    Returns:
        JSON response with validation error details
    """
    errors = exc.errors()

    logger.warning(
        "validation_error",
        method=request.method,
        path=str(request.url.path),
        error_count=len(errors),
        errors=errors,
        client_host=request.client.host if request.client else "unknown",
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "status_code": 422,
            "details": errors,
        },
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions with structured logging.

    Args:
        request: FastAPI request object
        exc: Unhandled exception

    Returns:
        JSON response with generic error message
    """
    logger.error(
        "unhandled_exception",
        method=request.method,
        path=str(request.url.path),
        error_type=type(exc).__name__,
        error_message=str(exc),
        client_host=request.client.host if request.client else "unknown",
        exc_info=True,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "status_code": 500,
        },
    )
