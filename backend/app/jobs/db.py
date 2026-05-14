"""Async DB helpers for the ingestion job.

We re-use the existing `app.db.session.SessionManager` engine where possible to share
the pool. For ad-hoc CLI invocations we create our own engine if no manager is present.

For the ingestion job, we connect as the local `postgres` superuser (which bypasses RLS)
in dev. In production this will become the Supabase service_role connection (which also
bypasses RLS via the `service_role_full FOR ALL TO service_role` policy).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


_engine: AsyncEngine | None = None


def _normalize_url(url: str) -> str:
    """Make sure DATABASE_URL uses the asyncpg driver."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):  # rarely used
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


def get_engine() -> AsyncEngine:
    """Singleton async engine for the ingestion job."""
    global _engine
    if _engine is None:
        url = os.environ.get(
            "DATABASE_URL",
            "postgresql://postgres:postgres@127.0.0.1:56322/postgres",
        )
        _engine = create_async_engine(
            _normalize_url(url),
            pool_size=int(os.environ.get("INGESTION_DB_POOL_SIZE", "5")),
            max_overflow=int(os.environ.get("INGESTION_DB_MAX_OVERFLOW", "5")),
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


async def dispose_engine() -> None:
    """Tear down the ingestion engine (used in tests + at end of CLI runs)."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Open an async transactional session; commit on success, rollback on error."""
    engine = get_engine()
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
