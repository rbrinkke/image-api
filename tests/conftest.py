"""
Pytest configuration and shared fixtures for image-api tests.

This module provides:
- Test client fixtures
- Database fixtures
- Storage fixtures
- Authentication fixtures
- Mocking utilities
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Import the FastAPI app
from app.main import app
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_session
from app.storage.local import LocalStorageBackend
from app.api.dependencies import get_processor_service


# ============================================================================
# Session-scoped fixtures
# ============================================================================

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for the test session.

    This is needed for async tests to work properly.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Test environment fixtures
# ============================================================================

@pytest.fixture(scope="function")
def test_env(tmp_path: Path) -> dict:
    """Create isolated test environment with temporary paths.

    Returns:
        dict: Environment configuration with temp paths
    """
    test_db_path = tmp_path / "test.db"
    test_storage_path = tmp_path / "storage"
    test_storage_path.mkdir(parents=True, exist_ok=True)

    # Update settings for test
    settings.DATABASE_PATH = str(test_db_path)
    settings.STORAGE_PATH = str(test_storage_path)
    # Ensure DATABASE_URL is not set to some other value if we rely on path
    if hasattr(settings, 'DATABASE_URL'):
        delattr(settings, 'DATABASE_URL')

    return {
        "db_path": str(test_db_path),
        "storage_path": str(test_storage_path),
        "tmp_path": tmp_path,
    }


# ============================================================================
# Database fixtures
# ============================================================================

@pytest.fixture
async def test_db_session(test_env: dict) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session with schema initialized.

    This creates a fresh database for each test.
    """
    database_url = f"sqlite+aiosqlite:///{test_env['db_path']}"
    engine = create_async_engine(
        database_url,
        connect_args={"check_same_thread": False}
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with SessionLocal() as session:
        yield session

    await engine.dispose()


# ============================================================================
# Storage fixtures
# ============================================================================

@pytest.fixture
def test_storage(test_env: dict) -> LocalStorageBackend:
    """Create a test storage instance with temporary directory.

    Returns:
        LocalStorageBackend: Test storage instance
    """
    return LocalStorageBackend(base_path=test_env["storage_path"])


# ============================================================================
# API Client fixtures
# ============================================================================

@pytest.fixture
def client(test_db_session) -> TestClient:
    """Create a synchronous test client for the FastAPI app.

    Use this for simple, synchronous tests.

    Returns:
        TestClient: Synchronous test client
    """
    # Override dependency
    async def override_get_session():
        yield test_db_session

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
async def async_client(test_db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create an asynchronous test client for the FastAPI app.

    Use this for testing async endpoints and concurrent requests.

    Yields:
        AsyncClient: Asynchronous test client
    """
    # Override dependency
    async def override_get_session():
        yield test_db_session

    app.dependency_overrides[get_session] = override_get_session

    from httpx import ASGITransport
    # AsyncClient(app=...) is deprecated. Use AsyncClient(transport=ASGITransport(app=...))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ============================================================================
# Authentication fixtures
# ============================================================================

@pytest.fixture
def mock_jwt_token() -> str:
    """Generate a mock JWT token for testing.

    Returns:
        str: Mock JWT token
    """
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token"


@pytest.fixture
def auth_headers(mock_jwt_token: str) -> dict:
    """Generate authentication headers for API requests.

    Args:
        mock_jwt_token: Mock JWT token

    Returns:
        dict: Headers with Authorization bearer token
    """
    return {
        "Authorization": f"Bearer {mock_jwt_token}",
    }


@pytest.fixture
def mock_auth_user() -> dict:
    """Mock authenticated user data.

    Returns:
        dict: User data with id, organization_id, and capabilities
    """
    return {
        "user_id": "test-user-123",
        "organization_id": "test-org-456",
        "capabilities": ["image:upload", "image:read", "image:delete"],
    }


# ============================================================================
# Mock fixtures
# ============================================================================

@pytest.fixture
def mock_celery_task() -> MagicMock:
    """Mock Celery task for testing without running actual workers.

    Returns:
        MagicMock: Mocked Celery task
    """
    mock = MagicMock()
    mock.delay.return_value = MagicMock(id="test-task-id")
    return mock


@pytest.fixture
def mock_storage() -> AsyncMock:
    """Mock storage backend for testing without file I/O.

    Returns:
        AsyncMock: Mocked storage backend
    """
    storage = AsyncMock()
    storage.save.return_value = None
    storage.load.return_value = b"fake-image-data"
    storage.delete.return_value = None
    return storage


# ============================================================================
# Test data fixtures
# ============================================================================

@pytest.fixture
def sample_image_bytes() -> bytes:
    """Generate sample image bytes for testing.

    Returns:
        bytes: Minimal valid JPEG image data
    """
    # Minimal valid JPEG (1x1 pixel, red)
    return bytes.fromhex(
        'ffd8ffe000104a46494600010100000100010000ffdb00430003020202020203'
        '020203030304060404040404080606050609080a0a090809090a0c0f0c0a0b'
        '0e0b09090d110d0e0f101011100a0c12131210130f101010ffc90011080001'
        '0001030122000211010311010fffc40015000101000000000000000000000000'
        '0000000001ffda000c03010002110311003f00bf800000ffd9'
    )


@pytest.fixture
def sample_upload_file(sample_image_bytes: bytes):
    """Create a mock UploadFile for testing.

    Returns:
        Mock UploadFile with image data
    """
    from io import BytesIO
    from unittest.mock import MagicMock

    mock_file = MagicMock()
    mock_file.file = BytesIO(sample_image_bytes)
    mock_file.filename = "test-image.jpg"
    mock_file.content_type = "image/jpeg"

    # Make the file seekable
    async def async_seek(position: int):
        mock_file.file.seek(position)

    mock_file.seek = async_seek

    return mock_file


# ============================================================================
# Utility functions
# ============================================================================

def assert_valid_uuid(value: str) -> None:
    """Assert that a string is a valid UUID.

    Args:
        value: String to validate

    Raises:
        AssertionError: If value is not a valid UUID
    """
    from uuid import UUID
    try:
        UUID(value)
    except (ValueError, AttributeError):
        pytest.fail(f"'{value}' is not a valid UUID")


def assert_iso_timestamp(value: str) -> None:
    """Assert that a string is a valid ISO 8601 timestamp.

    Args:
        value: String to validate

    Raises:
        AssertionError: If value is not a valid ISO timestamp
    """
    from datetime import datetime
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        pytest.fail(f"'{value}' is not a valid ISO 8601 timestamp")
