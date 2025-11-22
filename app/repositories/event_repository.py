"""Repository for ImageUploadEvent models."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ImageUploadEvent
from app.repositories.base import BaseRepository


class EventRepository(BaseRepository[ImageUploadEvent]):
    """Repository for accessing image upload event data."""

    def __init__(self, session: AsyncSession):
        super().__init__(ImageUploadEvent, session)

    # Add specific event queries here if needed
