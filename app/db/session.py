"""Database session management."""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings

# Determine database URL based on configuration
# If DATABASE_PATH is provided and no other URL is set, default to SQLite
# Note: SQLAlchemy uses sqlite+aiosqlite for async SQLite
if settings.DATABASE_PATH and not hasattr(settings, 'DATABASE_URL'):
    # Ensure we use absolute path for SQLite
    database_url = f"sqlite+aiosqlite:///{settings.DATABASE_PATH}"
else:
    # Fallback or explicit configuration (e.g. from env var injected into settings)
    # This assumes settings might be extended or env var is read directly if needed
    # For now, we rely on the logic that we are moving from SQLite
    database_url = getattr(settings, 'DATABASE_URL', f"sqlite+aiosqlite:///{settings.DATABASE_PATH}")


engine = create_async_engine(
    database_url,
    echo=settings.is_debug_mode,
    future=True,
    # SQLite specific args for concurrency
    connect_args={"check_same_thread": False} if "sqlite" in database_url else {}
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
