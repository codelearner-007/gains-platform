"""Tests for the /api/v1/dim/* lookup endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_list_standards_returns_global_lookup(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.get("/api/v1/dim/standards")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    # dim_standard seed = 7,958 rows
    assert len(body) >= 7000
    # Cache-Control header must be set for global lookups
    assert "max-age=3600" in response.headers.get("cache-control", "")
    first = body[0]
    assert "uniques_id" in first
    assert "identifier" in first


@pytest.mark.anyio
async def test_list_strands_returns_global_lookup(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.get("/api/v1/dim/strands")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 0
    assert "max-age=3600" in response.headers.get("cache-control", "")


@pytest.mark.anyio
async def test_list_subjects_returns_per_school_data(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.get("/api/v1/dim/subjects")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    # Athenian has 21 subjects after transformations
    assert len(body) > 0


@pytest.mark.anyio
async def test_list_grades(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/api/v1/dim/grades")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.anyio
async def test_list_sections(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/api/v1/dim/sections")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.anyio
async def test_list_sessions(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/api/v1/dim/sessions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.anyio
async def test_subjects_requires_reports_read(
    user_client: AsyncClient,
) -> None:
    response = await user_client.get("/api/v1/dim/subjects")
    assert response.status_code == 403
