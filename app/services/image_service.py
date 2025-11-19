"""
Image Service Layer - Business Logic Orchestration

This service layer separates HTTP concerns from business logic.
Benefits:
- Testable without HTTP mocking
- Reusable across different interfaces (API, CLI, batch jobs)
- Clear responsibility boundaries
- Easy to reason about and maintain
"""
import json
from uuid import uuid4
from datetime import datetime
from typing import Dict, Any
from fastapi import UploadFile

from app.db.sqlite import ProcessorDB
from app.storage.protocol import StorageBackend
from app.tasks.celery_app import process_image_task
from app.core.logging_config import get_logger
from app.core.errors import ServiceError, ErrorCode, processing_error, not_found_error
from app.core.config import settings

logger = get_logger(__name__)


class ImageService:
    """
    Core service for image processing orchestration.

    Responsibilities:
    - Coordinate between DB, Storage, and Task Queue
    - Enforce business rules
    - Handle transactions (create job, save file, queue task)
    - Provide clear error messages

    Does NOT know about:
    - HTTP status codes (returns data, raises ServiceError)
    - Request/Response formats (works with primitives)
    - Headers, cookies, sessions
    """

    def __init__(self, db: ProcessorDB, storage: StorageBackend):
        self.db = db
        self.storage = storage

    async def process_new_upload(
        self,
        file: UploadFile,
        bucket: str,
        auth_user_id: str,
        auth_org_id: str,
        metadata_json: str,
        content_length: int,
        detected_mime: str
    ) -> Dict[str, Any]:
        """
        Orchestrates the complete upload flow.

        Flow:
        1. Parse and validate metadata
        2. Generate unique identifiers (job_id, image_id)
        3. Create database record
        4. Save to staging storage
        5. Queue async processing task

        Args:
            file: The uploaded file object
            bucket: Logical storage bucket (e.g., "org-123/groups/abc")
            auth_user_id: Authenticated user ID from JWT
            auth_org_id: Organization ID from JWT
            metadata_json: JSON string with additional metadata
            content_length: File size in bytes
            detected_mime: MIME type detected via magic bytes

        Returns:
            Dict with job_id, image_id, status, and status_url

        Raises:
            ServiceError: On any business logic failure
        """

        # 1. Parse Metadata
        try:
            meta = json.loads(metadata_json)
        except json.JSONDecodeError as e:
            logger.warning("metadata_parse_failed", raw=metadata_json, error=str(e))
            # Graceful degradation: use empty dict instead of failing
            meta = {}

        # 2. Generate Identifiers
        job_id = str(uuid4())
        image_id = str(uuid4())
        timestamp = int(datetime.utcnow().timestamp())
        staging_path = f"staging/{image_id}_{timestamp}"

        # 3. Prepare Processing Metadata
        processing_metadata = {
            **meta,
            "uploader_id": auth_user_id,
            "org_id": auth_org_id,
            "original_filename": file.filename,
            "detected_mime_type": detected_mime,
            "content_length": content_length,
            "client_id": "image-api-v1",
            "upload_timestamp": timestamp
        }

        logger.info(
            "starting_upload_process",
            job_id=job_id,
            image_id=image_id,
            bucket=bucket,
            user_id=auth_user_id
        )

        # 4. Database Transaction (Atomic Job Creation)
        try:
            await self.db.create_job(
                job_id=job_id,
                image_id=image_id,
                storage_bucket=bucket,
                staging_path=staging_path,
                metadata=processing_metadata,
                user_id=auth_user_id,
                organization_id=auth_org_id
            )
            logger.debug("job_record_created", job_id=job_id)
        except Exception as e:
            logger.error("db_persist_failed", job_id=job_id, error=str(e))
            raise processing_error(
                code=ErrorCode.JOB_CREATION_FAILED,
                message="Could not create job record in database",
                details={"job_id": job_id}
            )

        # 5. Storage Operation (Save to Staging)
        try:
            # Reset file pointer to beginning (safety measure)
            try:
                await file.seek(0)
            except Exception as seek_error:
                # File stream might be closed or unseekable, log but continue
                logger.warning("file_seek_failed", job_id=job_id, error=str(seek_error))

            await self.storage.save(file.file, bucket, staging_path)
            logger.debug("file_saved_to_staging", job_id=job_id, path=staging_path)
        except Exception as e:
            # CRITICAL RACE CONDITION FIX: Rollback database state
            # Job exists in DB but file not saved - mark as failed to prevent zombie jobs
            logger.error(
                "storage_save_failed",
                job_id=job_id,
                bucket=bucket,
                path=staging_path,
                error=str(e)
            )

            # Rollback: Mark job as failed in database
            try:
                await self.db.update_job_status(
                    job_id=job_id,
                    status='failed',
                    error=f"Storage save failed: {str(e)}"
                )
                logger.info("job_marked_failed_after_storage_error", job_id=job_id)
            except Exception as rollback_error:
                # Rollback failed - log critical error
                logger.critical(
                    "rollback_failed_after_storage_error",
                    job_id=job_id,
                    rollback_error=str(rollback_error),
                    original_error=str(e)
                )

            raise processing_error(
                code=ErrorCode.STAGING_FAILED,
                message="Could not save file to staging storage",
                details={"job_id": job_id, "bucket": bucket}
            )

        # 6. Task Queue Operation (Trigger Async Processing)
        try:
            process_image_task.delay(job_id)
            logger.info("processing_task_queued", job_id=job_id)
        except Exception as e:
            # CRITICAL RACE CONDITION FIX: Rollback database state and cleanup file
            # Job and file exist, but not queued for processing - would remain pending forever
            logger.error("celery_dispatch_failed", job_id=job_id, error=str(e))

            # Rollback: Mark job as failed in database
            try:
                await self.db.update_job_status(
                    job_id=job_id,
                    status='failed',
                    error=f"Task queue failed: {str(e)}"
                )
                logger.info("job_marked_failed_after_queue_error", job_id=job_id)
            except Exception as rollback_error:
                logger.critical(
                    "rollback_failed_after_queue_error",
                    job_id=job_id,
                    rollback_error=str(rollback_error),
                    original_error=str(e)
                )

            # Cleanup: Delete orphaned staging file
            try:
                await self.storage.delete(bucket, staging_path)
                logger.info("staging_file_cleaned_up", job_id=job_id, path=staging_path)
            except Exception as cleanup_error:
                logger.warning(
                    "staging_cleanup_failed",
                    job_id=job_id,
                    path=staging_path,
                    error=str(cleanup_error)
                )

            raise processing_error(
                code=ErrorCode.TASK_QUEUE_FAILED,
                message="Could not queue processing task",
                details={"job_id": job_id}
            )

        # Success: Return job details
        return {
            "job_id": job_id,
            "image_id": image_id,
            "status": "pending",
            "status_url": f"/api/v1/images/jobs/{job_id}"
        }

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Retrieve current job status.

        Args:
            job_id: Unique job identifier

        Returns:
            Dict with job status and metadata

        Raises:
            ServiceError: If job not found (404 with JOB_NOT_FOUND code)
        """
        job = await self.db.get_job(job_id)
        if not job:
            raise not_found_error(
                code=ErrorCode.JOB_NOT_FOUND,
                message=f"Job not found: {job_id}",
                details={"job_id": job_id}
            )

        return {
            "job_id": job["job_id"],
            "image_id": job["image_id"],
            "status": job["status"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "last_error": job.get("last_error")
        }


# Updated: 2025-11-18 22:01 UTC - Production-ready code
