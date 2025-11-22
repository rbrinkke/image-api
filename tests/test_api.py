"""
API endpoint tests for image-api.

Tests the HTTP layer including:
- Request validation
- Response formatting
- Error handling
- Authentication
- Rate limiting
"""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock

from tests.conftest import assert_valid_uuid, assert_iso_timestamp


# ============================================================================
# Health check tests
# ============================================================================

@pytest.mark.unit
def test_health_check(client: TestClient):
    """Test health check endpoint returns 200 OK."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "timestamp" in data
    assert_iso_timestamp(data["timestamp"])


# ============================================================================
# Configuration endpoint tests
# ============================================================================

@pytest.mark.unit
def test_get_config(client: TestClient):
    """Test configuration endpoint returns server configuration."""
    response = client.get("/info")
    assert response.status_code == 200
    data = response.json()

    # Verify structure
    assert "service" in data
    assert "storage" in data
    assert "processing" in data
    assert "limits" in data

    # Verify processing config contains new ImageSizesConfig
    processing = data["processing"]
    assert "image_sizes" in processing
    image_sizes = processing["image_sizes"]

    # Verify type-safe image sizes are properly serialized
    assert "thumbnail" in image_sizes
    assert "medium" in image_sizes
    assert "large" in image_sizes
    assert "original" in image_sizes

    # Verify dimensions are integers
    assert isinstance(image_sizes["thumbnail"], int)
    assert image_sizes["thumbnail"] == 150
    assert image_sizes["medium"] == 600
    assert image_sizes["large"] == 1200
    assert image_sizes["original"] == 4096


# ============================================================================
# Image upload tests (mocked)
# ============================================================================

@pytest.mark.api
@pytest.mark.asyncio
async def test_upload_image_success(
    async_client: AsyncClient,
    auth_headers: dict,
    sample_image_bytes: bytes,
):
    """Test successful image upload flow (mocked)."""

    # Patch jose.jwt.decode GLOBALLY for this test because middleware imports it locally
    # but refers to the same module object.

    with patch("jose.jwt.decode") as mock_decode, \
         patch("app.services.image_service.ImageService.process_new_upload") as mock_process, \
         patch("app.core.authorization.AuthorizationService.check_access") as mock_check:

        mock_decode.return_value = {
            "sub": "test-user-123",
            "org_id": "test-org-456",
            "permissions": ["image:upload"],
            "aud": "image-api"
        }

        mock_process.return_value = {
            "job_id": "test-job-id",
            "image_id": "test-image-id",
            "status": "pending",
            "status_url": "/api/v1/images/jobs/test-job-id",
        }

        mock_check.return_value = True

        # Override rate limit dependency
        from app.main import app
        from app.api.dependencies import check_rate_limit
        async def override_rate_limit():
            return {"remaining": 50, "reset_at": "2025-01-01T00:00:00"}
        app.dependency_overrides[check_rate_limit] = override_rate_limit

        files = {"file": ("test.jpg", sample_image_bytes, "image/jpeg")}
        data = {"bucket": "system"}

        response = await async_client.post(
            "/api/v1/images/upload",
            files=files,
            data=data,
            headers=auth_headers,
        )

        app.dependency_overrides.clear()

        if response.status_code == 401:
            print("DEBUG 401 Response:", response.json())

        assert response.status_code == 202
        result = response.json()

        assert result["job_id"] == "test-job-id"
        assert result["image_id"] == "test-image-id"
        assert result["status_url"] == "/api/v1/images/jobs/test-job-id"


@pytest.mark.api
def test_upload_missing_file(client: TestClient, auth_headers: dict):
    """Test upload endpoint rejects requests without file."""
    # Patch jose.jwt.decode
    with patch("jose.jwt.decode") as mock_decode:

        mock_decode.return_value = {
            "sub": "test-user-123",
            "org_id": "test-org-456",
            "permissions": ["image:upload"],
            "aud": "image-api"
        }

        response = client.post(
            "/api/v1/images/upload",
            data={"bucket": "system/"},
            headers=auth_headers,
        )

        assert response.status_code == 422


@pytest.mark.api
def test_upload_missing_auth(client: TestClient, sample_image_bytes: bytes):
    """Test upload endpoint rejects unauthenticated requests."""
    files = {"file": ("test.jpg", sample_image_bytes, "image/jpeg")}
    data = {"bucket": "system/"}

    response = client.post(
        "/api/v1/images/upload",
        files=files,
        data=data,
        # No auth headers
    )

    assert response.status_code in [401, 403]


# ============================================================================
# Job status tests (mocked)
# ============================================================================

@pytest.mark.api
@pytest.mark.asyncio
async def test_get_job_status_success(
    async_client: AsyncClient,
    auth_headers: dict,
):
    """Test getting job status (mocked)."""
    with patch("app.services.processor_service.ProcessorService.get_job") as mock_get_job:
        mock_get_job.return_value = {
            "job_id": "test-job-id",
            "image_id": "test-image-id",
            "status": "completed",
            "storage_bucket": "system",
            "staging_path": None,
            "processed_paths": {},
            "processing_metadata": {},
            "user_id": "user",
            "organization_id": "org",
            "attempt_count": 0,
            "max_retries": 3,
            "last_error": None,
            "created_at": "2025-11-19T12:00:00",
            "started_at": None,
            "completed_at": "2025-11-19T12:05:00"
        }

        response = await async_client.get(
            "/api/v1/images/jobs/test-job-id",
        )

        assert response.status_code == 200
        result = response.json()

        assert result["job_id"] == "test-job-id"
        assert result["status"] == "completed"


@pytest.mark.api
@pytest.mark.asyncio
async def test_get_job_status_not_found(
    async_client: AsyncClient,
    auth_headers: dict,
):
    """Test getting non-existent job returns 404."""
    with patch("app.services.processor_service.ProcessorService.get_job") as mock_get_job:
        mock_get_job.return_value = None

        response = await async_client.get(
            "/api/v1/images/jobs/nonexistent-job",
        )

        assert response.status_code == 404


# ============================================================================
# Metrics endpoint tests
# ============================================================================

@pytest.mark.unit
def test_metrics_endpoint(client: TestClient):
    """Test Prometheus metrics endpoint."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]

    content = response.text
    assert "python_info" in content or "process_virtual_memory_bytes" in content
