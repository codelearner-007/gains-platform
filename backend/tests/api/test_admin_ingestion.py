"""Tests for the admin/ingestion endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_list_runs_requires_permission(user_client: AsyncClient) -> None:
    response = await user_client.get("/api/v1/admin/ingestion/runs")
    assert response.status_code == 403


@pytest.mark.anyio
async def test_list_runs_returns_list(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/api/v1/admin/ingestion/runs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.anyio
async def test_trigger_run_returns_202_and_run_id(
    admin_client: AsyncClient, athenian_school_id: str
) -> None:
    response = await admin_client.post(
        "/api/v1/admin/ingestion/trigger",
        json={"school_id": athenian_school_id, "note": "phase-5 smoke test"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert "run_id" in body
    assert body["status"] == "pending"
    run_id = body["run_id"]

    # Now read the run back
    detail = await admin_client.get(f"/api/v1/admin/ingestion/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["run_id"] == run_id


@pytest.mark.anyio
async def test_trigger_requires_trigger_permission(
    user_client: AsyncClient,
) -> None:
    response = await user_client.post(
        "/api/v1/admin/ingestion/trigger", json={}
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_get_unknown_run_returns_404(admin_client: AsyncClient) -> None:
    response = await admin_client.get(
        "/api/v1/admin/ingestion/runs/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404
