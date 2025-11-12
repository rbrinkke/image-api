"""Pytest configuration and shared fixtures for authorization tests."""

import asyncio
import pytest
import pytest_asyncio
import redis.asyncio as redis
from typing import AsyncGenerator

from app.core.config import settings


# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[redis.Redis, None]:
    """Create Redis client for testing."""
    client = redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=False  # Keep as bytes for compatibility
    )

    try:
        # Clear test keys before test
        keys = []
        async for key in client.scan_iter(match="auth:*"):
            keys.append(key)
        if keys:
            await client.delete(*keys)

        yield client
    finally:
        # Clean up after test
        keys = []
        async for key in client.scan_iter(match="auth:*"):
            keys.append(key)
        if keys:
            await client.delete(*keys)

        await client.aclose()


@pytest.fixture
def sample_jwt_payload():
    """Sample JWT payload for testing."""
    return {
        "sub": "test-user-123",
        "org_id": "test-org-456",
        "email": "test@example.com",
        "name": "Test User"
    }


@pytest.fixture
def sample_auth_context():
    """Sample AuthContext for testing."""
    from app.core.authorization import AuthContext
    return AuthContext(
        user_id="test-user-123",
        org_id="test-org-456",
        email="test@example.com"
    )
