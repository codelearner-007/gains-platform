"""Verify multi-tenant RLS isolation.

The Phase-5 middleware enforces tenant scoping by:

1. Switching the session role to ``authenticated`` (which does not bypass RLS).
2. Setting the ``app.current_school_id`` GUC to the user's tenant.

This test confirms that:
- A super_admin scoped to Athenian sees Athenian data.
- A super_admin scoped to a non-existent / different tenant via the
  ``?school_id=<uuid>`` override sees no data (RLS blocks every cube row).
"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.dependencies import get_current_user
from app.main import app

from .conftest import make_user_override


@pytest.mark.anyio
async def test_default_scope_returns_athenian_data(
    admin_client: AsyncClient,
) -> None:
    """Default fallback (no ?school_id) maps to Athenian; should see data."""
    response = await admin_client.get("/api/v1/assessments")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 0


@pytest.mark.anyio
async def test_explicit_unknown_tenant_returns_empty(
    admin_client: AsyncClient,
) -> None:
    """Override to a random UUID — RLS should hide all rows."""
    fake_school = str(uuid.uuid4())
    response = await admin_client.get(
        "/api/v1/assessments", params={"school_id": fake_school}
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 0, (
        f"RLS should reject rows for unknown school {fake_school}, "
        f"but got {len(body)} items"
    )


@pytest.mark.anyio
async def test_explicit_athenian_tenant_returns_data(
    admin_client: AsyncClient, athenian_school_id: str
) -> None:
    """Override to the Athenian UUID explicitly — must still see data."""
    response = await admin_client.get(
        "/api/v1/assessments", params={"school_id": athenian_school_id}
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 0


@pytest.mark.anyio
async def test_unknown_tenant_returns_404_for_qra(
    admin_client: AsyncClient, known_item_id: str
) -> None:
    """An item that exists for Athenian must 404 when the session is scoped
    to a different tenant (RLS hides the dim_item row)."""
    fake_school = str(uuid.uuid4())
    response = await admin_client.get(
        f"/api/v1/reports/question-response-analysis/{known_item_id}",
        params={"school_id": fake_school},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Claim-driven membership isolation (the Phase-1 control-plane behaviour).
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def member_of_athenian_client(
    athenian_school_id: str,
) -> AsyncGenerator[AsyncClient, None]:
    """A non-admin member whose ONLY school is Athenian (via JWT claim)."""
    override = make_user_override(
        permissions=["reports:read"],
        role="user",
        hierarchy=100,
        school_ids=[athenian_school_id],
        primary_school_id=athenian_school_id,
        user_id="00000000-0000-0000-0000-000000000001",
    )
    app.dependency_overrides[get_current_user] = override
    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides = {}


@pytest.mark.anyio
async def test_member_sees_own_school_via_claim(
    member_of_athenian_client: AsyncClient,
) -> None:
    """A member with primary_school_id=Athenian sees Athenian data with no
    ?school_id param — resolution comes from the JWT claim, not the fallback."""
    response = await member_of_athenian_client.get("/api/v1/assessments")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 0


@pytest.mark.anyio
async def test_member_cannot_scope_to_foreign_school(
    member_of_athenian_client: AsyncClient,
) -> None:
    """A member explicitly requesting a school they don't belong to is denied
    with 403 — not silently downgraded to their own tenant."""
    foreign = str(uuid.uuid4())
    response = await member_of_athenian_client.get(
        "/api/v1/assessments", params={"school_id": foreign}
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_member_with_no_school_sees_nothing() -> None:
    """A member with no membership and no override resolves to no tenant —
    RLS fails closed and returns zero rows."""
    override = make_user_override(
        permissions=["reports:read"],
        role="user",
        hierarchy=100,
        school_ids=[],
        primary_school_id=None,
    )
    app.dependency_overrides[get_current_user] = override
    transport = httpx.ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/assessments")
            assert response.status_code == 200
            assert response.json() == []
    finally:
        app.dependency_overrides = {}
