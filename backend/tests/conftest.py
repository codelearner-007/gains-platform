"""Pytest configuration and fixtures."""

import pytest
from typing import AsyncGenerator, Dict

import httpx
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
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


@pytest.fixture
def mock_super_admin_token() -> str:
    """
    Create a mock JWT token for super_admin.

    In real tests, you would use python-jose to create valid JWTs.
    This is a placeholder for testing purposes.
    """
    # For now, return a placeholder
    # In production tests, generate a real JWT with python-jose
    return "mock-super-admin-token"


@pytest.fixture
def mock_regular_user_token() -> str:
    """
    Create a mock JWT token for regular user.

    In real tests, you would use python-jose to create valid JWTs.
    This is a placeholder for testing purposes.
    """
    return "mock-user-token"


@pytest.fixture
def auth_headers_super_admin(mock_super_admin_token: str) -> Dict[str, str]:
    """Headers with super admin token."""
    return {"Authorization": f"Bearer {mock_super_admin_token}"}


@pytest.fixture
def auth_headers_user(mock_regular_user_token: str) -> Dict[str, str]:
    """Headers with regular user token."""
    return {"Authorization": f"Bearer {mock_regular_user_token}"}
