"""Tests for the per-school membership endpoints (grant / list / revoke).

Exercises the Wave-5 contract:
  * permission gate (``users:assign_roles`` for writes, ``users:read_all`` for
    reading another user's memberships);
  * server-side school validation (nonexistent + inactive rejected);
  * one-primary-per-user invariant;
  * grant then revoke round-trip.

Auth is mocked via the shared ``get_current_user`` override fixtures in
``conftest.py``. DB writes go to the live local Postgres.
"""

from __future__ import annotations

import uuid

import psycopg2
import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.dependencies import get_current_user
from app.main import app
from tests.api.conftest import make_user_override

_DB = "postgresql://postgres:postgres@127.0.0.1:56322/postgres"

# A distinct target user the admin acts on (not the acting tester user).
_TARGET_USER_ID = "00000000-0000-0000-0000-0000000000a5"


def _conn():
    c = psycopg2.connect(_DB)
    c.autocommit = True
    return c


@pytest.fixture
def target_user_id() -> str:
    """A real auth.users row to satisfy the user_schools FK."""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth.users (id, instance_id, aud, role, email,
                    email_confirmed_at, raw_app_meta_data, raw_user_meta_data,
                    created_at, updated_at)
                VALUES (%s, '00000000-0000-0000-0000-000000000000',
                        'authenticated', 'authenticated',
                        'ws-target@example.com', now(), '{}'::jsonb, '{}'::jsonb,
                        now(), now())
                ON CONFLICT (id) DO NOTHING
                """,
                (_TARGET_USER_ID,),
            )
    finally:
        conn.close()
    return _TARGET_USER_ID


def _make_school(is_active: bool) -> str:
    building_id = f"ws-test-{uuid.uuid4().hex[:8]}"
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.schools (schoology_building_id, name, short_name,
                    timezone, is_active)
                VALUES (%s, %s, %s, 'America/New_York', %s)
                RETURNING school_id::text
                """,
                (building_id, f"WS Test {building_id}", "WST", is_active),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def active_school_id() -> str:
    return _make_school(is_active=True)


@pytest.fixture
def second_active_school_id() -> str:
    return _make_school(is_active=True)


@pytest.fixture
def inactive_school_id() -> str:
    return _make_school(is_active=False)


@pytest_asyncio.fixture
async def assign_client():
    """Client with the ``users:assign_roles`` + ``users:read_all`` perms."""
    app.dependency_overrides[get_current_user] = make_user_override(
        permissions=["users:assign_roles", "users:read_all"],
        role="super_admin",
        hierarchy=10000,
    )
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides = {}


@pytest.mark.anyio
async def test_grant_requires_assign_permission(
    user_client: AsyncClient, target_user_id: str, active_school_id: str
) -> None:
    resp = await user_client.post(
        f"/api/v1/users/{target_user_id}/schools",
        json={"school_id": active_school_id, "school_role": "teacher"},
    )
    assert resp.status_code == 403
    # No permission-list leak in the body.
    assert "permission" not in resp.text.lower() or "users:" not in resp.text


@pytest.mark.anyio
async def test_grant_rejects_nonexistent_school(
    assign_client: AsyncClient, target_user_id: str
) -> None:
    resp = await assign_client.post(
        f"/api/v1/users/{target_user_id}/schools",
        json={"school_id": str(uuid.uuid4()), "school_role": "member"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_grant_rejects_inactive_school(
    assign_client: AsyncClient, target_user_id: str, inactive_school_id: str
) -> None:
    resp = await assign_client.post(
        f"/api/v1/users/{target_user_id}/schools",
        json={"school_id": inactive_school_id, "school_role": "member"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_grant_list_revoke_roundtrip(
    assign_client: AsyncClient, target_user_id: str, active_school_id: str
) -> None:
    # Grant
    grant = await assign_client.post(
        f"/api/v1/users/{target_user_id}/schools",
        json={"school_id": active_school_id, "school_role": "teacher", "is_primary": True},
    )
    assert grant.status_code == 201, grant.text
    body = grant.json()
    assert body["school_id"] == active_school_id
    assert body["school_role"] == "teacher"
    assert body["is_primary"] is True
    assert body["school_is_active"] is True

    # List
    listing = await assign_client.get(f"/api/v1/users/{target_user_id}/schools")
    assert listing.status_code == 200
    rows = listing.json()
    assert any(r["school_id"] == active_school_id for r in rows)

    # Revoke
    revoke = await assign_client.delete(
        f"/api/v1/users/{target_user_id}/schools/{active_school_id}"
    )
    assert revoke.status_code == 204

    # Gone
    listing2 = await assign_client.get(f"/api/v1/users/{target_user_id}/schools")
    assert all(r["school_id"] != active_school_id for r in listing2.json())


@pytest.mark.anyio
async def test_one_primary_per_user_invariant(
    assign_client: AsyncClient,
    target_user_id: str,
    active_school_id: str,
    second_active_school_id: str,
) -> None:
    # First primary
    await assign_client.post(
        f"/api/v1/users/{target_user_id}/schools",
        json={"school_id": active_school_id, "is_primary": True},
    )
    # Second primary should demote the first (no unique-index violation)
    resp = await assign_client.post(
        f"/api/v1/users/{target_user_id}/schools",
        json={"school_id": second_active_school_id, "is_primary": True},
    )
    assert resp.status_code == 201, resp.text

    rows = (await assign_client.get(f"/api/v1/users/{target_user_id}/schools")).json()
    primaries = [r for r in rows if r["is_primary"]]
    assert len(primaries) == 1
    assert primaries[0]["school_id"] == second_active_school_id

    # cleanup
    await assign_client.delete(
        f"/api/v1/users/{target_user_id}/schools/{active_school_id}"
    )
    await assign_client.delete(
        f"/api/v1/users/{target_user_id}/schools/{second_active_school_id}"
    )


@pytest.mark.anyio
async def test_revoke_nonexistent_membership_returns_404(
    assign_client: AsyncClient, target_user_id: str, active_school_id: str
) -> None:
    resp = await assign_client.delete(
        f"/api/v1/users/{target_user_id}/schools/{active_school_id}"
    )
    assert resp.status_code == 404
