"""
FastAPI Middleware for Request Tracking and Logging

Features:
- Request correlation IDs for distributed tracing
- Comprehensive request/response logging
- Performance metrics (request duration)
- Error tracking with context
- Security headers logging
"""

import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging_config import get_logger, set_correlation_id, clear_correlation_id


logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request correlation IDs and comprehensive logging.

    Functionality:
    1. Generates unique correlation ID for each request
    2. Injects correlation ID into logging context
    3. Logs request details (method, path, client, headers)
    4. Logs response details (status, duration)
    5. Tracks performance metrics
    6. Handles exceptions with full context
    """

    def __init__(self, app: ASGIApp):
        """Initialize middleware.

        Args:
            app: FastAPI application instance
        """
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process each request with correlation ID and logging.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response
        """
        # Generate correlation ID (check header first, then generate)
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())

        # Set correlation ID in logging context
        set_correlation_id(correlation_id)

        # Start timer
        start_time = time.time()

        # Extract request details
        client_host = request.client.host if request.client else "unknown"
        client_port = request.client.port if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        method = request.method
        path = request.url.path
        query_params = dict(request.query_params) if request.query_params else {}

        # Log incoming request
        logger.info(
            "request_started",
            method=method,
            path=path,
            client_host=client_host,
            client_port=client_port,
            user_agent=user_agent,
            query_params=query_params,
            correlation_id=correlation_id,
        )

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log successful response
            logger.info(
                "request_completed",
                method=method,
                path=path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                correlation_id=correlation_id,
            )

            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id

            return response

        except Exception as exc:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log error with full context
            logger.error(
                "request_failed",
                method=method,
                path=path,
                client_host=client_host,
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error_message=str(exc),
                correlation_id=correlation_id,
                exc_info=True,
            )

            # Re-raise exception to be handled by FastAPI exception handlers
            raise

        finally:
            # Clear correlation ID from context
            clear_correlation_id()


class PerformanceLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for tracking slow requests.

    Logs warnings for requests exceeding performance thresholds.
    Useful for identifying performance bottlenecks.
    """

    def __init__(self, app: ASGIApp, slow_request_threshold_ms: float = 1000.0):
        """Initialize performance middleware.

        Args:
            app: FastAPI application instance
            slow_request_threshold_ms: Threshold in ms for slow request warnings
        """
        super().__init__(app)
        self.slow_request_threshold_ms = slow_request_threshold_ms

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Track request performance.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response
        """
        start_time = time.time()

        response = await call_next(request)

        duration_ms = (time.time() - start_time) * 1000

        # Log slow requests
        if duration_ms > self.slow_request_threshold_ms:
            logger.warning(
                "slow_request_detected",
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration_ms, 2),
                threshold_ms=self.slow_request_threshold_ms,
                status_code=response.status_code,
            )

        return response
