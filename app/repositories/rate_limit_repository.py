"""Repository for UploadRateLimit models."""

from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UploadRateLimit
from app.repositories.base import BaseRepository


class RateLimitRepository(BaseRepository[UploadRateLimit]):
    """Repository for accessing rate limit data."""

    def __init__(self, session: AsyncSession):
        super().__init__(UploadRateLimit, session)

    async def get_by_user_and_window(self, user_id: str, window_start: str) -> Optional[UploadRateLimit]:
        """Get rate limit record for user and window."""
        return await self.get((user_id, window_start))

    async def increment_usage(self, user_id: str, window_start: str) -> int:
        """Increment usage count for a user in a window."""
        rate_limit = await self.get((user_id, window_start))
        if not rate_limit:
            rate_limit = await self.create(
                user_id=user_id,
                window_start=window_start,
                upload_count=1
            )
        else:
            rate_limit.upload_count += 1
            await self.session.flush()
            await self.session.refresh(rate_limit)

        return rate_limit.upload_count

    async def delete_old_windows(self, cutoff: str) -> int:
        """Delete rate limit records older than cutoff (string timestamp)."""
        # Assuming window_start is comparable string
        stmt = delete(self.model).where(self.model.window_start < cutoff)
        result = await self.session.execute(stmt)
        # commit is handled by service
        return result.rowcount
