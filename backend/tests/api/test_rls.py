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

import pytest
from httpx import AsyncClient


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
