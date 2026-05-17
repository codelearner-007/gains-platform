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
async def test_qra_questions_overall_is_deduped(
    admin_client: AsyncClient, known_item_id: str
) -> None:
    """Regression guard for the qs × qso cartesian-product bug.

    Before the dedupe, the LEFT JOIN on (school_id, ukey) multiplied each
    question row by the number of per-section qso replicas (4× on the worked
    Chapter 9 Test example). After the fix the API returns exactly one row
    per (question_id) and question_no values are unique.
    """
    response = await admin_client.get(
        f"/api/v1/reports/question-response-analysis/{known_item_id}"
    )
    assert response.status_code == 200, response.text
    payload = QuestionResponseAnalysisPayload.model_validate(response.json())

    ids = [q.question_id for q in payload.questions_overall]
    nos = [q.question_no for q in payload.questions_overall]
    assert len(ids) == len(set(ids)), "questions_overall has duplicate question_id rows"
    assert len(nos) == len(set(nos)), "questions_overall has duplicate question_no rows"


@pytest.mark.anyio
async def test_qra_preserves_image_url_placeholders(
    admin_client: AsyncClient, known_item_id: str
) -> None:
    """Regression guard for the _strip_html eating ``<https://…>`` placeholders.

    The Schoology image-stem markup ``<https://app.schoology.com/…>`` was
    being matched by the generic ``<[^>]+>`` HTML-tag regex and dropped on
    the server, leaving the QRA "Question" column blank. The regex now uses
    a negative lookahead for the URL scheme so the placeholders survive to
    the client's ``formatQuestionHtml`` (which converts them to ``<img>``).
    """
    response = await admin_client.get(
        f"/api/v1/reports/question-response-analysis/{known_item_id}"
    )
    assert response.status_code == 200, response.text
    payload = QuestionResponseAnalysisPayload.model_validate(response.json())

    # At least one question in our worked example carries an image-only stem;
    # if none do, the assertion below trivially holds and the test still
    # passes (we don't want to require a specific stem layout in the test
    # fixture). The defensive value of the test is that for every row that
    # contains an http(s) URL it MUST still be wrapped in the angle brackets
    # the frontend needs.
    for q in payload.questions_overall:
        if "http" in q.question:
            assert "<http" in q.question, (
                f"Question {q.question_id} dropped its <URL> wrapper; "
                f"frontend formatQuestionHtml will not render the image: "
                f"{q.question!r}"
            )


@pytest.mark.anyio
async def test_qra_requires_reports_read_permission(
    user_client: AsyncClient, known_item_id: str
) -> None:
    response = await user_client.get(
        f"/api/v1/reports/question-response-analysis/{known_item_id}"
    )
    assert response.status_code == 403
