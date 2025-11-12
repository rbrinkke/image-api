"""Unit tests for AuthorizationCache."""

import pytest
import time
from unittest.mock import AsyncMock, patch

from app.core.authorization import AuthorizationCache


@pytest.mark.asyncio
class TestAuthorizationCache:
    """Test AuthorizationCache functionality."""

    async def test_cache_set_and_get_allowed(self, redis_client):
        """Test setting and getting allowed permission."""
        cache = AuthorizationCache(redis_client)

        await cache.set(
            org_id="org-123",
            user_id="user-456",
            permission="image:upload",
            allowed=True,
            custom_ttl=60
        )

        result = await cache.get(
            org_id="org-123",
            user_id="user-456",
            permission="image:upload"
        )

        assert result is True

    async def test_cache_set_and_get_denied(self, redis_client):
        """Test setting and getting denied permission."""
        cache = AuthorizationCache(redis_client)

        await cache.set(
            org_id="org-123",
            user_id="user-456",
            permission="image:delete",
            allowed=False,
            custom_ttl=120
        )

        result = await cache.get(
            org_id="org-123",
            user_id="user-456",
            permission="image:delete"
        )

        assert result is False

    async def test_cache_miss_returns_none(self, redis_client):
        """Test cache miss returns None."""
        cache = AuthorizationCache(redis_client)

        result = await cache.get(
            org_id="org-999",
            user_id="user-999",
            permission="image:upload"
        )

        assert result is None

    async def test_cache_key_isolation_by_org(self, redis_client):
        """Test cache keys are isolated by organization."""
        cache = AuthorizationCache(redis_client)

        # Set permission for org-123
        await cache.set(
            org_id="org-123",
            user_id="user-456",
            permission="image:upload",
            allowed=True,
            custom_ttl=60
        )

        # Same user/permission in different org should be cache miss
        result = await cache.get(
            org_id="org-999",
            user_id="user-456",
            permission="image:upload"
        )

        assert result is None

    async def test_cache_key_isolation_by_user(self, redis_client):
        """Test cache keys are isolated by user."""
        cache = AuthorizationCache(redis_client)

        # Set permission for user-456
        await cache.set(
            org_id="org-123",
            user_id="user-456",
            permission="image:upload",
            allowed=True,
            custom_ttl=60
        )

        # Different user in same org should be cache miss
        result = await cache.get(
            org_id="org-123",
            user_id="user-999",
            permission="image:upload"
        )

        assert result is None

    async def test_cache_key_isolation_by_permission(self, redis_client):
        """Test cache keys are isolated by permission."""
        cache = AuthorizationCache(redis_client)

        # Set image:upload permission
        await cache.set(
            org_id="org-123",
            user_id="user-456",
            permission="image:upload",
            allowed=True,
            custom_ttl=60
        )

        # Different permission should be cache miss
        result = await cache.get(
            org_id="org-123",
            user_id="user-456",
            permission="image:delete"
        )

        assert result is None

    async def test_cache_ttl_expiration(self, redis_client):
        """Test cache entries expire after TTL."""
        cache = AuthorizationCache(redis_client)

        # Set with very short TTL
        await cache.set(
            org_id="org-123",
            user_id="user-456",
            permission="image:upload",
            allowed=True,
            custom_ttl=1
        )

        # Should be in cache immediately
        result = await cache.get(
            org_id="org-123",
            user_id="user-456",
            permission="image:upload"
        )
        assert result is True

        # Wait for expiration
        await asyncio.sleep(2)

        # Should be expired
        result = await cache.get(
            org_id="org-123",
            user_id="user-456",
            permission="image:upload"
        )
        assert result is None

    async def test_cache_delete_permission(self, redis_client):
        """Test invalidating cached permission by deleting cache key manually."""
        cache = AuthorizationCache(redis_client)

        # Set permission
        await cache.set(
            org_id="org-123",
            user_id="user-456",
            permission="image:upload",
            allowed=True,
            custom_ttl=60
        )

        # Verify it's cached
        result = await cache.get(
            org_id="org-123",
            user_id="user-456",
            permission="image:upload"
        )
        assert result is True

        # Delete from cache manually
        key = cache._make_cache_key(
            org_id="org-123",
            user_id="user-456",
            permission="image:upload"
        )
        await redis_client.delete(key)

        # Should be cache miss now
        result = await cache.get(
            org_id="org-123",
            user_id="user-456",
            permission="image:upload"
        )
        assert result is None

    async def test_cache_invalidate_user(self, redis_client):
        """Test invalidating all permissions for a user."""
        cache = AuthorizationCache(redis_client)

        # Set multiple permissions
        await cache.set(
            org_id="org-123",
            user_id="user-456",
            permission="image:upload",
            allowed=True,
            custom_ttl=60
        )
        await cache.set(
            org_id="org-123",
            user_id="user-456",
            permission="image:delete",
            allowed=True,
            custom_ttl=60
        )

        # Invalidate all permissions for user
        await cache.invalidate_user(org_id="org-123", user_id="user-456")

        # Both should be cache miss now
        result1 = await cache.get(
            org_id="org-123",
            user_id="user-456",
            permission="image:upload"
        )
        result2 = await cache.get(
            org_id="org-123",
            user_id="user-456",
            permission="image:delete"
        )

        assert result1 is None
        assert result2 is None

    async def test_get_ttl_for_permission_read(self, redis_client):
        """Test TTL calculation for read permissions."""
        cache = AuthorizationCache(redis_client)

        ttl = cache._get_ttl_for_permission("image:read", allowed=True)
        assert ttl == cache.ttl_read

    async def test_get_ttl_for_permission_write(self, redis_client):
        """Test TTL calculation for write permissions."""
        cache = AuthorizationCache(redis_client)

        ttl = cache._get_ttl_for_permission("image:upload", allowed=True)
        assert ttl == cache.ttl_write

    async def test_get_ttl_for_permission_admin(self, redis_client):
        """Test TTL calculation for admin permissions."""
        cache = AuthorizationCache(redis_client)

        ttl = cache._get_ttl_for_permission("image:admin", allowed=True)
        assert ttl == cache.ttl_admin

    async def test_get_ttl_for_permission_denied(self, redis_client):
        """Test TTL calculation for denied permissions."""
        cache = AuthorizationCache(redis_client)

        ttl = cache._get_ttl_for_permission("image:upload", allowed=False)
        assert ttl == cache.ttl_denied

    async def test_cache_key_format(self, redis_client):
        """Test cache key format is correct."""
        cache = AuthorizationCache(redis_client)

        key = cache._make_cache_key(
            org_id="org-123",
            user_id="user-456",
            permission="image:upload"
        )

        assert key == "auth:permission:org-123:user-456:image:upload"

    async def test_concurrent_cache_operations(self, redis_client):
        """Test concurrent cache operations work correctly."""
        cache = AuthorizationCache(redis_client)

        # Set multiple permissions concurrently
        await asyncio.gather(
            cache.set_permission("org-123", "user-1", "image:upload", True, 60),
            cache.set_permission("org-123", "user-2", "image:upload", True, 60),
            cache.set_permission("org-123", "user-3", "image:upload", True, 60),
        )

        # Get all concurrently
        results = await asyncio.gather(
            cache.get_permission("org-123", "user-1", "image:upload"),
            cache.get_permission("org-123", "user-2", "image:upload"),
            cache.get_permission("org-123", "user-3", "image:upload"),
        )

        assert all(r is True for r in results)


# Add missing import
import asyncio
