"""
FastAPI Middleware for Request Tracking and Logging

Features:
- Request correlation IDs for distributed tracing
- Comprehensive request/response logging
- Performance metrics (request duration)
- Error tracking with context
- Security headers logging
- Prometheus metrics collection
"""

import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging_config import get_logger, set_trace_id, clear_trace_id


logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request trace IDs and comprehensive logging.

    Functionality:
    1. Generates unique trace ID for each request
    2. Injects trace ID into logging context
    3. Logs request details (method, path, client, headers)
    4. Logs response details (status, duration)
    5. Tracks performance metrics
    6. Handles exceptions with full context
    7. Adds both X-Trace-ID and X-Correlation-ID headers for compatibility
    """

    def __init__(self, app: ASGIApp):
        """Initialize middleware.

        Args:
            app: FastAPI application instance
        """
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process each request with trace ID and logging.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response
        """
        # Generate trace ID (check headers first, then generate)
        # Priority: X-Trace-ID > X-Correlation-ID > generate new UUID
        trace_id = (
            request.headers.get("X-Trace-ID") or
            request.headers.get("X-Correlation-ID") or
            str(uuid.uuid4())
        )

        # Set trace ID in logging context
        set_trace_id(trace_id)

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
            endpoint=path,
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
                endpoint=path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

            # Add trace ID to response headers (both formats for compatibility)
            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Correlation-ID"] = trace_id

            return response

        except Exception as exc:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log error with full context
            logger.error(
                "request_failed",
                method=method,
                path=path,
                endpoint=path,
                client_host=client_host,
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error_message=str(exc),
                exc_info=True,
            )

            # Re-raise exception to be handled by FastAPI exception handlers
            raise

        finally:
            # Clear trace ID from context
            clear_trace_id()


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


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware for automatic Prometheus metrics collection.

    Tracks:
    - HTTP request counts by method, endpoint, and status
    - HTTP request duration by method and endpoint
    - Active HTTP requests by method
    - Errors by type and endpoint
    """

    def __init__(self, app: ASGIApp):
        """Initialize middleware.

        Args:
            app: FastAPI application instance
        """
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Track metrics for each request.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response
        """
        # Import here to avoid circular imports
        from app.api.v1.metrics import (
            http_requests_total,
            http_request_duration_seconds,
            http_requests_in_progress,
            errors_total,
        )
        from app.core.config import settings

        method = request.method
        path = request.url.path

        # Skip metrics for /metrics endpoint to avoid recursion
        if path == "/metrics":
            return await call_next(request)

        # Increment in-progress counter
        http_requests_in_progress.labels(
            service=settings.SERVICE_NAME,
            method=method
        ).inc()

        start_time = time.time()
        status_code = 500  # Default to error if something goes wrong

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response

        except Exception as exc:
            # Track errors
            errors_total.labels(
                service=settings.SERVICE_NAME,
                error_type=type(exc).__name__,
                endpoint=path
            ).inc()
            raise

        finally:
            # Calculate duration
            duration = time.time() - start_time

            # Decrement in-progress counter
            http_requests_in_progress.labels(
                service=settings.SERVICE_NAME,
                method=method
            ).dec()

            # Record request count
            http_requests_total.labels(
                service=settings.SERVICE_NAME,
                method=method,
                endpoint=path,
                status=status_code
            ).inc()

            # Record request duration
            http_request_duration_seconds.labels(
                service=settings.SERVICE_NAME,
                method=method,
                endpoint=path
            ).observe(duration)
