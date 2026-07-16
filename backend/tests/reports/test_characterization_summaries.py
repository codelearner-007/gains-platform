"""Characterization anchors for the two report builders with no prior coverage.

R2 confirmed ``build_standard_summary`` and ``build_strand_summary`` are 0-hit in
the existing suite. These anchors pin CURRENT, audited behaviour captured from the
golden baseline (2026-07-17, Athenian, no filters) so a behaviour-preserving Phase
A/B refactor that drifts the standard/strand rollups is caught by a committed test
(the golden harness is scratchpad-only; this is the durable net).

READ-ONLY: uses the ``tests/reports`` rollback ``db`` fixture — never writes.
Values are "what IS", not "what should be"; a legitimate data reseed may require
re-baselining. Mirror the anchor discipline of ``test_report_calculations.py``:
extend, don't silently edit expected values.

    cd backend && ./venv/bin/python -m pytest tests/reports -q
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.reports import StandardSummaryFilters, StrandSummaryFilters
from app.services.report_service import ReportService

ATHENIAN = "019eb11c-410a-7ffb-86e6-a0294c669670"


async def scope(session: AsyncSession, school_id: str) -> None:
    """Scope the session to a school EXACTLY as ``get_db_with_rls`` does.

    The test connects as the superuser ``postgres`` (which bypasses RLS), so
    setting only the GUC is not enough for builders whose SQL has no explicit
    school predicate (standard/strand summaries rely purely on RLS). We must
    also drop to the non-bypassing ``authenticated`` role — mirroring
    ``set_school_id_for_session`` in app/middleware/rls.py.
    """
    await session.execute(text("SET LOCAL ROLE authenticated"))
    await session.execute(
        text("SELECT set_config('app.current_school_id', :s, true)"),
        {"s": school_id},
    )


def approx(a: float | None, b: float, tol: float = 5e-4) -> bool:
    return a is not None and abs(float(a) - b) <= tol


@pytest.mark.asyncio
async def test_standard_summary_athenian_anchor(db: AsyncSession):
    await scope(db, ATHENIAN)
    p = await ReportService(db).build_standard_summary(StandardSummaryFilters())

    assert len(p.standards) == 989
    assert p.kpis.total_standards == 989
    assert p.kpis.total_students == 555
    assert p.kpis.total_questions == 21614
    assert approx(p.kpis.grade_average, 0.779052)
    assert approx(p.kpis.at_target_pct, 0.509606)

    row = next(r for r in p.standards if r.cpalms_standard == "MAFS.912.A-APR.1.1")
    assert row.num_questions == 4
    assert approx(row.grade_average, 0.846528)


@pytest.mark.asyncio
async def test_standard_summary_cards_only_matches_full_rollup(db: AsyncSession):
    """``cards_only`` skips the KPI cube reads but the per-standard rollup (the
    card grid) must be byte-for-byte identical to the full path — a load-bearing
    invariant the A-phase cards_only refactor must preserve."""
    svc = ReportService(db)
    await scope(db, ATHENIAN)
    full = await svc.build_standard_summary(StandardSummaryFilters(), cards_only=False)
    await scope(db, ATHENIAN)
    cards = await svc.build_standard_summary(StandardSummaryFilters(), cards_only=True)

    assert [r.cpalms_standard for r in full.standards] == [
        r.cpalms_standard for r in cards.standards
    ]
    assert [round(r.grade_average, 6) for r in full.standards] == [
        round(r.grade_average, 6) for r in cards.standards
    ]


@pytest.mark.asyncio
async def test_strand_summary_athenian_anchor(db: AsyncSession):
    await scope(db, ATHENIAN)
    p = await ReportService(db).build_strand_summary(StrandSummaryFilters())

    assert len(p.strands_rollup) == 41
    assert len(p.standards_rollup) == 989

    row = next(
        r
        for r in p.strands_rollup
        if r.strand == "Algebra: Arithmetic with Polynomials & Rational Expressions"
    )
    assert row.num_standards == 2
    assert row.num_questions == 4
    assert approx(row.grade_average, 0.862566)
    assert approx(row.incorrect_pct, 0.137434)
