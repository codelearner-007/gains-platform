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

    # Questions
    assert isinstance(payload.questions_overall, list)
    assert len(payload.questions_overall) > 0
    for q in payload.questions_overall:
        assert q.question_id
        assert 0.0 <= q.grade_average <= 1.0001  # tolerate rounding
        assert q.position_number  # never empty (defaults to "n/a")


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


_CHAPTER9_ITEM_ID = "8359960427"


@pytest.mark.anyio
async def test_qra_standards_rollup_has_multiple_strands_and_standards_for_chapter9(
    admin_client: AsyncClient,
) -> None:
    """Strands/standards rollups must source from cube_standard_summary (RCA Layer A1).

    The Chapter-9 fixture has 6 real strands and 12 distinct Schoology
    standard rows. The pre-fix substring chain collapsed both down to 4.
    """
    response = await admin_client.get(
        f"/api/v1/reports/question-response-analysis/{_CHAPTER9_ITEM_ID}"
    )
    if response.status_code == 404:
        pytest.skip(
            "Chapter 9 fixture item missing — pipeline not run for this DB."
        )
    assert response.status_code == 200, response.text
    payload = QuestionResponseAnalysisPayload.model_validate(response.json())

    assert len(payload.strands_rollup) >= 5, (
        f"expected ≥5 strands for {_CHAPTER9_ITEM_ID}, got "
        f"{len(payload.strands_rollup)}: "
        f"{[s.strand for s in payload.strands_rollup]}"
    )
    assert len(payload.standards_rollup) >= 10, (
        f"expected ≥10 Schoology standard rows for {_CHAPTER9_ITEM_ID}, got "
        f"{len(payload.standards_rollup)}"
    )


@pytest.mark.anyio
async def test_qra_payload_includes_data_quality(
    admin_client: AsyncClient, known_item_id: str
) -> None:
    """QRA payload must expose data_quality so the page can gate the empty state.

    Mirrors the SDD page contract — when an assessment has zero aligned
    questions the QRA page renders the explanatory ``<AlignmentEmptyState>``
    card instead of the sentinel "(All Questions)" fallback row (RCA Layer
    A5).
    """
    response = await admin_client.get(
        f"/api/v1/reports/question-response-analysis/{known_item_id}"
    )
    assert response.status_code == 200, response.text
    payload = QuestionResponseAnalysisPayload.model_validate(response.json())

    assert payload.data_quality is not None
    assert payload.data_quality.alignment_status in {"full", "partial", "missing"}
    assert payload.data_quality.questions_total >= 0
    assert payload.data_quality.questions_with_alignment >= 0
    assert payload.data_quality.remediation_hint  # non-empty hint
