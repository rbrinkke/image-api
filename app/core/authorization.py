"""
Distributed Authorization System with Redis Caching
====================================================

Architecture:
- JWT contains minimal claims (user_id, org_id)
- Auth-API is source of truth for group permissions
- Redis cache layer with configurable TTL per permission type
- Circuit breaker pattern for auth-api resilience
- Graceful degradation with fail-closed default

Security Features:
- Cache isolation per organization
- Negative caching (permission denied)
- TTL stratification by permission sensitivity
- Circuit breaker prevents cascade failures
- Comprehensive audit logging

Usage Example:
    # Protect endpoint with permission check
    @router.post("/upload")
    async def upload_image(
        file: UploadFile,
        auth: AuthContext = Depends(require_permission("image:upload"))
    ):
        # User is authorized - proceed
        logger.info("upload", user_id=auth.user_id, org_id=auth.org_id)
        ...
"""

from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum
import json

import httpx
import redis.asyncio as redis
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging_config import get_logger


logger = get_logger(__name__)


# ============================================================================
# Data Models
# ============================================================================


class AuthContext(BaseModel):
    """Authenticated user context extracted from JWT token.

    Contains minimal claims - no groups, no permissions.
    Authorization happens via auth-api + cache.
    """
    user_id: str
    org_id: str
    email: Optional[str] = None
    name: Optional[str] = None


