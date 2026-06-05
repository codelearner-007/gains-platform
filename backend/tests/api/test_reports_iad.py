"""IAD endpoint smoke + parity tests.

Specifically regression-tests the standards-completeness defect: legacy
Schoology tags Q2 of "Chapter 9 Test" (item 8359960427, question 2269599902)
with FOUR distinct standards, but `cube_repository.get_question_overall`
used `MAX(standards)` / `DISTINCT ON (ukey)` which collapsed the array to
one alphabetic-greatest standard. Fixed in 2026-05 by switching to
`STRING_AGG` against `dim_question_data`.
"""

from __future__ import annotations

import pytest
import psycopg2
from httpx import AsyncClient

from app.schemas.reports import IncorrectAnswerDetailsPayload


CHAPTER_9_TEST_ITEM = "8359960427"
CHAPTER_9_TEST_Q2 = "2269599902"


def _item_has_question(item_id: str, question_id: str) -> bool:
    """Skip-fast guard for environments that haven't loaded this fixture."""
    conn = psycopg2.connect(
        "postgresql://postgres:postgres@127.0.0.1:56322/postgres"
    )
    try:
        with conn.cursor() as c:
            c.execute("SET row_security = off")
            c.execute(
                """
                SELECT 1
                FROM dim_question_data
                WHERE item_id = %s AND question_id = %s
                LIMIT 1
                """,
                (item_id, question_id),
            )
            return c.fetchone() is not None
    finally:
        conn.close()


@pytest.mark.anyio
async def test_iad_returns_all_standards_for_multi_aligned_question(
    admin_client: AsyncClient,
) -> None:
    """Regression for the standards-completeness defect.

    Q2 of Chapter 9 Test is tagged with 4 standards in Schoology
    (verifiable in the raw Question-Data CSV). The fixed IAD query
    must return all 4 newline-joined; the broken `MAX(standards)`
    version returned only `MA.9-12.MAFS.912.N-RN.1.2`.
    """
    if not _item_has_question(CHAPTER_9_TEST_ITEM, CHAPTER_9_TEST_Q2):
        pytest.skip(
            "Chapter 9 Test Q2 fixture not loaded — pipeline must run first."
        )

    response = await admin_client.get(
        f"/api/v1/reports/incorrect-answer-details/"
        f"{CHAPTER_9_TEST_ITEM}/{CHAPTER_9_TEST_Q2}"
    )
    assert response.status_code == 200, response.text

    payload = IncorrectAnswerDetailsPayload.model_validate(response.json())
    assert payload.question.question_id == CHAPTER_9_TEST_Q2

    standards = [
        s.strip()
        for s in payload.question.standards.split("\n")
        if s.strip()
    ]

    expected = {
        "AI.MA.912.NSO.1.4",
        "MA.9-12.MAFS.912.N-Q.1.3",
        "MA.9-12.MAFS.912.N-RN.1.2",
        "MA.912.NSO.1.4",
    }
    assert set(standards) == expected, (
        f"Expected the four Schoology-tagged standards on Q2 of Chapter 9 "
        f"Test, got {standards!r}. This regression check guards against the "
        f"old `MAX(standards)` collapse — see "
        f".planning/audit/reports-parity/05_standards_completeness_defect.md"
    )
    # Newline-joined string lets the frontend render one code per line.
    assert "\n" in payload.question.standards


@pytest.mark.anyio
async def test_iad_returns_total_incorrect_choices(
    admin_client: AsyncClient,
) -> None:
    """6th KPI tile: Total Incorrect Choices =
    DISTINCTCOUNT(fact_student_submission[Answer_Submission]).

    Legacy DAX (``04_dax_measures.csv:405``) has no ``[Score]=0`` filter,
    so the DISTINCTCOUNT spans ALL distinct answer submissions for the
    question — including the correct answer. The tile therefore equals
    the total distinct distractor rows, not just the wrong ones.
    """
    if not _item_has_question(CHAPTER_9_TEST_ITEM, CHAPTER_9_TEST_Q2):
        pytest.skip("fixture missing")

    response = await admin_client.get(
        f"/api/v1/reports/incorrect-answer-details/"
        f"{CHAPTER_9_TEST_ITEM}/{CHAPTER_9_TEST_Q2}"
    )
    assert response.status_code == 200
    payload = IncorrectAnswerDetailsPayload.model_validate(response.json())

    # `total_incorrect_choices` = DISTINCTCOUNT of all answer submissions,
    # i.e. every distinct distractor row (correct answer included).
    distinct_answer_count = len(payload.distractors)
    assert payload.kpis.total_incorrect_choices == distinct_answer_count
    assert payload.kpis.total_incorrect_choices == payload.kpis.distinct_answers
    assert payload.kpis.total_incorrect_choices >= 1
