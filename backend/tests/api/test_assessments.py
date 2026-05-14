"""Tests for the assessment list and drill-down endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_list_assessments_returns_items(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/api/v1/assessments")
    assert response.status_code == 200
    items = response.json()
    assert isinstance(items, list)
    assert len(items) > 0
    first = items[0]
    assert "item_id" in first
    assert "item_name" in first


@pytest.mark.anyio
async def test_list_assessments_with_subject_filter(admin_client: AsyncClient) -> None:
    # Mathematics is one of the subjects in dim_subject for Athenian
    response = await admin_client.get(
        "/api/v1/assessments", params={"subject": "Mathematics"}
    )
    assert response.status_code == 200
    items = response.json()
    for item in items:
        # filter is honoured for items that have a subject mapping
        if item.get("subject"):
            assert item["subject"] == "Mathematics"


@pytest.mark.anyio
async def test_list_assessments_with_session_filter(admin_client: AsyncClient) -> None:
    response = await admin_client.get(
        "/api/v1/assessments", params={"session": "2025-26"}
    )
    assert response.status_code == 200
    items = response.json()
    for item in items:
        if item.get("session"):
            assert item["session"] == "2025-26"


@pytest.mark.anyio
async def test_get_assessment(
    admin_client: AsyncClient, known_item_id: str
) -> None:
    response = await admin_client.get(f"/api/v1/assessments/{known_item_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["item_id"] == known_item_id
    assert "school_id" in body


@pytest.mark.anyio
async def test_get_assessment_summary(
    admin_client: AsyncClient, known_item_id: str
) -> None:
    response = await admin_client.get(
        f"/api/v1/assessments/{known_item_id}/summary"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["item_id"] == known_item_id
    assert body["total_questions"] >= 0
    assert 0.0 <= body["grade_average"] <= 1.0001


@pytest.mark.anyio
async def test_get_assessment_questions(
    admin_client: AsyncClient, known_item_id: str
) -> None:
    response = await admin_client.get(
        f"/api/v1/assessments/{known_item_id}/questions"
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)


@pytest.mark.anyio
async def test_get_assessment_standards(
    admin_client: AsyncClient, known_item_id: str
) -> None:
    response = await admin_client.get(
        f"/api/v1/assessments/{known_item_id}/standards"
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.anyio
async def test_get_assessment_incorrect_choices(
    admin_client: AsyncClient, known_item_id: str
) -> None:
    response = await admin_client.get(
        f"/api/v1/assessments/{known_item_id}/incorrect-choices"
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.anyio
async def test_assessments_requires_reports_read(user_client: AsyncClient) -> None:
    response = await user_client.get("/api/v1/assessments")
    assert response.status_code == 403


@pytest.mark.anyio
async def test_get_unknown_assessment_returns_404(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.get("/api/v1/assessments/0000000000")
    assert response.status_code == 404
