"""Base repository pattern."""

from typing import Generic, TypeVar, Type, Optional, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from app.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository with common CRUD operations."""

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """
        Args:
            model: The SQLAlchemy model class.
            session: The async database session.
        """
        self.model = model
        self.session = session

    async def get(self, id: Any) -> Optional[ModelType]:
        """Get a record by its primary key."""
        return await self.session.get(self.model, id)

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Get all records with pagination."""
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> ModelType:
        """Create a new record."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: Any, **kwargs) -> Optional[ModelType]:
        """Update a record by its primary key."""
        instance = await self.get(id)
        if instance:
            for key, value in kwargs.items():
                setattr(instance, key, value)
            await self.session.flush()
            await self.session.refresh(instance)
        return instance

    async def delete(self, id: Any) -> bool:
        """Delete a record by its primary key."""
        instance = await self.get(id)
        if instance:
            await self.session.delete(instance)
            await self.session.flush()
            return True
        return False
