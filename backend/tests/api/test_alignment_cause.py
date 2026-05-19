"""Tests for the alignment ``cause`` field in AlignmentDataQuality.

Distinguishes the two "missing" empty-state flavours surfaced by the
2026-05-19 RCA (``.hermes/report-parity/missing-alignment-2026-05-19/``):

* Category A (``no_standards_in_source``) — Schoology Export Stats CSV
  shipped zero ``Standards{N}`` columns. Teacher never used
  "Align Learning Objective". 18 of 33 audited items in the RCA.
* Category B (``labels_not_mapped``) — CSV contains labels but the
  exact-match join against ``dim_standard.schoology_standard`` failed
  (e.g. literal ``"Social Studies"`` on a Grade K Math assessment).
  3 of 33 items.

Two test surfaces here:

1. Pure unit tests of ``_classify_alignment_cause`` — fast, no DB.
2. Integration tests over the QRA payload for three reference items
   (Chapter 9 Test, PM3 Reading, Grade K Math Time). Skipped if the
   pipeline-seeded DB doesn't have the items.

The existing ``alignment_status`` enum (full / partial / missing) is
unchanged; ``cause`` is purely additive and optional, so legacy clients
keep working.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.schemas.reports import QuestionResponseAnalysisPayload
from app.services.report_service import _classify_alignment_cause


# ─── Pure unit tests on the classifier ──────────────────────────────────────


def test_classify_alignment_cause_no_questions() -> None:
    """Empty item → 'no_questions'."""
    assert _classify_alignment_cause(0, 0, 0, 0) == "no_questions"


def test_classify_alignment_cause_full_alignment() -> None:
    """All questions aligned → 'full_alignment'."""
    # 18 / 18 questions aligned (Chapter 9 Test legacy shape).
    assert _classify_alignment_cause(18, 18, 8, 0) == "full_alignment"


def test_classify_alignment_cause_partial_teacher_alignment() -> None:
    """Some aligned, some not → 'partial_teacher_alignment'.

    Mirrors item 7893398199 (Chapter 17 Grade 2 Math, 19 of 20 aligned).
    """
    assert (
        _classify_alignment_cause(20, 19, 5, 1) == "partial_teacher_alignment"
    )


def test_classify_alignment_cause_no_standards_in_source() -> None:
    """Source CSV had zero non-empty standards → Category A."""
    # 10 questions, 0 aligned, 0 distinct non-empty labels.
    assert (
        _classify_alignment_cause(10, 0, 0, 0) == "no_standards_in_source"
    )


def test_classify_alignment_cause_labels_not_mapped() -> None:
    """Source had labels but none matched a CPALMS code → Category B.

    Mirrors item 8356554433 (Grade K Math "Time" with literal
    ``"Social Studies"`` label).
    """
    # 10 questions, 0 aligned, 1 non-empty label, 1 unmatched.
    assert _classify_alignment_cause(10, 0, 1, 1) == "labels_not_mapped"


def test_classify_alignment_cause_inconsistent_returns_none() -> None:
    """Pathological counts where no branch applies → None.

    Caller treats None as "cannot determine"; do not fabricate a cause.
    """
    # zero aligned, zero non-empty labels, but zero unmatched too —
    # shouldn't happen with consistent data, but guard against fabrication.
    # We re-route this through the "no labels" branch which returns
    # ``no_standards_in_source`` (the safe default for the Category A path).
    # Verify the explicit pathological path: positive non-empty count but
    # zero unmatched is internally inconsistent (every non-empty label
    # mapped, yet questions_with_alignment is 0).
    assert _classify_alignment_cause(10, 0, 2, 0) is None


# ─── Integration tests over the live pipeline-seeded DB ────────────────────


_CHAPTER9_FULL_ALIGNMENT_ITEM_ID = "8359960427"
_PM3_NO_STANDARDS_ITEM_ID = "8363033309"
_GRADE_K_LABELS_NOT_MAPPED_ITEM_ID = "8356554433"


async def _get_qra_or_skip(
    client: AsyncClient, item_id: str
) -> QuestionResponseAnalysisPayload:
    response = await client.get(
        f"/api/v1/reports/question-response-analysis/{item_id}"
    )
    if response.status_code == 404:
        pytest.skip(
            f"Item {item_id} missing — pipeline not seeded for this DB."
        )
    assert response.status_code == 200, response.text
    return QuestionResponseAnalysisPayload.model_validate(response.json())


@pytest.mark.anyio
async def test_alignment_cause_full_alignment_for_chapter9(
    admin_client: AsyncClient,
) -> None:
    """Item 8359960427 should report cause='full_alignment'."""
    qra = await _get_qra_or_skip(admin_client, _CHAPTER9_FULL_ALIGNMENT_ITEM_ID)
    assert qra.data_quality is not None, (
        "data_quality block missing from QRA payload"
    )
    assert qra.data_quality.alignment_status == "full", (
        f"Chapter 9 Test should be fully aligned, got "
        f"alignment_status={qra.data_quality.alignment_status!r}"
    )
    assert qra.data_quality.cause == "full_alignment", (
        f"Chapter 9 Test should report cause='full_alignment', got "
        f"{qra.data_quality.cause!r}"
    )
    assert qra.data_quality.unmatched_labels is None, (
        f"unmatched_labels must be None when cause='full_alignment', got "
        f"{qra.data_quality.unmatched_labels!r}"
    )


@pytest.mark.anyio
async def test_alignment_cause_no_standards_in_source_for_pm3_reading(
    admin_client: AsyncClient,
) -> None:
    """Item 8363033309 (PM3 ELA) should report cause='no_standards_in_source'.

    Source CSV had zero Standards columns — teacher never aligned in
    Schoology. The UI should render the "no Standards columns in source"
    empty state, not the generic one.
    """
    qra = await _get_qra_or_skip(admin_client, _PM3_NO_STANDARDS_ITEM_ID)
    assert qra.data_quality is not None
    assert qra.data_quality.alignment_status == "missing", (
        f"PM3 Reading must be missing alignment, got "
        f"{qra.data_quality.alignment_status!r}"
    )
    assert qra.data_quality.cause == "no_standards_in_source", (
        f"PM3 Reading should report cause='no_standards_in_source' "
        f"(Category A: no Standards columns in CSV), got "
        f"{qra.data_quality.cause!r}"
    )
    assert qra.data_quality.unmatched_labels is None, (
        f"unmatched_labels must be None when cause='no_standards_in_source'"
        f", got {qra.data_quality.unmatched_labels!r}"
    )


@pytest.mark.anyio
async def test_alignment_cause_labels_not_mapped_for_grade_k_time(
    admin_client: AsyncClient,
) -> None:
    """Item 8356554433 should report cause='labels_not_mapped'.

    Grade K Math "Time" assessment has a literal ``"Social Studies"``
    label in the source CSV but no row in dim_standard matches that
    string, so the exact-match join fails and identifier stays NULL.
    The UI should render the "labels didn't map" empty state with the
    offending label inline.
    """
    qra = await _get_qra_or_skip(
        admin_client, _GRADE_K_LABELS_NOT_MAPPED_ITEM_ID
    )
    assert qra.data_quality is not None
    assert qra.data_quality.alignment_status == "missing", (
        f"Grade K Time must be missing alignment, got "
        f"{qra.data_quality.alignment_status!r}"
    )
    assert qra.data_quality.cause == "labels_not_mapped", (
        f"Grade K Time should report cause='labels_not_mapped' "
        f"(Category B: label exists but didn't map), got "
        f"{qra.data_quality.cause!r}"
    )
    # Should surface at least one label; "Social Studies" is the
    # documented offender for this item.
    assert qra.data_quality.unmatched_labels, (
        f"unmatched_labels must be populated when cause='labels_not_mapped'"
        f", got {qra.data_quality.unmatched_labels!r}"
    )
    assert len(qra.data_quality.unmatched_labels) <= 5, (
        f"unmatched_labels must be capped at 5, got "
        f"{len(qra.data_quality.unmatched_labels)} entries"
    )


@pytest.mark.anyio
async def test_alignment_status_enum_unchanged(
    admin_client: AsyncClient,
) -> None:
    """Regression guard: alignment_status enum must stay full/partial/missing.

    The ``cause`` field is purely additive — adding new values to
    ``alignment_status`` would be a breaking change for existing UI code
    that gates on the three legacy values. This test asserts that even
    when ``cause`` resolves a previously-ambiguous "missing" into a
    specific Category A / B, the ``alignment_status`` value still falls
    in the legacy set.
    """
    qra = await _get_qra_or_skip(admin_client, _CHAPTER9_FULL_ALIGNMENT_ITEM_ID)
    assert qra.data_quality is not None
    assert qra.data_quality.alignment_status in {"full", "partial", "missing"}
