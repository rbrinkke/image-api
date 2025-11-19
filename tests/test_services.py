"""
Service layer tests for image-api.

Tests business logic in the service layer without HTTP concerns.
This demonstrates the testability benefits of the service layer pattern.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.image_service import ImageService
from app.core.errors import ServiceError, ErrorCode


# ============================================================================
# ImageService tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_new_upload_success(
    test_db,
    test_storage,
    sample_upload_file,
):
    """Test successful image upload processing."""
    # Arrange
    service = ImageService(db=test_db, storage=test_storage)

    # Mock Celery task
    with patch("app.services.image_service.process_image_task") as mock_task:
        mock_task.delay.return_value = MagicMock(id="celery-task-id")

        # Act
        result = await service.process_new_upload(
            file=sample_upload_file,
            bucket="test-bucket",
            auth_user_id="user-123",
            auth_org_id="org-456",
            metadata_json='{"source": "test"}',
            content_length=1024,
            detected_mime="image/jpeg",
        )

        # Assert
        assert "job_id" in result
        assert "image_id" in result
        assert result["status"] == "pending"
        assert "status_url" in result

        # Verify task was queued
        mock_task.delay.assert_called_once()

        # Verify job was created in database
        job = await test_db.get_job(result["job_id"])
        assert job is not None
        assert job["status"] == "pending"
        assert job["user_id"] == "user-123"
        assert job["organization_id"] == "org-456"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_new_upload_invalid_metadata(
    test_db,
    test_storage,
    sample_upload_file,
):
    """Test that invalid JSON metadata is handled gracefully."""
    # Arrange
    service = ImageService(db=test_db, storage=test_storage)

    # Mock Celery task
    with patch("app.services.image_service.process_image_task") as mock_task:
        mock_task.delay.return_value = MagicMock(id="celery-task-id")

        # Act - Pass invalid JSON
        result = await service.process_new_upload(
            file=sample_upload_file,
            bucket="test-bucket",
            auth_user_id="user-123",
            auth_org_id="org-456",
            metadata_json='{"invalid": json}',  # Invalid JSON
            content_length=1024,
            detected_mime="image/jpeg",
        )

        # Assert - Should succeed with empty metadata (graceful degradation)
        assert "job_id" in result
        assert result["status"] == "pending"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_new_upload_storage_failure(
    test_db,
    sample_upload_file,
):
    """Test rollback when storage save fails."""
    # Arrange
    mock_storage = AsyncMock()
    mock_storage.save.side_effect = Exception("Storage unavailable")

    service = ImageService(db=test_db, storage=mock_storage)

    # Act & Assert
    with pytest.raises(ServiceError) as exc_info:
        await service.process_new_upload(
            file=sample_upload_file,
            bucket="test-bucket",
            auth_user_id="user-123",
            auth_org_id="org-456",
            metadata_json="{}",
            content_length=1024,
            detected_mime="image/jpeg",
        )

    # Verify error details
    error = exc_info.value
    assert error.code == ErrorCode.STAGING_FAILED
    assert "staging storage" in error.message.lower()

    # Verify job was marked as failed (rollback)
    job_id = error.details["job_id"]
    job = await test_db.get_job(job_id)
    assert job is not None
    assert job["status"] == "failed"
    assert "Storage save failed" in job["last_error"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_new_upload_queue_failure(
    test_db,
    test_storage,
    sample_upload_file,
):
    """Test rollback when task queue fails."""
    # Arrange
    service = ImageService(db=test_db, storage=test_storage)

    # Mock Celery task to fail
    with patch("app.services.image_service.process_image_task") as mock_task:
        mock_task.delay.side_effect = Exception("Celery unavailable")

        # Act & Assert
        with pytest.raises(ServiceError) as exc_info:
            await service.process_new_upload(
                file=sample_upload_file,
                bucket="test-bucket",
                auth_user_id="user-123",
                auth_org_id="org-456",
                metadata_json="{}",
                content_length=1024,
                detected_mime="image/jpeg",
            )

        # Verify error details
        error = exc_info.value
        assert error.code == ErrorCode.TASK_QUEUE_FAILED
        assert "queue" in error.message.lower()

        # Verify job was marked as failed (rollback)
        job_id = error.details["job_id"]
        job = await test_db.get_job(job_id)
        assert job is not None
        assert job["status"] == "failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_job_status_success(test_db):
    """Test retrieving job status."""
    # Arrange
    service = ImageService(db=test_db, storage=AsyncMock())

    # Create a job
    job_id = str(uuid4())
    await test_db.create_job(
        job_id=job_id,
        image_id=str(uuid4()),
        storage_bucket="test-bucket",
        staging_path="staging/test.jpg",
        metadata={"test": "data"},
        user_id="user-123",
        organization_id="org-456",
    )

    # Act
    result = await service.get_job_status(job_id)

    # Assert
    assert result["job_id"] == job_id
    assert result["status"] == "pending"
    assert "created_at" in result
    assert "updated_at" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_job_status_not_found(test_db):
    """Test retrieving non-existent job raises ServiceError."""
    # Arrange
    service = ImageService(db=test_db, storage=AsyncMock())

    # Act & Assert
    with pytest.raises(ServiceError) as exc_info:
        await service.get_job_status("nonexistent-job-id")

    error = exc_info.value
    assert error.code == ErrorCode.JOB_NOT_FOUND
    assert error.http_status == 404
    assert "nonexistent-job-id" in error.message
