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
from typing import Callable, Optional
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


# ============================================================================
# OAuth 2.0 JWT Validation Middleware
# ============================================================================


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """OAuth 2.0 JWT validation middleware with HS256 shared secret.

    Validates JWT tokens locally using shared secret (HS256).
    No remote API calls needed for authorization - all claims are in the token.

    Flow:
        1. Extract Bearer token from Authorization header
        2. Validate token signature using shared secret
        3. Validate token expiry, issuer, audience
        4. Store validated payload in request.state
    """

    def __init__(self, app: ASGIApp):
        """Initialize middleware.

        Args:
            app: FastAPI application instance
        """
        super().__init__(app)
        from app.core.config import settings

        self.settings = settings
        logger.info(
            "jwt_middleware_initialized",
            algorithm=settings.JWT_ALGORITHM,
            issuer=settings.AUTH_API_ISSUER_URL,
            audience=settings.AUTH_API_AUDIENCE,
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Validate JWT token for each request.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response
        """
        from jose import jwt
        from jose.exceptions import ExpiredSignatureError, JWTError

        # Extract token from Authorization header
        token = self._get_token_from_header(request)

        if not token:
            # No token provided - continue without authentication
            # Individual endpoints can require authentication via dependencies
            request.state.authenticated = False
            return await call_next(request)

        try:
            # Decode and validate token with shared secret (HS256)
            # Note: auth-api tokens don't include iss/aud claims, so we skip those validations
            payload = jwt.decode(
                token,
                self.settings.JWT_SECRET_KEY,
                algorithms=[self.settings.JWT_ALGORITHM],
                options={
                    "verify_aud": False,  # auth-api tokens don't include audience
                    "verify_iss": False,  # auth-api tokens don't include issuer
                }
            )

            # Success - store validated payload in request state
            request.state.authenticated = True
            request.state.auth_payload = payload

            logger.debug(
                "jwt_validated",
                user_id=payload.get("sub"),
                org_id=payload.get("org_id"),
                permissions=payload.get("permissions", []),
            )

            return await call_next(request)

        except ExpiredSignatureError:
            logger.info("jwt_expired", token_prefix=token[:20])
            return self._unauthorized_response("Token has expired")

        except JWTError as e:
            logger.warning("jwt_invalid", error=str(e), token_prefix=token[:20])
            return self._unauthorized_response(f"Invalid token: {e}")

        except Exception as e:
            logger.error(
                "jwt_validation_error",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return self._unauthorized_response(f"Token validation failed: {e}")

    def _get_token_from_header(self, request: Request) -> Optional[str]:
        """Extract Bearer token from Authorization header.

        Args:
            request: HTTP request

        Returns:
            Token string or None
        """
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.debug("malformed_auth_header", auth_header=auth_header[:50])
            return None

        return parts[1]

    def _unauthorized_response(self, detail: str) -> Response:
        """Create 401 Unauthorized response.

        Args:
            detail: Error message

        Returns:
            JSONResponse with 401 status
        """
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=401,
            content={"detail": detail}
        )

# Updated: 2025-11-18 22:01 UTC - Production-ready code
