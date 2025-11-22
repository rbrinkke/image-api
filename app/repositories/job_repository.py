"""Repository for ProcessingJob models."""

from typing import Optional, List
from datetime import datetime
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProcessingJob
from app.repositories.base import BaseRepository


class JobRepository(BaseRepository[ProcessingJob]):
    """Repository for accessing processing job data."""

    def __init__(self, session: AsyncSession):
        super().__init__(ProcessingJob, session)

    async def get_by_job_id(self, job_id: str) -> Optional[ProcessingJob]:
        """Get job by job_id."""
        return await self.get(job_id)

    async def get_latest_completed_by_image_id(self, image_id: str) -> Optional[ProcessingJob]:
        """Get most recent completed job for an image_id."""
        stmt = select(self.model).where(
            self.model.image_id == image_id,
            self.model.status == 'completed'
        ).order_by(self.model.completed_at.desc()).limit(1)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self,
        job_id: str,
        status: str,
        processed_paths: Optional[dict] = None,
        processing_metadata: Optional[dict] = None,
        error: Optional[str] = None,
        started_at = None,
        completed_at = None
    ) -> Optional[ProcessingJob]:
        """Update job status and related fields."""
        job = await self.get(job_id)
        if not job:
            return None

        job.status = status

        if started_at:
            job.started_at = started_at

        if completed_at:
            job.completed_at = completed_at

        if processed_paths:
            job.processed_paths = processed_paths

        if processing_metadata:
            # Merge or replace? Original code replaced or merged in task logic.
            # We will assume the service layer passes the final dict.
            job.processing_metadata = processing_metadata

        if error:
            job.last_error = error

        if status == 'retrying':
            job.attempt_count += 1

        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def has_started(self, job_id: str) -> bool:
        """Check if job has started."""
        job = await self.get(job_id)
        return job.started_at is not None if job else False

    async def get_old_failed_or_pending_jobs(self, cutoff: datetime) -> List[ProcessingJob]:
        """Get failed or pending jobs older than cutoff with staging path."""
        stmt = select(self.model).where(
            self.model.status.in_(['failed', 'pending']),
            self.model.created_at < cutoff,
            self.model.staging_path.is_not(None)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
