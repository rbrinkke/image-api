"""Distributed authorization system with auth-api integration.

This module implements a robust authorization system that:
1. Validates bucket structure (org-{org_id}/groups/{group_id}/ format)
2. Calls auth-api to check group membership and permissions
3. Caches authorization decisions in Redis
4. Protects auth-api with circuit breaker (fail-closed)

Architecture:
- BucketValidator: Parse and validate bucket structure
- AuthAPIClient: HTTP client for auth-api calls
- CircuitBreaker: Fail-closed protection for auth-api
- AuthorizationCache: Redis-based caching of auth decisions
- AuthorizationService: Orchestrates all components
"""

import re
import httpx
import redis.asyncio as redis
from typing import Optional, Tuple, Literal
from dataclasses import dataclass
from datetime import datetime, timedelta
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.logging_config import get_logger


logger = get_logger(__name__)


# ============================================================================
# Data Models
# ============================================================================


BucketType = Literal["group", "user", "system"]


@dataclass
class BucketInfo:
    """Parsed bucket information."""
    bucket_type: BucketType
    org_id: str
    resource_id: Optional[str] = None  # group_id or user_id (None for system)
    original_bucket: str = ""


@dataclass
class AuthContext:
    """Authentication context from JWT token."""
    user_id: str
    org_id: str
    permissions: list[str] = None

    def __post_init__(self):
        if self.permissions is None:
            self.permissions = []


# ============================================================================
# Bucket Validator
# ============================================================================


class BucketValidator:
    """Validates and parses bucket structure.

    Required formats:
    - Group: org-{org_id}/groups/{group_id}/
    - User: org-{org_id}/users/{user_id}/
    - System: org-{org_id}/system/

    Examples:
        >>> validator = BucketValidator()
        >>> info = validator.parse("org-abc123/groups/xyz789/")
        >>> print(info.bucket_type)  # "group"
        >>> print(info.org_id)       # "abc123"
        >>> print(info.resource_id)  # "xyz789"
    """

    # Regex patterns for bucket validation
    # With org prefix (multi-tenant apps)
    GROUP_PATTERN = re.compile(r'^org-([a-zA-Z0-9\-_]+)/groups/([a-zA-Z0-9\-_]+)/?$')
    USER_PATTERN = re.compile(r'^org-([a-zA-Z0-9\-_]+)/users/([a-zA-Z0-9\-_]+)/?$')
    SYSTEM_PATTERN = re.compile(r'^org-([a-zA-Z0-9\-_]+)/system/?$')

    # Without org prefix (single-tenant apps or apps without org concept)
    GROUP_PATTERN_SIMPLE = re.compile(r'^groups/([a-zA-Z0-9\-_]+)/?$')
    USER_PATTERN_SIMPLE = re.compile(r'^users/([a-zA-Z0-9\-_]+)/?$')
    SYSTEM_PATTERN_SIMPLE = re.compile(r'^system/?$')

    def parse(self, bucket: str) -> BucketInfo:
        """Parse and validate bucket string.

        Args:
            bucket: Bucket identifier string

        Returns:
            BucketInfo: Parsed bucket information

        Raises:
            HTTPException: 400 Bad Request if bucket format is invalid
        """
        if not bucket or not isinstance(bucket, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bucket must be a non-empty string"
            )

        # Try group pattern (with org prefix)
        match = self.GROUP_PATTERN.match(bucket)
        if match:
            return BucketInfo(
                bucket_type="group",
                org_id=match.group(1),
                resource_id=match.group(2),
                original_bucket=bucket
            )

        # Try user pattern (with org prefix)
        match = self.USER_PATTERN.match(bucket)
        if match:
            return BucketInfo(
                bucket_type="user",
                org_id=match.group(1),
                resource_id=match.group(2),
                original_bucket=bucket
            )

        # Try system pattern (with org prefix)
        match = self.SYSTEM_PATTERN.match(bucket)
        if match:
            return BucketInfo(
                bucket_type="system",
                org_id=match.group(1),
                resource_id=None,
                original_bucket=bucket
            )

        # Try simple group pattern (without org prefix)
        match = self.GROUP_PATTERN_SIMPLE.match(bucket)
        if match:
            return BucketInfo(
                bucket_type="group",
                org_id=None,  # No org concept
                resource_id=match.group(1),
                original_bucket=bucket
            )

        # Try simple user pattern (without org prefix)
        match = self.USER_PATTERN_SIMPLE.match(bucket)
        if match:
            return BucketInfo(
                bucket_type="user",
                org_id=None,  # No org concept
                resource_id=match.group(1),
                original_bucket=bucket
            )

        # Try simple system pattern (without org prefix)
        match = self.SYSTEM_PATTERN_SIMPLE.match(bucket)
        if match:
            return BucketInfo(
                bucket_type="system",
                org_id=None,  # No org concept
                resource_id=None,
                original_bucket=bucket
            )

        # Invalid format
        if settings.BUCKET_VALIDATION_STRICT:
            logger.warning(
                "invalid_bucket_format",
                bucket=bucket,
                expected_formats=[
                    "org-{org_id}/groups/{group_id}/",
                    "org-{org_id}/users/{user_id}/",
                    "org-{org_id}/system/",
                    "groups/{group_id}/",
                    "users/{user_id}/",
                    "system/"
                ]
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Invalid bucket format. Expected: "
                    "org-{org_id}/groups/{group_id}/, "
                    "org-{org_id}/users/{user_id}/, "
                    "org-{org_id}/system/, "
                    "groups/{group_id}/, "
                    "users/{user_id}/, or "
                    "system/"
                )
            )

        # Fallback for non-strict mode (backward compatibility)
        return BucketInfo(
            bucket_type="system",
            org_id="default-org",
            resource_id=None,
            original_bucket=bucket
        )


