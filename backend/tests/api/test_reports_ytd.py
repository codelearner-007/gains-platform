"""Tests for the YTD Longitudinal paginated matrix endpoint (PBIX ord 8/9/10).

Legacy NUMERIC parity cannot be diffed here: no school has BOTH ingested cube
data AND a legacy YTD PDF (Decision 9 — CFP/CrestWell raw exports are absent).
The achievable bar is therefore STRUCTURE (matches the CFP/CrestWell PDFs) plus
MATH SELF-CONSISTENCY on the only real tenant, Athenian: per-student Score% =
SUM(received)/SUM(possible); per-teacher subtotal = sum over its students; grand
total = sum over all teachers AND = sum over per-standard columns.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.schemas.reports import YearToDatePerformancePayload

# A real Athenian (session, grade, subject, assessment_type) longitudinal unit
# with multiple standards and multiple assessments. Tied to the current
# seed=42 / limit-per-school=100 sample: this scope yields 41 students across
# 5 assessments and 16 standard columns, and the rows are Athenian-exclusive
# (only Athenian carries per-student fact data in this sample). Re-anchored from
# the prior Grade 8 scope, which became empty under the new sample.
_SCOPE = {
    "session": "2025-26",
    "grade": "Grade 1",
    "subject": "Mathematics",
    "category": "Lesson  Assessments",
}


@pytest.mark.anyio
async def test_ytd_matrix_structure_and_self_consistency(
    admin_client: AsyncClient, athenian_school_id: str
) -> None:
    resp = await admin_client.get(
        "/api/v1/reports/year-to-date-performance",
        params={**_SCOPE, "school_id": athenian_school_id},
    )
    assert resp.status_code == 200, resp.text
    payload = YearToDatePerformancePayload.model_validate(resp.json())

    # ── Structure ────────────────────────────────────────────────────────
    assert payload.subject == "Mathematics"
    assert payload.grade == "Grade 1"
    assert payload.standards, "expected at least one standard column"
    assert payload.teacher_groups, "expected at least one teacher group"

    # Standards are de-aliased (no Schoology course-prefix duplicates like
    # AI.MA.* alongside MA.*) — one canonical label per column.
    labels = [s.standard_label for s in payload.standards]
    assert len(labels) == len(set(labels))

    gt = payload.grand_total
    eps = 1e-3

    # Legacy SSRS column order: ascending by the standard's overall Score%
    # (lowest-scoring standard first), ties broken alphabetically by label.
    def _col_score(label: str) -> float:
        tot = gt.standard_totals[label]
        return round(tot.points_received / tot.points_possible, 6) if tot.points_possible else 0.0

    assert labels == sorted(labels, key=lambda lab: (_col_score(lab), lab))

    # ── Per-student: Score% = SUM(received)/SUM(possible); cells reconcile ──
    sum_students_recv = 0.0
    sum_students_poss = 0.0
    for tg in payload.teacher_groups:
        t_recv = 0.0
        t_poss = 0.0
        for st in tg.students:
            cell_recv = sum(c.points_received for c in st.cells.values())
            cell_poss = sum(c.points_possible for c in st.cells.values())
            assert abs(cell_recv - st.points_received) < eps
            assert abs(cell_poss - st.points_possible) < eps
            expected = (
                st.points_received / st.points_possible
                if st.points_possible
                else 0.0
            )
            assert abs(expected - st.score_pct) < eps
            t_recv += st.points_received
            t_poss += st.points_possible

        # ── Per-teacher subtotal = sum over its students ──
        assert abs(t_recv - sum(
            v.points_received for v in tg.standard_subtotals.values()
        )) < eps
        assert abs(t_poss - sum(
            v.points_possible for v in tg.standard_subtotals.values()
        )) < eps
        expected_t = t_recv / t_poss if t_poss else 0.0
        assert abs(expected_t - tg.teacher_score_pct) < eps

        sum_students_recv += t_recv
        sum_students_poss += t_poss

    # ── Grand total = sum over teachers ──
    assert abs(sum_students_recv - gt.points_received) < eps
    assert abs(sum_students_poss - gt.points_possible) < eps

    # ── Grand total = sum over per-standard columns ──
    std_recv = sum(v.points_received for v in gt.standard_totals.values())
    std_poss = sum(v.points_possible for v in gt.standard_totals.values())
    assert abs(std_recv - gt.points_received) < eps
    assert abs(std_poss - gt.points_possible) < eps

    expected_grand = gt.points_received / gt.points_possible if gt.points_possible else 0.0
    assert abs(expected_grand - gt.score_pct) < eps


@pytest.mark.anyio
async def test_ytd_empty_scope_returns_empty_matrix(
    admin_client: AsyncClient, athenian_school_id: str
) -> None:
    """A scope with no data yields an empty (but well-formed) matrix."""
    resp = await admin_client.get(
        "/api/v1/reports/year-to-date-performance",
        params={
            "session": "1999-00",
            "grade": "Grade 99",
            "subject": "Nonexistent",
            "category": "Nope",
            "school_id": athenian_school_id,
        },
    )
    assert resp.status_code == 200, resp.text
    payload = YearToDatePerformancePayload.model_validate(resp.json())
    assert payload.standards == []
    assert payload.teacher_groups == []
    assert payload.grand_total.points_possible == 0
