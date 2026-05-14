"""Tests for the admin/schools endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_list_schools_requires_permission(user_client: AsyncClient) -> None:
    response = await user_client.get("/api/v1/admin/schools")
    assert response.status_code == 403


@pytest.mark.anyio
async def test_list_schools_returns_athenian(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/api/v1/admin/schools")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    names = [r.get("name") for r in body]
    assert any("Athenian" in (n or "") for n in names)


@pytest.mark.anyio
async def test_get_school_by_id(
    admin_client: AsyncClient, athenian_school_id: str
) -> None:
    response = await admin_client.get(
        f"/api/v1/admin/schools/{athenian_school_id}"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["school_id"] == athenian_school_id


@pytest.mark.anyio
async def test_create_and_update_school(admin_client: AsyncClient) -> None:
    # Use a random building id so this test can run repeatedly
    building_id = f"phase5-test-{uuid.uuid4().hex[:8]}"
    payload = {
        "schoology_building_id": building_id,
        "name": "Phase 5 Test School",
        "short_name": "P5",
        "current_session": "2025-26",
        "timezone": "America/New_York",
    }
    create_resp = await admin_client.post("/api/v1/admin/schools", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["schoology_building_id"] == building_id
    assert created["name"] == "Phase 5 Test School"
    school_id = created["school_id"]

    # Duplicate POST should return 409
    dup_resp = await admin_client.post("/api/v1/admin/schools", json=payload)
    assert dup_resp.status_code == 409

    # Update
    update_resp = await admin_client.put(
        f"/api/v1/admin/schools/{school_id}",
        json={"name": "Phase 5 Test School (renamed)", "is_active": False},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["name"] == "Phase 5 Test School (renamed)"
    assert updated["is_active"] is False


@pytest.mark.anyio
async def test_create_school_requires_create_permission(
    user_client: AsyncClient,
) -> None:
    response = await user_client.post(
        "/api/v1/admin/schools",
        json={
            "schoology_building_id": "x-test",
            "name": "X",
            "short_name": "X",
        },
    )
    assert response.status_code == 403
