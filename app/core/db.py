"""
Database Session Management
SQLAlchemy 2.0 Async Session Configuration
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)

from app.core.config import settings
from app.models.base import Base


# Async Engine (created once at startup)
async_engine: AsyncEngine | None = None


def get_async_engine() -> AsyncEngine:
    """
    Get or create async database engine

    Returns:
        AsyncEngine instance
    """
    global async_engine

    if async_engine is None:
        async_engine = create_async_engine(
            settings.async_database_url,
            echo=settings.database_echo,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,  # Verify connections before using
        )

    return async_engine


# Async Session Maker
async_session_maker = async_sessionmaker(
    bind=get_async_engine(),
    class_=AsyncSession,
    expire_on_commit=False,  # Prevent lazy-loading issues
    autocommit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI routes to get database session

    Usage:
        @router.get("/example")
        async def example(session: AsyncSession = Depends(get_session)):
            ...

    Yields:
        AsyncSession instance
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database (create tables)
    Should only be used in development. Use Alembic in production.
    """
    async with get_async_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    Close database connections
    Should be called on application shutdown
    """
    global async_engine

    if async_engine is not None:
        await async_engine.dispose()
        async_engine = None
