"""Database session management with connection pooling."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


class SessionManager:
    """Manages database connections and sessions."""

    def __init__(self) -> None:
        """Initialize the session manager with connection pool."""
        # Convert postgresql:// to postgresql+asyncpg://
        database_url = settings.DATABASE_URL.replace(
            "postgresql://", "postgresql+asyncpg://"
        )

        self.engine: AsyncEngine = create_async_engine(
            database_url,
            pool_size=settings.DB_POOL_SIZE,  # Base pool size
            max_overflow=settings.DB_MAX_OVERFLOW,  # Additional connections
            pool_timeout=30,  # Wait time before error
            pool_recycle=1800,  # Recycle connections after 30 minutes
            pool_pre_ping=True,  # Verify connection health before use
            echo=settings.ENVIRONMENT == "development",  # Log SQL in dev mode
        )

        self.async_session_maker = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Provide a transactional scope for database operations.

        Yields:
            AsyncSession instance

        Example:
            async with session_manager.session() as session:
                result = await session.execute(query)
        """
        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self) -> None:
        """Close all database connections."""
        await self.engine.dispose()


# Global session manager instance
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Get or create the global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
