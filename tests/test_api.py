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


@pytest.mark.unit
def test_readiness_check(client: TestClient):
    """Test readiness check endpoint."""
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"


# ============================================================================
# Configuration endpoint tests
# ============================================================================

@pytest.mark.unit
def test_get_config(client: TestClient):
    """Test configuration endpoint returns server configuration."""
    response = client.get("/")
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
    # Mock the dependencies to avoid actual processing
    with patch("app.api.v1.images.get_image_service") as mock_service, \
         patch("app.api.v1.images.verify_jwt_token") as mock_verify:

        # Setup mocks
        mock_verify.return_value = {
            "sub": "test-user-123",
            "organization_id": "test-org-456",
        }

        mock_service_instance = AsyncMock()
        mock_service_instance.process_new_upload.return_value = {
            "job_id": "test-job-id",
            "image_id": "test-image-id",
            "status": "pending",
            "status_url": "/api/v1/images/jobs/test-job-id",
        }
        mock_service.return_value = mock_service_instance

        # Make request
        files = {"file": ("test.jpg", sample_image_bytes, "image/jpeg")}
        data = {"bucket": "system/"}

        response = await async_client.post(
            "/api/v1/images/upload",
            files=files,
            data=data,
            headers=auth_headers,
        )

        # Verify response
        assert response.status_code == 202
        result = response.json()

        assert result["job_id"] == "test-job-id"
        assert result["image_id"] == "test-image-id"
        assert result["status"] == "pending"
        assert result["status_url"] == "/api/v1/images/jobs/test-job-id"


@pytest.mark.api
def test_upload_missing_file(client: TestClient, auth_headers: dict):
    """Test upload endpoint rejects requests without file."""
    with patch("app.api.v1.images.verify_jwt_token") as mock_verify:
        mock_verify.return_value = {
            "sub": "test-user-123",
            "organization_id": "test-org-456",
        }

        response = client.post(
            "/api/v1/images/upload",
            data={"bucket": "system/"},
            headers=auth_headers,
        )

        # Should fail with 422 validation error
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

    # Should fail with 401 or 403
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
    with patch("app.api.v1.images.get_image_service") as mock_service, \
         patch("app.api.v1.images.verify_jwt_token") as mock_verify:

        # Setup mocks
        mock_verify.return_value = {
            "sub": "test-user-123",
            "organization_id": "test-org-456",
        }

        mock_service_instance = AsyncMock()
        mock_service_instance.get_job_status.return_value = {
            "job_id": "test-job-id",
            "image_id": "test-image-id",
            "status": "completed",
            "created_at": "2025-11-19T12:00:00",
            "updated_at": "2025-11-19T12:05:00",
            "last_error": None,
        }
        mock_service.return_value = mock_service_instance

        # Make request
        response = await async_client.get(
            "/api/v1/images/jobs/test-job-id",
            headers=auth_headers,
        )

        # Verify response
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
    from app.core.errors import not_found_error, ErrorCode

    with patch("app.api.v1.images.get_image_service") as mock_service, \
         patch("app.api.v1.images.verify_jwt_token") as mock_verify:

        # Setup mocks
        mock_verify.return_value = {
            "sub": "test-user-123",
            "organization_id": "test-org-456",
        }

        mock_service_instance = AsyncMock()
        mock_service_instance.get_job_status.side_effect = not_found_error(
            code=ErrorCode.JOB_NOT_FOUND,
            message="Job not found: nonexistent-job",
            details={"job_id": "nonexistent-job"},
        )
        mock_service.return_value = mock_service_instance

        # Make request
        response = await async_client.get(
            "/api/v1/images/jobs/nonexistent-job",
            headers=auth_headers,
        )

        # Verify response
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

    # Should contain some basic metrics
    content = response.text
    assert "python_info" in content or "process_" in content
