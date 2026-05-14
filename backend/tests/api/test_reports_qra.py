"""Tests for the composed Question-Response-Analysis endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.schemas.reports import QuestionResponseAnalysisPayload


@pytest.mark.anyio
async def test_qra_returns_full_payload(
    admin_client: AsyncClient, known_item_id: str
) -> None:
    response = await admin_client.get(
        f"/api/v1/reports/question-response-analysis/{known_item_id}"
    )
    assert response.status_code == 200, response.text

    # Validates against the Pydantic schema and therefore the dataset.ts contract
    payload = QuestionResponseAnalysisPayload.model_validate(response.json())

    # Assessment metadata
    assert payload.assessment.item_id == known_item_id
    assert payload.assessment.item_name
    assert payload.assessment.school_id

    # KPIs are sane
    assert 0.0 <= payload.kpis.grade_average <= 1.0
    assert payload.kpis.grade_average_pct.endswith("%")
    assert payload.kpis.total_students > 0
    assert payload.kpis.total_questions > 0
    assert payload.kpis.total_possible_point >= 0
    assert payload.kpis.total_score >= 0

    # Students
    assert isinstance(payload.students, list)
    assert len(payload.students) > 0
    for s in payload.students:
        assert s.user_uid

    # Questions
    assert isinstance(payload.questions_overall, list)
    assert len(payload.questions_overall) > 0
    for q in payload.questions_overall:
        assert q.question_id
        assert 0.0 <= q.grade_average <= 1.0001  # tolerate rounding
        assert q.position_number  # never empty (defaults to "n/a")

    # Incorrect choices
    assert isinstance(payload.incorrect_choices, list)
    if payload.incorrect_choices:
        ic = payload.incorrect_choices[0]
        assert ic.question_id
        assert ic.share_of_attempts >= 0


@pytest.mark.anyio
async def test_qra_unknown_item_returns_404(admin_client: AsyncClient) -> None:
    response = await admin_client.get(
        "/api/v1/reports/question-response-analysis/0000000000"
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_qra_requires_reports_read_permission(
    user_client: AsyncClient, known_item_id: str
) -> None:
    response = await user_client.get(
        f"/api/v1/reports/question-response-analysis/{known_item_id}"
    )
    assert response.status_code == 403
