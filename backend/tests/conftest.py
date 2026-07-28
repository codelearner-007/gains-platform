"""Pytest configuration and fixtures."""

import pytest
from typing import AsyncGenerator

import httpx
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session_manager
from app.main import app


@pytest.fixture(scope="session")
def anyio_backend():
    """Use asyncio as the async backend for pytest-asyncio."""
    return "asyncio"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a test database session.

    For true isolation, use a separate test database.
    For simplicity, we'll use the same database but with rollback.
    """
    session_manager = get_session_manager()
    async with session_manager.session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create a test HTTP client."""
    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
