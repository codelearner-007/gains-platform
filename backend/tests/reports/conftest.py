"""Fixtures for the report-calculation regression suite.

READ-ONLY. These tests never write or truncate — they open a session, scope it
to a school via the RLS GUC (exactly as a request does), call the report
repository / service, and assert results. Each test rolls back, so the dev DB
is never mutated. This suite is intentionally isolated from the destructive
pipeline/ingestion conftests under ``tests/transformations`` and ``tests/jobs``
(which TRUNCATE tables); nothing here imports them.

A fresh NullPool engine is created per test so the asyncpg connection is bound
to that test's event loop (pytest-asyncio uses a new loop per test, which would
otherwise trip "Event loop is closed" on a shared/pooled engine).
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


@pytest_asyncio.fixture
async def db():
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()
    finally:
        await engine.dispose()
