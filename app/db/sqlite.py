"""SQLite database operations for the image processor."""

import aiosqlite
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


logger = logging.getLogger(__name__)


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
            logger.info(f"Database initialized at {self.db_path}")

    async def create_job(
        self,
        job_id: str,
        image_id: str,
        storage_bucket: str,
        staging_path: str,
        metadata: dict
    ) -> dict:
        """Create a new processing job.

        Args:
            job_id: Unique job identifier
            image_id: Unique image identifier
            storage_bucket: Target storage bucket name
            staging_path: Temporary staging file path
            metadata: Job metadata dictionary

        Returns:
            dict: Created job information
        """
        now = datetime.utcnow().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            # Create job record
            await db.execute("""
                INSERT INTO processing_jobs (
                    job_id, image_id, status, storage_bucket,
                    staging_path, processing_metadata, created_at
                ) VALUES (?, ?, 'pending', ?, ?, ?, ?)
            """, (job_id, image_id, storage_bucket, staging_path, json.dumps(metadata), now))

            # Log event
            await db.execute("""
                INSERT INTO image_upload_events (
                    id, event_type, image_id, job_id, metadata, created_at
                ) VALUES (?, 'upload_initiated', ?, ?, ?, ?)
            """, (job_id, image_id, job_id, json.dumps(metadata), now))

            await db.commit()

        return {"job_id": job_id, "staging_path": staging_path}

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
        now = datetime.utcnow().isoformat()

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

    async def get_job(self, job_id: str) -> Optional[dict]:
        """Get job details by job_id.

        Args:
            job_id: Job identifier

        Returns:
            dict or None: Job details including parsed JSON fields
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM processing_jobs WHERE job_id = ?", (job_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    result = dict(row)
                    # Parse JSON fields
                    if result.get('processed_paths'):
                        result['processed_paths'] = json.loads(result['processed_paths'])
                    if result.get('processing_metadata'):
                        result['processing_metadata'] = json.loads(result['processing_metadata'])
                    return result
        return None

    async def get_job_by_image_id(self, image_id: str) -> Optional[dict]:
        """Get most recent completed job for an image_id.

        Args:
            image_id: Image identifier

        Returns:
            dict or None: Most recent completed job for this image
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM processing_jobs
                WHERE image_id = ? AND status = 'completed'
                ORDER BY completed_at DESC LIMIT 1
            """, (image_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    result = dict(row)
                    # Parse JSON fields
                    if result.get('processed_paths'):
                        result['processed_paths'] = json.loads(result['processed_paths'])
                    if result.get('processing_metadata'):
                        result['processing_metadata'] = json.loads(result['processing_metadata'])
                    return result
        return None

    async def check_rate_limit(self, user_id: str, max_uploads: int = 50) -> dict:
        """Check and increment rate limit for a user.

        Args:
            user_id: User identifier
            max_uploads: Maximum allowed uploads per window

        Returns:
            dict: Rate limit status with allowed, remaining, reset_at
        """
        # Calculate current hourly window
        window_start = datetime.utcnow().replace(
            minute=0, second=0, microsecond=0
        ).isoformat()

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

            return {
                "allowed": True,
                "remaining": max_uploads - current_count - 1,
                "reset_at": window_start
            }

    async def can_retry(self, job_id: str) -> bool:
        """Check if a job can be retried based on attempt count.

        Args:
            job_id: Job identifier

        Returns:
            bool: True if job can be retried
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT attempt_count, max_retries
                FROM processing_jobs
                WHERE job_id = ?
            """, (job_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0] < row[1]
        return False


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