# ============================================================================
# Auth API Client
# ============================================================================


class AuthAPIClient:
    """HTTP client for auth-api authorization checks.

    Calls the auth-api to verify user permissions and group memberships.

    Example:
        >>> client = AuthAPIClient()
        >>> allowed = await client.check_permission(
        ...     org_id="abc123",
        ...     user_id="user-xyz",
        ...     permission="image:upload:group:xyz789"
        ... )
    """

    def __init__(self):
        self.base_url = settings.AUTH_API_URL
        self.timeout = settings.AUTH_API_TIMEOUT
        self.check_endpoint = settings.AUTH_API_CHECK_ENDPOINT

    async def check_permission(
        self,
        org_id: str,
        user_id: str,
        permission: str
    ) -> bool:
        """Check if user has permission via auth-api.

        Args:
            org_id: Organization ID
            user_id: User ID
            permission: Permission string (e.g., "image:upload:group:xyz")

        Returns:
            bool: True if permission granted, False if denied

        Raises:
            HTTPException: 503 if auth-api is unreachable or returns error
        """
        url = f"{self.base_url}{self.check_endpoint}"
        payload = {
            "org_id": org_id,
            "user_id": user_id,
            "permission": permission
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.debug(
                    "auth_api_request",
                    url=url,
                    org_id=org_id,
                    user_id=user_id,
                    permission=permission
                )

                response = await client.post(url, json=payload)

                # 200: Permission granted
                if response.status_code == 200:
                    logger.debug(
                        "auth_api_allowed",
                        org_id=org_id,
                        user_id=user_id,
                        permission=permission
                    )
                    return True

                # 403: Permission denied
                if response.status_code == 403:
                    logger.info(
                        "auth_api_denied",
                        org_id=org_id,
                        user_id=user_id,
                        permission=permission
                    )
                    return False

                # Other errors
                logger.error(
                    "auth_api_error",
                    status_code=response.status_code,
                    response=response.text[:200],
                    org_id=org_id,
                    user_id=user_id,
                    permission=permission
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authorization service unavailable"
                )

        except httpx.TimeoutException as e:
            logger.error(
                "auth_api_timeout",
                timeout=self.timeout,
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                error=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authorization service timeout"
            )
        except httpx.RequestError as e:
            logger.error(
                "auth_api_request_error",
                url=url,
                org_id=org_id,
                user_id=user_id,
                permission=permission,
                error=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authorization service unreachable"
            )


# ============================================================================
# Circuit Breaker
# ============================================================================


class CircuitBreaker:
    """Circuit breaker for auth-api with Redis state management.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, all requests blocked
    - HALF_OPEN: Testing if service recovered (not implemented yet)

    Fail-closed behavior: When open, deny all authorization requests.

    Example:
        >>> breaker = CircuitBreaker(redis_client)
        >>> async with breaker.call():
        ...     result = await auth_api_client.check_permission(...)
    """

    REDIS_KEY_STATE = "auth:circuit_breaker:state"
    REDIS_KEY_FAILURES = "auth:circuit_breaker:failures"
    REDIS_KEY_OPENED_AT = "auth:circuit_breaker:opened_at"

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.threshold = settings.CIRCUIT_BREAKER_THRESHOLD
        self.timeout = settings.CIRCUIT_BREAKER_TIMEOUT
        self.enabled = settings.CIRCUIT_BREAKER_ENABLED

    async def is_open(self) -> bool:
        """Check if circuit breaker is open (blocking requests).

        Returns:
            bool: True if circuit is open and blocking
        """
        if not self.enabled:
            return False

        state = await self.redis.get(self.REDIS_KEY_STATE)
        if state != b"OPEN":
            return False

        # Check if timeout has expired
        opened_at = await self.redis.get(self.REDIS_KEY_OPENED_AT)
        if opened_at:
            opened_time = datetime.fromisoformat(opened_at.decode())
            if datetime.utcnow() - opened_time > timedelta(seconds=self.timeout):
                # Timeout expired, close circuit
                await self.reset()
                logger.info("circuit_breaker_auto_reset", timeout=self.timeout)
                return False

        return True

    async def record_success(self):
        """Record successful call, reset failure counter."""
        if not self.enabled:
            return

        await self.redis.delete(self.REDIS_KEY_FAILURES)
        logger.debug("circuit_breaker_success")

    async def record_failure(self):
        """Record failed call, open circuit if threshold exceeded."""
        if not self.enabled:
            return

        failures = await self.redis.incr(self.REDIS_KEY_FAILURES)
        logger.warning("circuit_breaker_failure", failures=failures, threshold=self.threshold)

        if failures >= self.threshold:
            await self.open()

    async def open(self):
        """Open circuit breaker (block all requests)."""
        await self.redis.set(self.REDIS_KEY_STATE, "OPEN")
        await self.redis.set(
            self.REDIS_KEY_OPENED_AT,
            datetime.utcnow().isoformat()
        )
        logger.error(
            "circuit_breaker_opened",
            threshold=self.threshold,
            timeout=self.timeout,
            behavior="fail_closed"
        )

    async def reset(self):
        """Reset circuit breaker to closed state."""
        await self.redis.delete(self.REDIS_KEY_STATE)
        await self.redis.delete(self.REDIS_KEY_FAILURES)
        await self.redis.delete(self.REDIS_KEY_OPENED_AT)
        logger.info("circuit_breaker_reset")

    async def execute(self, func):
        """Execute function with circuit breaker protection.

        Args:
            func: Async function to execute

        Returns:
            Result of function call

        Raises:
            HTTPException: 503 if circuit is open or service fails
        """
        # Check if circuit is open
        if await self.is_open():
            logger.warning(
                "circuit_breaker_blocked",
                state="OPEN",
                behavior="fail_closed"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authorization service temporarily unavailable"
            )

        # Try to execute
        try:
            result = await func()
            await self.record_success()
            return result
        except HTTPException as e:
            # Record failure for 5xx errors (service errors)
            if e.status_code >= 500:
                await self.record_failure()
            raise
        except Exception as e:
            # Unexpected error - record failure and convert to 503
            logger.error(
                "circuit_breaker_unexpected_error",
                error_type=type(e).__name__,
                error=str(e),
                exc_info=True
            )
            await self.record_failure()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authorization service error"
            )