class CircuitBreakerState(Enum):
    """Circuit breaker states for auth-api resilience."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing - skip calls
    HALF_OPEN = "half_open"  # Testing recovery


class PermissionCheckResult(BaseModel):
    """Result of permission check from auth-api."""
    allowed: bool
    groups: Optional[list] = None  # Optional context
    reason: Optional[str] = None
    cached_until: Optional[str] = None


# ============================================================================
# Redis Authorization Cache
# ============================================================================


class AuthorizationCache:
    """Redis-based authorization cache with TTL support.

    Cache Key Pattern:
        auth:permission:{org_id}:{user_id}:{permission} → "1" (allowed) or "0" (denied)

    TTL Strategy:
        - Read permissions: 5 minutes (less sensitive)
        - Write permissions: 1 minute (more sensitive)
        - Admin permissions: 30 seconds (very sensitive)
        - Denied permissions: 2 minutes (negative caching)
    """

    def __init__(self, redis_client: redis.Redis):
        """Initialize cache manager.

        Args:
            redis_client: Async Redis connection
        """
        self.redis = redis_client

    def _make_cache_key(self, org_id: str, user_id: str, permission: str) -> str:
        """Generate cache key for permission check.

        Args:
            org_id: Organization ID
            user_id: User ID
            permission: Permission string (e.g., "image:read")

        Returns:
            str: Redis cache key
        """
        return f"auth:permission:{org_id}:{user_id}:{permission}"

    def _get_ttl_for_permission(self, permission: str, allowed: bool) -> int:
        """Determine TTL based on permission type and result.

        Args:
            permission: Permission string (e.g., "image:read")
            allowed: Whether permission was granted

        Returns:
            int: TTL in seconds
        """
        if not allowed:
            # Negative caching - denied permissions
            return settings.AUTH_CACHE_TTL_DENIED

        # Extract action from permission (e.g., "read" from "image:read")
        if ":" not in permission:
            return settings.AUTH_CACHE_TTL_WRITE  # Default

        action = permission.split(":", 1)[1].lower()

        # Map actions to TTL
        if action in ("read", "list", "view", "get"):
            return settings.AUTH_CACHE_TTL_READ
        elif action in ("admin", "delete", "purge"):
            return settings.AUTH_CACHE_TTL_ADMIN
        else:
            return settings.AUTH_CACHE_TTL_WRITE

    async def get(
        self,
        org_id: str,
        user_id: str,
        permission: str
    ) -> Optional[bool]:
        """Check if permission is cached.

        Args:
            org_id: Organization ID
            user_id: User ID
            permission: Permission string

        Returns:
            Optional[bool]: True if allowed, False if denied, None if not cached
        """
        if not settings.AUTH_CACHE_ENABLED:
            return None

        key = self._make_cache_key(org_id, user_id, permission)

        try:
            value = await self.redis.get(key)
            if value is None:
                return None

            # Decode boolean value ("1" = allowed, "0" = denied)
            result = value.decode() == "1"

            logger.debug(
                "auth_cache_hit",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                allowed=result,
                cache_key=key,
            )

            return result

        except Exception as e:
            logger.warning(
                "auth_cache_read_failed",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                error=str(e),
            )
            return None

    async def set(
        self,
        org_id: str,
        user_id: str,
        permission: str,
        allowed: bool,
        custom_ttl: Optional[int] = None
    ) -> None:
        """Cache permission check result.

        Args:
            org_id: Organization ID
            user_id: User ID
            permission: Permission string
            allowed: Whether permission is granted
            custom_ttl: Override default TTL (optional)
        """
        if not settings.AUTH_CACHE_ENABLED:
            return

        key = self._make_cache_key(org_id, user_id, permission)

        # Determine TTL
        ttl = custom_ttl if custom_ttl is not None else self._get_ttl_for_permission(permission, allowed)

        try:
            # Store as "1" for True, "0" for False
            value = "1" if allowed else "0"
            await self.redis.setex(key, ttl, value)

            logger.debug(
                "auth_cache_stored",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                allowed=allowed,
                ttl=ttl,
                cache_key=key,
            )

        except Exception as e:
            logger.warning(
                "auth_cache_write_failed",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                error=str(e),
            )

    async def invalidate_user(self, org_id: str, user_id: str) -> int:
        """Invalidate all cached permissions for a user.

        Useful when user's group membership changes.

        Args:
            org_id: Organization ID
            user_id: User ID

        Returns:
            int: Number of keys deleted
        """
        pattern = f"auth:permission:{org_id}:{user_id}:*"

        try:
            keys = []
            async for key in self.redis.scan_iter(match=pattern, count=100):
                keys.append(key)

            if keys:
                deleted = await self.redis.delete(*keys)
                logger.info(
                    "auth_cache_invalidated",
                    org_id=org_id,
                    user_id=user_id,
                    keys_deleted=deleted,
                )
                return deleted

            return 0

        except Exception as e:
            logger.error(
                "auth_cache_invalidation_failed",
                org_id=org_id,
                user_id=user_id,
                error=str(e),
                exc_info=True,
            )
            return 0


# ============================================================================
# Circuit Breaker for Auth-API
# ============================================================================


class CircuitBreaker:
    """Circuit breaker pattern for auth-api resilience.

    States:
        CLOSED: Normal operation, requests go through
        OPEN: Too many failures, skip requests (fail fast)
        HALF_OPEN: Testing if service recovered

    Transition Logic:
        CLOSED → OPEN: After N consecutive failures
        OPEN → HALF_OPEN: After timeout expires
        HALF_OPEN → CLOSED: On successful request
        HALF_OPEN → OPEN: On failed request
    """

    def __init__(self, redis_client: redis.Redis):
        """Initialize circuit breaker.

        Args:
            redis_client: Redis connection for state persistence
        """
        self.redis = redis_client
        self._state_key = "auth:circuit_breaker:state"

    async def _get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state from Redis.

        Returns:
            dict: State with 'state', 'failures', 'opened_at'
        """
        try:
            state_json = await self.redis.get(self._state_key)
            if state_json:
                return json.loads(state_json.decode())
        except Exception:
            pass

        # Default state
        return {
            "state": CircuitBreakerState.CLOSED.value,
            "failures": 0,
            "opened_at": None
        }

    async def _update_state(self, state: Dict[str, Any]) -> None:
        """Update circuit breaker state in Redis.

        Args:
            state: State dictionary
        """
        try:
            await self.redis.setex(
                self._state_key,
                settings.CIRCUIT_BREAKER_TIMEOUT * 2,
                json.dumps(state)
            )
        except Exception as e:
            logger.warning("circuit_breaker_state_update_failed", error=str(e))

    async def should_attempt(self) -> bool:
        """Check if request should be attempted.

        Returns:
            bool: True if request should proceed
        """
        state = await self._get_state()

        if state["state"] == CircuitBreakerState.CLOSED.value:
            return True

        if state["state"] == CircuitBreakerState.OPEN.value:
            # Check if timeout has passed
            if state["opened_at"]:
                opened_at = datetime.fromisoformat(state["opened_at"])
                elapsed = (datetime.utcnow() - opened_at).total_seconds()

                if elapsed > settings.CIRCUIT_BREAKER_TIMEOUT:
                    # Transition to HALF_OPEN
                    state["state"] = CircuitBreakerState.HALF_OPEN.value
                    await self._update_state(state)

                    logger.info("circuit_breaker_half_open", reason="timeout_expired", elapsed_seconds=elapsed)
                    return True

            return False

        # HALF_OPEN - allow one test request
        return True

    async def record_success(self) -> None:
        """Record successful auth-api call."""
        state = await self._get_state()

        if state["state"] != CircuitBreakerState.CLOSED.value:
            logger.info("circuit_breaker_closed", reason="successful_call", previous_state=state["state"])

        state["state"] = CircuitBreakerState.CLOSED.value
        state["failures"] = 0
        state["opened_at"] = None

        await self._update_state(state)

    async def record_failure(self) -> None:
        """Record failed auth-api call."""
        state = await self._get_state()

        state["failures"] += 1

        if state["failures"] >= settings.CIRCUIT_BREAKER_THRESHOLD:
            if state["state"] != CircuitBreakerState.OPEN.value:
                logger.warning(
                    "circuit_breaker_opened",
                    failures=state["failures"],
                    threshold=settings.CIRCUIT_BREAKER_THRESHOLD,
                )

            state["state"] = CircuitBreakerState.OPEN.value
            state["opened_at"] = datetime.utcnow().isoformat()

        await self._update_state(state)

    async def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status for monitoring.

        Returns:
            dict: Current state, failures, opened_at
        """
        return await self._get_state()


# ============================================================================
# Auth-API HTTP Client
# ============================================================================


class AuthAPIClient:
    """HTTP client for auth-api with circuit breaker integration."""

    def __init__(self, circuit_breaker: CircuitBreaker):
        """Initialize auth-api client.

        Args:
            circuit_breaker: Circuit breaker instance
        """
        self.circuit_breaker = circuit_breaker
        self.http_client = httpx.AsyncClient(timeout=settings.AUTH_API_TIMEOUT)

    async def check_permission(
        self,
        org_id: str,
        user_id: str,
        permission: str
    ) -> Optional[PermissionCheckResult]:
        """Check permission via auth-api.

        Args:
            org_id: Organization ID
            user_id: User ID
            permission: Permission string (e.g., "image:upload")

        Returns:
            Optional[PermissionCheckResult]: Result if available, None if unavailable
        """
        # Check circuit breaker
        if not await self.circuit_breaker.should_attempt():
            logger.warning(
                "auth_api_circuit_breaker_open",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
            )
            return None

        try:
            response = await self.http_client.post(
                f"{settings.AUTH_API_URL}/api/v1/authorization/check",
                json={
                    "org_id": org_id,
                    "user_id": user_id,
                    "permission": permission
                }
            )

            if response.status_code == 200:
                # Permission granted
                result = PermissionCheckResult(
                    allowed=True,
                    **response.json()
                )

                await self.circuit_breaker.record_success()

                logger.info(
                    "auth_api_permission_granted",
                    org_id=org_id,
                    user_id=user_id,
                    permission=permission,
                )

                return result

            elif response.status_code == 403:
                # Permission denied (API call succeeded, but permission denied)
                result = PermissionCheckResult(
                    allowed=False,
                    reason=response.json().get("reason", "permission_denied")
                )

                await self.circuit_breaker.record_success()  # API call succeeded

                logger.info(
                    "auth_api_permission_denied",
                    org_id=org_id,
                    user_id=user_id,
                    permission=permission,
                    reason=result.reason,
                )

                return result

            else:
                # API error
                await self.circuit_breaker.record_failure()

                logger.error(
                    "auth_api_error_response",
                    org_id=org_id,
                    user_id=user_id,
                    permission=permission,
                    status_code=response.status_code,
                    response_body=response.text[:200],
                )

                return None

        except httpx.TimeoutException:
            await self.circuit_breaker.record_failure()

            logger.error(
                "auth_api_timeout",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                timeout=settings.AUTH_API_TIMEOUT,
            )

            return None

        except Exception as e:
            await self.circuit_breaker.record_failure()

            logger.error(
                "auth_api_call_failed",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                error_type=type(e).__name__,
                error=str(e),
                exc_info=True,
            )

            return None

    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()


# ============================================================================
# Authorization Service (Main Orchestrator)
# ============================================================================


class AuthorizationService:
    """Complete authorization service with caching and fallback.

    Flow:
        1. Check Redis cache (fast path)
        2. If cache miss, query auth-api
        3. Cache result with appropriate TTL
        4. Apply fallback policy if auth-api unavailable
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        cache: AuthorizationCache,
        circuit_breaker: CircuitBreaker,
        auth_client: AuthAPIClient
    ):
        """Initialize authorization service.

        Args:
            redis_client: Redis connection
            cache: Authorization cache
            circuit_breaker: Circuit breaker
            auth_client: Auth-API client
        """
        self.redis = redis_client
        self.cache = cache
        self.circuit_breaker = circuit_breaker
        self.auth_client = auth_client

    async def check_permission(
        self,
        org_id: str,
        user_id: str,
        permission: str,
        custom_cache_ttl: Optional[int] = None
    ) -> bool:
        """Check if user has permission in organization.

        Args:
            org_id: Organization ID
            user_id: User ID
            permission: Permission string (e.g., "image:upload")
            custom_cache_ttl: Override default cache TTL (optional)

        Returns:
            bool: True if permission granted

        Raises:
            Exception: If permission denied or auth unavailable (fail-closed)
        """
        start_time = datetime.utcnow()

        # Check cache first (fast path)
        cached_result = await self.cache.get(org_id, user_id, permission)

        if cached_result is not None:
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            logger.info(
                "authorization_decision",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                allowed=cached_result,
                source="cache",
                duration_ms=round(duration_ms, 2),
            )

            if not cached_result:
                raise Exception(f"Permission denied: {permission}")

            return True

        # Cache miss - query auth-api
        logger.debug(
            "auth_cache_miss",
            org_id=org_id,
            user_id=user_id,
            permission=permission,
        )

        api_result = await self.auth_client.check_permission(org_id, user_id, permission)

        if api_result is not None:
            # Cache the result
            await self.cache.set(
                org_id, user_id, permission, api_result.allowed, custom_cache_ttl
            )

            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            logger.info(
                "authorization_decision",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                allowed=api_result.allowed,
                source="auth_api",
                duration_ms=round(duration_ms, 2),
            )

            if not api_result.allowed:
                raise Exception(f"Permission denied: {permission}")

            return True

        # Auth-API unavailable - apply fallback policy
        if settings.AUTH_FAIL_OPEN:
            logger.warning(
                "authorization_fail_open",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                reason="auth_api_unavailable",
            )
            return True
        else:
            logger.error(
                "authorization_fail_closed",
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                reason="auth_api_unavailable",
            )

            raise Exception("Authorization service temporarily unavailable")

    async def invalidate_user_cache(self, org_id: str, user_id: str) -> int:
        """Invalidate all cached permissions for user.

        Args:
            org_id: Organization ID
            user_id: User ID

        Returns:
            int: Number of cache entries invalidated
        """
        return await self.cache.invalidate_user(org_id, user_id)

    async def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get circuit breaker status for monitoring.

        Returns:
            dict: Circuit breaker state
        """
        return await self.circuit_breaker.get_status()

    async def close(self):
        """Cleanup resources."""
        await self.auth_client.close()


# ============================================================================
# Global Instances (initialized at startup)
# ============================================================================

_redis_client: Optional[redis.Redis] = None
_authorization_service: Optional[AuthorizationService] = None


async def get_redis_for_auth() -> redis.Redis:
    """Get Redis client for authorization system.

    Reuses existing Redis connection from settings.

    Returns:
        redis.Redis: Redis client
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=False
        )
    return _redis_client


async def get_authorization_service() -> AuthorizationService:
    """Get authorization service instance.

    Singleton pattern - created once at startup.

    Returns:
        AuthorizationService: Service instance
    """
    global _authorization_service
    if _authorization_service is None:
        redis_client = await get_redis_for_auth()
        cache = AuthorizationCache(redis_client)
        circuit_breaker = CircuitBreaker(redis_client)
        auth_client = AuthAPIClient(circuit_breaker)
        _authorization_service = AuthorizationService(
            redis_client, cache, circuit_breaker, auth_client
        )
    return _authorization_service


async def close_authorization_service():
    """Cleanup authorization service resources.

    Call this during application shutdown.
    """
    global _authorization_service, _redis_client

    if _authorization_service:
        await _authorization_service.close()
        _authorization_service = None

    if _redis_client:
        await _redis_client.close()
        _redis_client = None
