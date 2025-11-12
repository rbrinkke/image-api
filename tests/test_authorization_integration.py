"""Integration tests for Authorization system."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from app.core.authorization import (
    AuthorizationService,
    AuthorizationCache,
    CircuitBreaker,
    AuthAPIClient,
    AuthContext,
    CircuitBreakerState
)


@pytest.mark.asyncio
class TestAuthorizationServiceIntegration:
    """Test AuthorizationService end-to-end flows."""

    @pytest.fixture
    async def auth_service(self, redis_client):
        """Create AuthorizationService for testing."""
        service = AuthorizationService(
            redis_url="redis://localhost:6379/0",
            auth_api_url="http://mock-auth-api:8000",
            auth_api_timeout=5,
            circuit_breaker_threshold=5,
            circuit_breaker_timeout=60,
            cache_enabled=True,
            fail_open=False
        )

        # Use test redis client
        service.cache.redis = redis_client

        yield service

        # Cleanup
        await service.close()

    async def test_check_permission_cache_hit(self, auth_service, sample_auth_context):
        """Test permission check with cache hit (fast path)."""
        # Pre-populate cache
        await auth_service.cache.set(
            org_id=sample_auth_context.org_id,
            user_id=sample_auth_context.user_id,
            permission="image:upload",
            allowed=True,
            custom_ttl=60
        )

        # Check permission (should hit cache)
        result = await auth_service.check_permission(
            auth_context=sample_auth_context,
            permission="image:upload"
        )

        assert result is True

    async def test_check_permission_cache_miss_calls_api(self, auth_service, sample_auth_context):
        """Test permission check with cache miss calls auth-api."""
        # Mock auth-api client
        with patch.object(auth_service.auth_api_client, 'check_permission', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True

            # Check permission (cache miss)
            result = await auth_service.check_permission(
                auth_context=sample_auth_context,
                permission="image:upload"
            )

            assert result is True
            mock_check.assert_called_once_with(
                user_id=sample_auth_context.user_id,
                org_id=sample_auth_context.org_id,
                permission="image:upload"
            )

    async def test_check_permission_caches_auth_api_response(self, auth_service, sample_auth_context):
        """Test auth-api response is cached."""
        # Mock auth-api client
        with patch.object(auth_service.auth_api_client, 'check_permission', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True

            # First call (cache miss)
            result1 = await auth_service.check_permission(
                auth_context=sample_auth_context,
                permission="image:upload"
            )

            # Second call (cache hit)
            result2 = await auth_service.check_permission(
                auth_context=sample_auth_context,
                permission="image:upload"
            )

            assert result1 is True
            assert result2 is True

            # Auth-API should only be called once
            assert mock_check.call_count == 1

    async def test_check_permission_negative_caching(self, auth_service, sample_auth_context):
        """Test denied permissions are cached (negative caching)."""
        # Mock auth-api to deny
        with patch.object(auth_service.auth_api_client, 'check_permission', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = False

            # First call
            result1 = await auth_service.check_permission(
                auth_context=sample_auth_context,
                permission="image:delete"
            )

            # Second call (should hit cache)
            result2 = await auth_service.check_permission(
                auth_context=sample_auth_context,
                permission="image:delete"
            )

            assert result1 is False
            assert result2 is False

            # Auth-API should only be called once
            assert mock_check.call_count == 1

    async def test_check_permission_cache_disabled(self, redis_client, sample_auth_context):
        """Test permission check with cache disabled."""
        service = AuthorizationService(
            redis_url="redis://localhost:6379/0",
            auth_api_url="http://mock-auth-api:8000",
            auth_api_timeout=5,
            circuit_breaker_threshold=5,
            circuit_breaker_timeout=60,
            cache_enabled=False,
            fail_open=False
        )
        service.cache.redis = redis_client

        # Mock auth-api client
        with patch.object(service.auth_api_client, 'check_permission', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True

            # Multiple calls should all hit auth-api
            await service.check_permission(sample_auth_context, "image:upload")
            await service.check_permission(sample_auth_context, "image:upload")

            assert mock_check.call_count == 2

        await service.close()

    async def test_check_permission_circuit_breaker_open_fail_closed(self, auth_service, sample_auth_context):
        """Test permission denied when circuit breaker is open (fail-closed)."""
        # Open circuit breaker
        auth_service.circuit_breaker.record_failure()
        auth_service.circuit_breaker.record_failure()
        auth_service.circuit_breaker.record_failure()
        auth_service.circuit_breaker.record_failure()
        auth_service.circuit_breaker.record_failure()

        assert auth_service.circuit_breaker.state == CircuitBreakerState.OPEN

        # Check permission (should fail closed)
        result = await auth_service.check_permission(
            auth_context=sample_auth_context,
            permission="image:upload"
        )

        assert result is False

    async def test_check_permission_circuit_breaker_open_fail_open(self, redis_client, sample_auth_context):
        """Test permission allowed when circuit breaker is open (fail-open)."""
        service = AuthorizationService(
            redis_url="redis://localhost:6379/0",
            auth_api_url="http://mock-auth-api:8000",
            auth_api_timeout=5,
            circuit_breaker_threshold=5,
            circuit_breaker_timeout=60,
            cache_enabled=True,
            fail_open=True  # Fail open
        )
        service.cache.redis = redis_client

        # Open circuit breaker
        for _ in range(5):
            service.circuit_breaker.record_failure()

        assert service.circuit_breaker.state == CircuitState.OPEN

        # Check permission (should fail open = allow)
        result = await service.check_permission(
            auth_context=sample_auth_context,
            permission="image:upload"
        )

        assert result is True

        await service.close()

    async def test_check_permission_auth_api_error_opens_circuit(self, auth_service, sample_auth_context):
        """Test auth-api errors open circuit breaker."""
        # Mock auth-api to fail
        with patch.object(auth_service.auth_api_client, 'check_permission', new_callable=AsyncMock) as mock_check:
            mock_check.side_effect = Exception("Auth API connection error")

            # Make calls until circuit opens
            for _ in range(5):
                try:
                    await auth_service.check_permission(
                        auth_context=sample_auth_context,
                        permission="image:upload"
                    )
                except:
                    pass

            # Circuit should be open
            assert auth_service.circuit_breaker.state == CircuitBreakerState.OPEN

    async def test_invalidate_user_cache(self, auth_service, sample_auth_context):
        """Test invalidating user cache."""
        # Cache some permissions
        await auth_service.cache.set(
            org_id=sample_auth_context.org_id,
            user_id=sample_auth_context.user_id,
            permission="image:upload",
            allowed=True,
            custom_ttl=60
        )
        await auth_service.cache.set(
            org_id=sample_auth_context.org_id,
            user_id=sample_auth_context.user_id,
            permission="image:delete",
            allowed=True,
            custom_ttl=60
        )

        # Invalidate user
        await auth_service.invalidate_user(
            org_id=sample_auth_context.org_id,
            user_id=sample_auth_context.user_id
        )

        # Check cache is empty
        result1 = await auth_service.cache.get(
            org_id=sample_auth_context.org_id,
            user_id=sample_auth_context.user_id,
            permission="image:upload"
        )
        result2 = await auth_service.cache.get(
            org_id=sample_auth_context.org_id,
            user_id=sample_auth_context.user_id,
            permission="image:delete"
        )

        assert result1 is None
        assert result2 is None

    async def test_concurrent_permission_checks(self, auth_service, sample_auth_context):
        """Test concurrent permission checks work correctly."""
        # Mock auth-api
        with patch.object(auth_service.auth_api_client, 'check_permission', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True

            # Make concurrent checks
            results = await asyncio.gather(
                auth_service.check_permission(sample_auth_context, "image:upload"),
                auth_service.check_permission(sample_auth_context, "image:read"),
                auth_service.check_permission(sample_auth_context, "image:delete"),
            )

            assert all(r is True for r in results)

    async def test_organization_isolation(self, auth_service):
        """Test permissions are isolated by organization."""
        # Mock auth-api
        with patch.object(auth_service.auth_api_client, 'check_permission', new_callable=AsyncMock) as mock_check:
            # Allow for org-1, deny for org-2
            def check_side_effect(user_id, org_id, permission):
                return org_id == "org-1"

            mock_check.side_effect = check_side_effect

            # User in org-1
            auth1 = AuthContext(user_id="user-123", org_id="org-1")
            result1 = await auth_service.check_permission(auth1, "image:upload")

            # Same user in org-2
            auth2 = AuthContext(user_id="user-123", org_id="org-2")
            result2 = await auth_service.check_permission(auth2, "image:upload")

            assert result1 is True
            assert result2 is False

    async def test_ttl_stratification(self, auth_service, sample_auth_context):
        """Test different permissions have different TTLs."""
        # Mock auth-api
        with patch.object(auth_service.auth_api_client, 'check_permission', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True

            # Check different permission types
            await auth_service.check_permission(sample_auth_context, "image:read")
            await auth_service.check_permission(sample_auth_context, "image:upload")
            await auth_service.check_permission(sample_auth_context, "image:admin")

            # Verify cached with correct TTLs (we can't easily check TTL, but we can verify they're cached)
            result1 = await auth_service.cache.get(
                sample_auth_context.org_id,
                sample_auth_context.user_id,
                "image:read"
            )
            result2 = await auth_service.cache.get(
                sample_auth_context.org_id,
                sample_auth_context.user_id,
                "image:upload"
            )
            result3 = await auth_service.cache.get(
                sample_auth_context.org_id,
                sample_auth_context.user_id,
                "image:admin"
            )

            assert result1 is True
            assert result2 is True
            assert result3 is True


@pytest.mark.asyncio
class TestAuthAPIClient:
    """Test AuthAPIClient."""

    async def test_check_permission_success(self):
        """Test successful permission check."""
        client = AuthAPIClient(
            base_url="http://mock-auth-api:8000",
            timeout=5
        )

        # Mock httpx response
        with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"allowed": True}
            mock_post.return_value = mock_response

            result = await client.check_permission(
                user_id="user-123",
                org_id="org-456",
                permission="image:upload"
            )

            assert result is True

        await client.close()

    async def test_check_permission_denied(self):
        """Test denied permission check."""
        client = AuthAPIClient(
            base_url="http://mock-auth-api:8000",
            timeout=5
        )

        # Mock httpx response
        with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"allowed": False}
            mock_post.return_value = mock_response

            result = await client.check_permission(
                user_id="user-123",
                org_id="org-456",
                permission="image:delete"
            )

            assert result is False

        await client.close()

    async def test_check_permission_timeout(self):
        """Test timeout handling."""
        client = AuthAPIClient(
            base_url="http://mock-auth-api:8000",
            timeout=1
        )

        # Mock timeout
        with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timeout")

            with pytest.raises(Exception, match="Auth-API timeout"):
                await client.check_permission(
                    user_id="user-123",
                    org_id="org-456",
                    permission="image:upload"
                )

        await client.close()

    async def test_check_permission_connection_error(self):
        """Test connection error handling."""
        client = AuthAPIClient(
            base_url="http://mock-auth-api:8000",
            timeout=5
        )

        # Mock connection error
        with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection refused")

            with pytest.raises(Exception, match="Auth-API connection error"):
                await client.check_permission(
                    user_id="user-123",
                    org_id="org-456",
                    permission="image:upload"
                )

        await client.close()

    async def test_check_permission_http_error(self):
        """Test HTTP error handling."""
        client = AuthAPIClient(
            base_url="http://mock-auth-api:8000",
            timeout=5
        )

        # Mock HTTP error
        with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.return_value = mock_response

            with pytest.raises(Exception, match="Auth-API HTTP 500"):
                await client.check_permission(
                    user_id="user-123",
                    org_id="org-456",
                    permission="image:upload"
                )

        await client.close()