# ============================================================================
# Authorization Cache
# ============================================================================


class AuthorizationCache:
    """Redis-based cache for authorization decisions.

    Cache keys: auth:permission:{org_id}:{user_id}:{permission}
    Cache values: "1" (allowed) or "0" (denied)
    TTL: Configurable per outcome (allowed vs denied)

    Example:
        >>> cache = AuthorizationCache(redis_client)
        >>> await cache.set("org-abc", "user-xyz", "image:upload", True)
        >>> allowed = await cache.get("org-abc", "user-xyz", "image:upload")
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.enabled = settings.AUTH_CACHE_ENABLED
        self.ttl_allowed = settings.AUTH_CACHE_TTL_ALLOWED
        self.ttl_denied = settings.AUTH_CACHE_TTL_DENIED

    def _make_key(self, org_id: str, user_id: str, permission: str) -> str:
        """Generate cache key."""
        return f"auth:permission:{org_id}:{user_id}:{permission}"

    async def get(
        self,
        org_id: str,
        user_id: str,
        permission: str
    ) -> Optional[bool]:
        """Get cached authorization decision.

        Args:
            org_id: Organization ID
            user_id: User ID
            permission: Permission string

        Returns:
            Optional[bool]: True if allowed, False if denied, None if cache miss
        """
        if not self.enabled:
            return None

        key = self._make_key(org_id, user_id, permission)
        value = await self.redis.get(key)

        if value is None:
            logger.debug("auth_cache_miss", key=key)
            return None

        allowed = value == b"1"
        logger.debug("auth_cache_hit", key=key, allowed=allowed)
        return allowed

    async def set(
        self,
        org_id: str,
        user_id: str,
        permission: str,
        allowed: bool
    ):
        """Cache authorization decision.

        Args:
            org_id: Organization ID
            user_id: User ID
            permission: Permission string
            allowed: Authorization decision
        """
        if not self.enabled:
            return

        key = self._make_key(org_id, user_id, permission)
        value = "1" if allowed else "0"
        ttl = self.ttl_allowed if allowed else self.ttl_denied

        await self.redis.setex(key, ttl, value)
        logger.debug(
            "auth_cache_set",
            key=key,
            allowed=allowed,
            ttl=ttl
        )

    async def invalidate(
        self,
        org_id: str,
        user_id: str,
        permission: str
    ):
        """Invalidate cached authorization decision.

        Args:
            org_id: Organization ID
            user_id: User ID
            permission: Permission string
        """
        if not self.enabled:
            return

        key = self._make_key(org_id, user_id, permission)
        await self.redis.delete(key)
        logger.debug("auth_cache_invalidate", key=key)


# ============================================================================
# Authorization Service (Orchestrator)
# ============================================================================


class AuthorizationService:
    """Main authorization service orchestrating all components.

    This service:
    1. Validates bucket structure
    2. Checks org_id match
    3. Determines required permission based on bucket type
    4. Checks cache
    5. Calls auth-api (with circuit breaker protection)
    6. Caches result

    Example:
        >>> service = AuthorizationService(redis_client)
        >>> allowed = await service.check_access(
        ...     auth_context=auth,
        ...     permission="image:upload",
        ...     bucket="org-abc123/groups/xyz789/"
        ... )
    """

    def __init__(self, redis_client: redis.Redis):
        self.validator = BucketValidator()
        self.auth_client = AuthAPIClient()
        self.circuit_breaker = CircuitBreaker(redis_client)
        self.cache = AuthorizationCache(redis_client)

    async def check_access(
        self,
        auth_context: AuthContext,
        permission: str,
        bucket: str
    ) -> bool:
        """Check if user has access to perform operation on bucket.

        Args:
            auth_context: Authenticated user context from JWT
            permission: Base permission (e.g., "image:upload")
            bucket: Bucket identifier

        Returns:
            bool: True if access allowed, False otherwise

        Raises:
            HTTPException: 400 for invalid bucket, 403 for denied access, 503 for auth-api issues
        """
        # Parse and validate bucket
        bucket_info = self.validator.parse(bucket)

        # Validate org_id match (only if both have org_id)
        if bucket_info.org_id is not None and auth_context.org_id is not None:
            if bucket_info.org_id != auth_context.org_id:
                logger.warning(
                    "org_mismatch",
                    token_org_id=auth_context.org_id,
                    bucket_org_id=bucket_info.org_id,
                    user_id=auth_context.user_id,
                    bucket=bucket
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Organization ID mismatch"
                )

        # Determine required permission based on bucket type
        required_permission = self._build_permission(
            permission,
            bucket_info
        )

        # Special case: user bucket - check if user owns the bucket
        if bucket_info.bucket_type == "user":
            if bucket_info.resource_id == auth_context.user_id:
                logger.debug(
                    "user_bucket_access_granted",
                    user_id=auth_context.user_id,
                    bucket=bucket
                )
                return True
            else:
                logger.warning(
                    "user_bucket_access_denied",
                    user_id=auth_context.user_id,
                    bucket_user_id=bucket_info.resource_id,
                    bucket=bucket
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot access another user's bucket"
                )

        # Special case: system bucket - allow all authenticated users
        if bucket_info.bucket_type == "system":
            logger.debug(
                "system_bucket_access_granted",
                user_id=auth_context.user_id,
                bucket=bucket
            )
            return True

        # Group bucket - requires auth-api check
        return await self._check_group_permission(
            auth_context,
            required_permission
        )

    def _build_permission(
        self,
        base_permission: str,
        bucket_info: BucketInfo
    ) -> str:
        """Build permission string based on bucket type.

        Args:
            base_permission: Base permission (e.g., "image:upload")
            bucket_info: Parsed bucket information

        Returns:
            str: Full permission string

        Examples:
            - Group bucket: "image:upload" -> "image:upload:group:{group_id}"
            - User bucket: "image:upload" -> "image:upload:user:{user_id}"
            - System bucket: "image:upload" -> "image:upload:system"
        """
        if bucket_info.bucket_type == "group":
            return f"{base_permission}:group:{bucket_info.resource_id}"
        elif bucket_info.bucket_type == "user":
            return f"{base_permission}:user:{bucket_info.resource_id}"
        else:  # system
            return f"{base_permission}:system"

    async def _check_group_permission(
        self,
        auth_context: AuthContext,
        permission: str
    ) -> bool:
        """Check group permission via cache and auth-api.

        Args:
            auth_context: Authenticated user context
            permission: Full permission string

        Returns:
            bool: True if allowed

        Raises:
            HTTPException: 403 if denied, 503 if auth-api unavailable
        """
        # Check cache first
        cached = await self.cache.get(
            auth_context.org_id,
            auth_context.user_id,
            permission
        )

        if cached is not None:
            if not cached:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permission denied (cached)"
                )
            return True

        # Cache miss - call auth-api with circuit breaker protection
        async def _check():
            return await self.auth_client.check_permission(
                org_id=auth_context.org_id,
                user_id=auth_context.user_id,
                permission=permission
            )

        try:
            allowed = await self.circuit_breaker.execute(_check)
        except HTTPException:
            # Circuit breaker open or auth-api error
            # Fail-closed: deny access
            raise

        # Cache result
        await self.cache.set(
            auth_context.org_id,
            auth_context.user_id,
            permission,
            allowed
        )

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied"
            )

        return True


# ============================================================================
# Dependency Injection Helpers & Singleton Pattern
# ============================================================================


# Global Redis client pool (singleton)
_redis_pool: Optional[redis.Redis] = None


async def get_redis_pool() -> redis.Redis:
    """Get or create singleton Redis connection pool.

    This function ensures only one Redis connection pool exists for the entire
    application lifecycle, preventing memory leaks and connection exhaustion.

    Returns:
        redis.Redis: Shared async Redis client with connection pooling
    """
    global _redis_pool

    if _redis_pool is None:
        logger.info(
            "initializing_redis_pool",
            redis_url=settings.REDIS_URL,
            max_connections=10
        )
        _redis_pool = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=False,
            max_connections=10,  # Connection pool size
            socket_keepalive=True,
            socket_connect_timeout=5,
            retry_on_timeout=True
        )

    return _redis_pool


async def get_authorization_service() -> AuthorizationService:
    """Get authorization service instance with shared Redis pool.

    Returns:
        AuthorizationService: Configured authorization service

    Note:
        The Redis client is shared across all requests via connection pooling.
        This prevents memory leaks and connection exhaustion.
    """
    redis_pool = await get_redis_pool()
    return AuthorizationService(redis_pool)
