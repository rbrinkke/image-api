"""Service layer for image processing operations."""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.repositories.job_repository import JobRepository
from app.repositories.event_repository import EventRepository
from app.repositories.rate_limit_repository import RateLimitRepository
from app.db.models import ProcessingJob, ImageUploadEvent

logger = get_logger(__name__)


class ProcessorService:
    """Service for image processing business logic."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.job_repo = JobRepository(session)
        self.event_repo = EventRepository(session)
        self.rate_limit_repo = RateLimitRepository(session)

    async def create_job(
        self,
        job_id: str,
        image_id: str,
        storage_bucket: str,
        staging_path: str,
        metadata: dict,
        user_id: str,
        organization_id: str
    ) -> dict:
        """Create a new processing job."""
        start_time = time.time()

        logger.debug(
            "service_create_job_started",
            job_id=job_id,
            image_id=image_id,
            bucket=storage_bucket,
        )

        try:
            # Create job
            await self.job_repo.create(
                job_id=job_id,
                image_id=image_id,
                status='pending',
                storage_bucket=storage_bucket,
                staging_path=staging_path,
                processing_metadata=metadata,
                user_id=user_id,
                organization_id=organization_id,
            )

            # Log event
            event_id = str(uuid.uuid4())
            await self.event_repo.create(
                id=event_id,
                event_type='upload_initiated',
                image_id=image_id,
                job_id=job_id,
                metadata_=metadata
            )

            await self.session.commit()

            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                "service_create_job_success",
                job_id=job_id,
                image_id=image_id,
                duration_ms=round(duration_ms, 2),
            )

            return {"job_id": job_id, "staging_path": staging_path}

        except Exception as exc:
            await self.session.rollback()
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "service_create_job_failed",
                job_id=job_id,
                image_id=image_id,
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def update_job_status(
        self,
        job_id: str,
        status: str,
        processed_paths: Optional[dict] = None,
        processing_metadata: Optional[dict] = None,
        error: Optional[str] = None
    ):
        """Update job processing status."""
        start_time = time.time()

        now = datetime.now(timezone.utc)

        logger.debug(
            "service_update_job_status_started",
            job_id=job_id,
            new_status=status,
            has_processed_paths=processed_paths is not None,
            has_error=error is not None,
        )

        try:
            job = await self.job_repo.get_by_job_id(job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found")

            updates = {}

            # Set started_at on first processing
            if status == 'processing' and job.started_at is None:
                updates['started_at'] = now

            # Set completed_at on terminal states
            if status in ('completed', 'failed'):
                updates['completed_at'] = now

            await self.job_repo.update_status(
                job_id=job_id,
                status=status,
                processed_paths=processed_paths,
                processing_metadata=processing_metadata,
                error=error,
                **updates
            )

            await self.session.commit()

            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                "service_update_job_status_success",
                job_id=job_id,
                new_status=status,
                variant_count=len(processed_paths) if processed_paths else 0,
                duration_ms=round(duration_ms, 2),
            )

        except Exception as exc:
            await self.session.rollback()
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "service_update_job_status_failed",
                job_id=job_id,
                new_status=status,
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def get_job(self, job_id: str) -> Optional[dict]:
        """Get job details."""
        start_time = time.time()
        logger.debug("service_get_job_started", job_id=job_id)

        try:
            job = await self.job_repo.get_by_job_id(job_id)
            duration_ms = (time.time() - start_time) * 1000

            if job:
                # Convert model to dict
                result = {
                    "job_id": job.job_id,
                    "image_id": job.image_id,
                    "status": job.status,
                    "storage_bucket": job.storage_bucket,
                    "staging_path": job.staging_path,
                    "processed_paths": job.processed_paths,
                    "processing_metadata": job.processing_metadata,
                    "user_id": job.user_id,
                    "organization_id": job.organization_id,
                    "attempt_count": job.attempt_count,
                    "max_retries": job.max_retries,
                    "last_error": job.last_error,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                }

                logger.debug(
                    "service_get_job_found",
                    job_id=job_id,
                    status=job.status,
                    duration_ms=round(duration_ms, 2),
                )
                return result
            else:
                logger.debug(
                    "service_get_job_not_found",
                    job_id=job_id,
                    duration_ms=round(duration_ms, 2),
                )
                return None

        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "service_get_job_failed",
                job_id=job_id,
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def get_job_by_image_id(self, image_id: str) -> Optional[dict]:
        """Get most recent completed job for an image_id."""
        start_time = time.time()
        logger.debug("service_get_job_by_image_id_started", image_id=image_id)

        try:
            job = await self.job_repo.get_latest_completed_by_image_id(image_id)
            duration_ms = (time.time() - start_time) * 1000

            if job:
                result = {
                    "job_id": job.job_id,
                    "image_id": job.image_id,
                    "status": job.status,
                    "storage_bucket": job.storage_bucket,
                    "staging_path": job.staging_path,
                    "processed_paths": job.processed_paths,
                    "processing_metadata": job.processing_metadata,
                    "user_id": job.user_id,
                    "organization_id": job.organization_id,
                    "attempt_count": job.attempt_count,
                    "max_retries": job.max_retries,
                    "last_error": job.last_error,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                }

                logger.debug(
                    "service_get_job_by_image_id_found",
                    image_id=image_id,
                    job_id=job.job_id,
                    duration_ms=round(duration_ms, 2),
                )
                return result
            else:
                logger.debug(
                    "service_get_job_by_image_id_not_found",
                    image_id=image_id,
                    duration_ms=round(duration_ms, 2),
                )
                return None

        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "service_get_job_by_image_id_failed",
                image_id=image_id,
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def check_rate_limit(self, user_id: str, max_uploads: int = 50) -> dict:
        """Check and increment rate limit for a user."""
        start_time = time.time()

        # Calculate current hourly window
        window_start = datetime.now(timezone.utc).replace(
            minute=0, second=0, microsecond=0
        ).isoformat()

        logger.debug(
            "service_rate_limit_check_started",
            user_id=user_id,
            max_uploads=max_uploads,
            window_start=window_start,
        )

        try:
            rate_limit = await self.rate_limit_repo.get_by_user_and_window(user_id, window_start)
            current_count = rate_limit.upload_count if rate_limit else 0

            if current_count >= max_uploads:
                duration_ms = (time.time() - start_time) * 1000
                logger.warning(
                    "service_rate_limit_exceeded",
                    user_id=user_id,
                    current_count=current_count,
                    max_uploads=max_uploads,
                    duration_ms=round(duration_ms, 2),
                )
                return {
                    "allowed": False,
                    "remaining": 0,
                    "reset_at": window_start
                }

            new_count = await self.rate_limit_repo.increment_usage(user_id, window_start)
            await self.session.commit()

            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                "service_rate_limit_incremented",
                user_id=user_id,
                new_count=new_count,
                remaining=max_uploads - new_count,
                duration_ms=round(duration_ms, 2),
            )

            return {
                "allowed": True,
                "remaining": max_uploads - new_count,
                "reset_at": window_start
            }

        except Exception as exc:
            await self.session.rollback()
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "service_rate_limit_check_failed",
                user_id=user_id,
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def can_retry(self, job_id: str) -> bool:
        """Check if a job can be retried."""
        start_time = time.time()
        logger.debug("service_can_retry_check_started", job_id=job_id)

        try:
            job = await self.job_repo.get_by_job_id(job_id)
            duration_ms = (time.time() - start_time) * 1000

            if job:
                can_retry = job.attempt_count < job.max_retries
                logger.debug(
                    "service_can_retry_checked",
                    job_id=job_id,
                    attempt_count=job.attempt_count,
                    max_retries=job.max_retries,
                    can_retry=can_retry,
                    duration_ms=round(duration_ms, 2),
                )
                return can_retry
            else:
                logger.warning(
                    "service_can_retry_job_not_found",
                    job_id=job_id,
                    duration_ms=round(duration_ms, 2),
                )
                return False

        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "service_can_retry_check_failed",
                job_id=job_id,
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def delete_job(self, job_id: str):
        """Delete a job record."""
        start_time = time.time()
        logger.debug("service_delete_job_started", job_id=job_id)

        try:
            success = await self.job_repo.delete(job_id)
            if success:
                await self.session.commit()

            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                "service_delete_job_success",
                job_id=job_id,
                duration_ms=round(duration_ms, 2),
            )

        except Exception as exc:
            await self.session.rollback()
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "service_delete_job_failed",
                job_id=job_id,
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def get_old_failed_or_pending_jobs(self, cutoff: datetime) -> List[ProcessingJob]:
        """Get failed/pending jobs older than cutoff."""
        return await self.job_repo.get_old_failed_or_pending_jobs(cutoff)

    async def cleanup_old_rate_limits(self, cutoff: str) -> int:
        """Cleanup old rate limit records."""
        try:
            count = await self.rate_limit_repo.delete_old_windows(cutoff)
            await self.session.commit()
            return count
        except Exception:
            await self.session.rollback()
            raise
