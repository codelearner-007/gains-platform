"""Shared fixtures for the Phase-5 API tests.

These tests run against the live local Postgres (the same DB the FastAPI
worker connects to). They lookup an actual ``item_id`` so the assertions
match the data ingested by the transformations module.

Auth is mocked: we override ``get_current_user`` with an in-test fixture so
the tests don't need a real JWT.
"""

from __future__ import annotations

from typing import AsyncGenerator, List, Optional

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient

import app.db.session as session_module
from app.core.dependencies import get_current_user
from app.main import app
from app.schemas.auth import CurrentUser


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


_TEST_USER_ID = "00000000-0000-0000-0000-000000000001"


def _ensure_test_user() -> None:
    """Insert a stub user in auth.users so audit-log FKs are satisfied.

    Audit writes from the admin tests reference ``current_user.user_id``;
    those rows must exist in ``auth.users`` to clear the FK. We do this
    once per test session.
    """
    import psycopg2

    conn = psycopg2.connect(
        "postgresql://postgres:postgres@127.0.0.1:56322/postgres"
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth.users (id, instance_id, aud, role, email, email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at)
                VALUES (%s, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',
                        'phase5-tester@example.com', now(), '{}'::jsonb, '{}'::jsonb, now(), now())
                ON CONFLICT (id) DO NOTHING
                """,
                (_TEST_USER_ID,),
            )
    finally:
        conn.close()


@pytest_asyncio.fixture(autouse=True)
async def _reset_session_manager() -> AsyncGenerator[None, None]:
    """Force a fresh SQLAlchemy engine per test.

    pytest-asyncio creates a new event loop per test on Windows; a singleton
    engine bound to a previous loop trips ``ProactorEventLoop`` errors when
    the new loop tries to issue I/O. Disposing the engine before each test
    keeps every test isolated.
    """
    _ensure_test_user()
    if session_module._session_manager is not None:
        try:
            await session_module._session_manager.close()
        except Exception:
            pass
        session_module._session_manager = None
    yield
    if session_module._session_manager is not None:
        try:
            await session_module._session_manager.close()
        except Exception:
            pass
        session_module._session_manager = None


def make_user_override(
    permissions: Optional[List[str]] = None,
    role: str = "super_admin",
    hierarchy: int = 10000,
):
    """Build an async dependency that returns a mock CurrentUser."""

    async def _override() -> CurrentUser:
        return CurrentUser(
            user_id="00000000-0000-0000-0000-000000000001",
            email="phase5-tester@example.com",
            user_role=role,
            hierarchy_level=hierarchy,
            permissions=permissions or [],
        )

    return _override


@pytest.fixture
def super_admin_override():
    """Super-admin with every permission this phase introduces."""
    return make_user_override(
        permissions=[
            "reports:read",
            "schools:create",
            "schools:update",
            "schools:read_all",
            "ingestion:trigger",
            "ingestion:read",
            "audit:read",
        ],
        role="super_admin",
        hierarchy=10000,
    )


@pytest.fixture
def regular_user_override():
    """Regular user with no Phase-5 permissions."""
    return make_user_override(permissions=[], role="user", hierarchy=100)


@pytest.fixture
async def admin_client(super_admin_override) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client authenticated as a Phase-5 super_admin."""
    app.dependency_overrides[get_current_user] = super_admin_override
    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides = {}


@pytest.fixture
async def user_client(regular_user_override) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client authenticated as a regular user (no Phase-5 perms)."""
    app.dependency_overrides[get_current_user] = regular_user_override
    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides = {}


@pytest.fixture
def known_item_id() -> str:
    """A known item_id with cube data populated. Look up dynamically.

    The transformations module produced 33 items; we pick one with a
    non-trivial cube_school_summary entry.
    """
    import psycopg2

    conn = psycopg2.connect(
        "postgresql://postgres:postgres@127.0.0.1:56322/postgres"
    )
    try:
        with conn.cursor() as c:
            c.execute("SET row_security = off")
            c.execute(
                """
                SELECT cs.item_id
                FROM cube_school_summary cs
                JOIN cube_grade_summary cg
                  ON cs.school_id = cg.school_id AND cs.item_id = cg.item_id
                WHERE cs.item_id IS NOT NULL
                  AND cs.total_students > 0
                  AND cs.total_questions > 0
                ORDER BY cs.total_students DESC
                LIMIT 1
                """
            )
            row = c.fetchone()
            if not row:
                pytest.skip("No populated cube_school_summary rows for tests")
            return row[0]
    finally:
        conn.close()


@pytest.fixture
def athenian_school_id() -> str:
    import psycopg2

    conn = psycopg2.connect(
        "postgresql://postgres:postgres@127.0.0.1:56322/postgres"
    )
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT school_id::text FROM public.schools "
                "WHERE schoology_building_id = '186370968'"
            )
            row = c.fetchone()
            if not row:
                pytest.skip("Athenian school not seeded")
            return row[0]
    finally:
        conn.close()
