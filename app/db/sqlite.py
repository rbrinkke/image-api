"""SQLite database operations for the image processor."""

import aiosqlite
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from app.core.logging_config import get_logger


logger = get_logger(__name__)


class ProcessorDB:
    """SQLite database handler for image processing operations."""

    def __init__(self, db_path: str):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async def init_schema(self):
        """Initialize database schema from SQL file."""
        schema_path = Path(__file__).parent / "schema.sql"
        async with aiosqlite.connect(self.db_path) as db:
            with open(schema_path) as f:
                await db.executescript(f.read())
            await db.commit()
            logger.info(
                "database_schema_initialized",
                db_path=self.db_path,
                schema_file=str(schema_path),
            )

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
        """Create a new processing job.

        Args:
            job_id: Unique job identifier
            image_id: Unique image identifier
            storage_bucket: Target storage bucket name
            staging_path: Temporary staging file path
            metadata: Job metadata dictionary
            user_id: Owner user identifier (for RBAC)
            organization_id: Organization identifier (for RBAC)

        Returns:
            dict: Created job information
        """
        start_time = time.time()
        now = datetime.utcnow().isoformat()

        logger.debug(
            "db_create_job_started",
            job_id=job_id,
            image_id=image_id,
            bucket=storage_bucket,
        )

        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Create job record
                await db.execute("""
                    INSERT INTO processing_jobs (
                        job_id, image_id, status, storage_bucket,
                        staging_path, processing_metadata, created_at,
                        user_id, organization_id
                    ) VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?)
                """, (job_id, image_id, storage_bucket, staging_path, json.dumps(metadata), now, user_id, organization_id))

                # Log event
                await db.execute("""
                    INSERT INTO image_upload_events (
                        id, event_type, image_id, job_id, metadata, created_at
                    ) VALUES (?, 'upload_initiated', ?, ?, ?, ?)
                """, (job_id, image_id, job_id, json.dumps(metadata), now))

                await db.commit()

            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                "db_create_job_success",
                job_id=job_id,
                image_id=image_id,
                duration_ms=round(duration_ms, 2),
            )

            return {"job_id": job_id, "staging_path": staging_path}

        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "db_create_job_failed",
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
        error: Optional[str] = None
    ):
        """Update job processing status.

        Args:
            job_id: Job identifier
            status: New status (pending, processing, completed, failed, retrying)
            processed_paths: Dictionary of processed file paths by variant
            error: Error message if failed
        """
        start_time = time.time()
        now = datetime.utcnow().isoformat()

        logger.debug(
            "db_update_job_status_started",
            job_id=job_id,
            new_status=status,
            has_processed_paths=processed_paths is not None,
            has_error=error is not None,
        )

        try:
            async with aiosqlite.connect(self.db_path) as db:
                updates = ["status = ?"]
                params = [status]

                # Set started_at on first processing
                if status == 'processing' and not await self._has_started(db, job_id):
                    updates.append("started_at = ?")
                    params.append(now)

                # Set completed_at on terminal states
                if status in ('completed', 'failed'):
                    updates.append("completed_at = ?")
                    params.append(now)

                # Store processed paths
                if processed_paths:
                    updates.append("processed_paths = ?")
                    params.append(json.dumps(processed_paths))

                # Store error message
                if error:
                    updates.append("last_error = ?")
                    params.append(error)

                # Increment retry counter
                if status == 'retrying':
                    updates.append("attempt_count = attempt_count + 1")

                params.append(job_id)

                await db.execute(f"""
                    UPDATE processing_jobs
                    SET {', '.join(updates)}
                    WHERE job_id = ?
                """, params)

                await db.commit()

            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                "db_update_job_status_success",
                job_id=job_id,
                new_status=status,
                variant_count=len(processed_paths) if processed_paths else 0,
                duration_ms=round(duration_ms, 2),
            )

        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "db_update_job_status_failed",
                job_id=job_id,
                new_status=status,
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def _has_started(self, db: aiosqlite.Connection, job_id: str) -> bool:
        """Check if job has started_at timestamp.

        Args:
            db: Database connection
            job_id: Job identifier

        Returns:
            bool: True if job has started
        """
        async with db.execute(
            "SELECT started_at FROM processing_jobs WHERE job_id = ?", (job_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row and row[0] is not None

    def _parse_job_row(self, row: aiosqlite.Row) -> dict:
        """Parse job row and deserialize JSON fields.

        This eliminates duplication of JSON parsing logic across query methods.

        Args:
            row: Database row from processing_jobs table

        Returns:
            dict: Parsed job data with deserialized JSON fields
        """
        result = dict(row)
        # Deserialize JSON fields
        if result.get('processed_paths'):
            result['processed_paths'] = json.loads(result['processed_paths'])
        if result.get('processing_metadata'):
            result['processing_metadata'] = json.loads(result['processing_metadata'])
        return result

    async def get_job(self, job_id: str) -> Optional[dict]:
        """Get job details by job_id.

        Args:
            job_id: Job identifier

        Returns:
            dict or None: Job details including parsed JSON fields
        """
        start_time = time.time()
        logger.debug("db_get_job_started", job_id=job_id)

        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM processing_jobs WHERE job_id = ?", (job_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    duration_ms = (time.time() - start_time) * 1000

                    if row:
                        result = self._parse_job_row(row)
                        logger.debug(
                            "db_get_job_found",
                            job_id=job_id,
                            status=result.get("status"),
                            duration_ms=round(duration_ms, 2),
                        )
                        return result
                    else:
                        logger.debug(
                            "db_get_job_not_found",
                            job_id=job_id,
                            duration_ms=round(duration_ms, 2),
                        )
            return None

        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "db_get_job_failed",
                job_id=job_id,
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def get_job_by_image_id(self, image_id: str) -> Optional[dict]:
        """Get most recent completed job for an image_id.

        Args:
            image_id: Image identifier

        Returns:
            dict or None: Most recent completed job for this image
        """
        start_time = time.time()
        logger.debug("db_get_job_by_image_id_started", image_id=image_id)

        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT * FROM processing_jobs
                    WHERE image_id = ? AND status = 'completed'
                    ORDER BY completed_at DESC LIMIT 1
                """, (image_id,)) as cursor:
                    row = await cursor.fetchone()
                    duration_ms = (time.time() - start_time) * 1000

                    if row:
                        result = self._parse_job_row(row)
                        logger.debug(
                            "db_get_job_by_image_id_found",
                            image_id=image_id,
                            job_id=result.get("job_id"),
                            duration_ms=round(duration_ms, 2),
                        )
                        return result
                    else:
                        logger.debug(
                            "db_get_job_by_image_id_not_found",
                            image_id=image_id,
                            duration_ms=round(duration_ms, 2),
                        )
            return None

        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "db_get_job_by_image_id_failed",
                image_id=image_id,
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def check_rate_limit(self, user_id: str, max_uploads: int = 50) -> dict:
        """Check and increment rate limit for a user.

        Args:
            user_id: User identifier
            max_uploads: Maximum allowed uploads per window

        Returns:
            dict: Rate limit status with allowed, remaining, reset_at
        """
        start_time = time.time()
        # Calculate current hourly window
        window_start = datetime.utcnow().replace(
            minute=0, second=0, microsecond=0
        ).isoformat()

        logger.debug(
            "db_rate_limit_check_started",
            user_id=user_id,
            max_uploads=max_uploads,
            window_start=window_start,
        )

        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Get current count for this window
                async with db.execute("""
                    SELECT upload_count FROM upload_rate_limits
                    WHERE user_id = ? AND window_start = ?
                """, (user_id, window_start)) as cursor:
                    row = await cursor.fetchone()

                current_count = row[0] if row else 0

                # Check if limit exceeded
                if current_count >= max_uploads:
                    duration_ms = (time.time() - start_time) * 1000
                    logger.warning(
                        "db_rate_limit_exceeded",
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

                # Increment counter
                await db.execute("""
                    INSERT INTO upload_rate_limits (user_id, window_start, upload_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(user_id, window_start)
                    DO UPDATE SET upload_count = upload_count + 1
                """, (user_id, window_start))

                await db.commit()

                duration_ms = (time.time() - start_time) * 1000
                logger.info(
                    "db_rate_limit_incremented",
                    user_id=user_id,
                    new_count=current_count + 1,
                    remaining=max_uploads - current_count - 1,
                    duration_ms=round(duration_ms, 2),
                )

                return {
                    "allowed": True,
                    "remaining": max_uploads - current_count - 1,
                    "reset_at": window_start
                }

        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "db_rate_limit_check_failed",
                user_id=user_id,
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def can_retry(self, job_id: str) -> bool:
        """Check if a job can be retried based on attempt count.

        Args:
            job_id: Job identifier

        Returns:
            bool: True if job can be retried
        """
        start_time = time.time()
        logger.debug("db_can_retry_check_started", job_id=job_id)

        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("""
                    SELECT attempt_count, max_retries
                    FROM processing_jobs
                    WHERE job_id = ?
                """, (job_id,)) as cursor:
                    row = await cursor.fetchone()
                    duration_ms = (time.time() - start_time) * 1000

                    if row:
                        can_retry = row[0] < row[1]
                        logger.debug(
                            "db_can_retry_checked",
                            job_id=job_id,
                            attempt_count=row[0],
                            max_retries=row[1],
                            can_retry=can_retry,
                            duration_ms=round(duration_ms, 2),
                        )
                        return can_retry
                    else:
                        logger.warning(
                            "db_can_retry_job_not_found",
                            job_id=job_id,
                            duration_ms=round(duration_ms, 2),
                        )
            return False

        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "db_can_retry_check_failed",
                job_id=job_id,
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise


# Global database instance
_db: Optional[ProcessorDB] = None


def get_db() -> ProcessorDB:
    """Get or create global database instance.

    Returns:
        ProcessorDB: Global database instance
    """
    global _db
    if _db is None:
        from app.core.config import settings
        _db = ProcessorDB(settings.DATABASE_PATH)
    return _db

# Updated: 2025-11-18 22:01 UTC - Production-ready code
