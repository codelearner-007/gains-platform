"""Forward View report regression suite — READ-ONLY.

Same discipline as ``test_report_calculations.py`` / ``test_student_reports.py``:
open a session, scope it to a school via the RLS GUC exactly as a request does,
call ``ReportService.build_forward_view``, assert, and roll back (the dev DB is
never mutated). Verified anchors come from ``.planning/forward-view/BASELINE.md``.

Run (safe — never truncates):
    cd backend && ./venv/bin/python -m pytest tests/reports/test_forward_view.py -q

NEVER run pytest outside ``tests/reports`` — the pipeline/ingestion conftests
TRUNCATE the dev DB.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.reports import ForwardViewFilters
from app.services.reports import ReportService

# ── School ids (BASELINE.md) ────────────────────────────────────────────────
ATHENIAN = "019eb11c-410a-7ffb-86e6-a0294c669670"
CFP = "019eb11c-413b-7a66-a7d8-a18f14736ede"
CRESTWELL = "019eb11c-413c-7ed9-872e-0fe5e9a947b6"

# ── Anchor slice (Athenian · 2024-25 · Math · Grade 3 · threshold 0.7) ──────
SESSION = "2024-25"
SUBJECT = "Math"
GRADE = "Grade 3"
THRESHOLD = 0.7

# Whitespace normalisation applied by ``get_forward_view_rollup`` to
# assessment_type (→ period) and item_name (→ unit): btrim + collapse runs.
_NORM = r"btrim(regexp_replace({col}, '\s+', ' ', 'g'))"


async def scope(session: AsyncSession, school_id: str) -> None:
    """Scope EXACTLY as ``get_db_with_rls`` does: drop to ``authenticated`` (so
    RLS is enforced, not bypassed as a superuser would) and set the tenant GUC
    (SET LOCAL — lives only inside this transaction, which the fixture rolls
    back)."""
    await session.execute(text("SET LOCAL ROLE authenticated"))
    await session.execute(
        text("SELECT set_config('app.current_school_id', :s, true)"),
        {"s": school_id},
    )


async def _athenian_math_g3(
    db: AsyncSession, threshold: float = THRESHOLD
) -> "object":
    """Build the anchor Forward View payload (Athenian · Math · Grade 3)."""
    await scope(db, ATHENIAN)
    return await ReportService(db).build_forward_view(
        ForwardViewFilters(
            session=SESSION, subject=SUBJECT, grade=GRADE, threshold=threshold
        )
    )


def _body_cells(payload) -> list:
    """Flatten (period, unit, row) triples of the period→unit→standard body."""
    return [
        (p, u, r)
        for p in payload.periods
        for u in p.units
        for r in u.standards
    ]


# ════════════════════════════════════════════════════════════════════════════
# a. CROSS-CHECK POOLED MATH — independent re-derivation from the FACT
#    (fact_student_submission is a DIFFERENT code path than cube_user_summary).
# ════════════════════════════════════════════════════════════════════════════
class TestPooledMathCrossCheck:
    async def test_worst_flagged_cell_matches_raw_fact(self, db: AsyncSession):
        payload = await _athenian_math_g3(db)
        cells = _body_cells(payload)
        flagged = [(p, u, r) for (p, u, r) in cells if r.is_troublesome]
        assert flagged, "expected at least one flagged cell in the anchor slice"

        # Worst flagged cell = lowest pooled % correct among flagged rows.
        period, unit, row = min(flagged, key=lambda t: t[2].grade_average)

        # Re-derive pooled SUM(points_received)/SUM(points_possible) for the
        # SAME (period, unit, standard) directly from fact_student_submission,
        # applying the identical whitespace normalisation to assessment_type
        # (=period) and item_name (=unit). Columns confirmed against
        # app/transformations/07_facts/fact_student_submission.sql.
        sql = text(
            f"""
            SELECT SUM(points_received)::float AS score,
                   SUM(points_possible)::float AS possible
            FROM fact_student_submission
            WHERE session = :sess AND subject = :subj AND grade = :grade
              AND {_NORM.format(col='assessment_type')} = :period
              AND {_NORM.format(col='item_name')}       = :unit
              AND standard = :std
            """
        )
        r = (
            await db.execute(
                sql,
                {
                    "sess": SESSION,
                    "subj": SUBJECT,
                    "grade": GRADE,
                    "period": period.period,
                    "unit": unit.unit,
                    "std": row.schoology_standard,
                },
            )
        ).one()
        assert r.possible and r.possible > 0
        fact_pct = r.score / r.possible

        # The cube's denominator is SUM(dim_question_data.total_points); this
        # independent check uses fact.points_possible. Empirically the two
        # coincide for this cell (residual ~2e-7), so 5e-3 is comfortable; the
        # numerator (SUM points_received) is a shared source, hence exact.
        assert abs(fact_pct - row.grade_average) <= 5e-3, (
            f"{period.period}/{unit.unit}/{row.schoology_standard}: "
            f"fact {fact_pct} vs payload {row.grade_average}"
        )
        # Numerator sanity: cube total_score = round(Σ points_received) re-summed
        # over base rows; agrees with the raw fact Σ to within rounding slack.
        assert abs(r.score - row.total_score) <= 0.5

    async def test_worst_body_cell_anchor(self, db: AsyncSession):
        # BASELINE: worst body cell = MA.3.NSO.1.2 @ 51.1% (in "Chapter 1").
        payload = await _athenian_math_g3(db)
        cells = _body_cells(payload)
        _, unit, row = min(
            cells,
            key=lambda t: t[2].grade_average
            if t[2].grade_average is not None
            else 2.0,
        )
        assert row.schoology_standard == "MA.3.NSO.1.2"
        assert abs(row.grade_average - 0.5108) <= 5e-3
        assert row.grade_average_pct == "51.1%"


# ════════════════════════════════════════════════════════════════════════════
# b. FLAG SEMANTICS + MONOTONICITY
# ════════════════════════════════════════════════════════════════════════════
class TestFlagSemantics:
    async def test_per_row_flag_is_pct_below_threshold(self, db: AsyncSession):
        payload = await _athenian_math_g3(db)
        for _, _, r in _body_cells(payload):
            expected = r.grade_average is not None and r.grade_average < THRESHOLD
            assert r.is_troublesome is expected, (
                f"{r.schoology_standard}: ga={r.grade_average} flag={r.is_troublesome}"
            )
            # grade_average == None ⇒ never flagged (0 possible points).
            if r.grade_average is None:
                assert r.is_troublesome is False

    async def test_flagged_standards_is_distinct_pooled_below_threshold(
        self, db: AsyncSession
    ):
        payload = await _athenian_math_g3(db)
        # Independently pool each standard across the WHOLE body scope (sum of
        # per-cell sums), then count distinct codes whose pooled % < threshold.
        pools: dict[str, list[float]] = {}
        for _, _, r in _body_cells(payload):
            acc = pools.setdefault(r.schoology_standard, [0.0, 0.0])
            acc[0] += r.total_score
            acc[1] += r.total_possible_point
        assessed = [c for c, (_, poss) in pools.items() if poss > 0]
        flagged = [
            c for c, (score, poss) in pools.items() if poss > 0 and score / poss < THRESHOLD
        ]
        assert payload.kpis.standards_assessed == len(assessed)
        assert payload.kpis.flagged_standards == len(flagged)
        # BASELINE anchors @70%.
        assert payload.kpis.standards_assessed == 37
        assert payload.kpis.flagged_standards == 3
        assert payload.kpis.flag_rate_pct == "8.1%"

    async def test_flagged_standards_monotonic_in_threshold(self, db: AsyncSession):
        fs = {}
        for th in (0.6, 0.7, 0.8):
            payload = await _athenian_math_g3(db, threshold=th)
            fs[th] = payload.kpis.flagged_standards
        # More standards fall below a HIGHER cut-off (weakly monotonic).
        assert fs[0.8] >= fs[0.7] >= fs[0.6]
        # BASELINE-verified anchors on the pinned dev DB.
        assert fs[0.6] == 1
        assert fs[0.7] == 3
        assert fs[0.8] == 12

    async def test_top_focus_is_flagged_worst_first(self, db: AsyncSession):
        payload = await _athenian_math_g3(db)
        assert len(payload.top_focus) <= 10
        # Every top-focus entry is flagged, and the list is pct-ascending.
        assert all(t.is_troublesome for t in payload.top_focus)
        gas = [t.grade_average for t in payload.top_focus]
        assert gas == sorted(gas)
        # BASELINE: worst three scope-pooled standards.
        assert payload.top_focus[0].schoology_standard == "MA.3.NSO.1.2"
        assert abs(payload.top_focus[0].grade_average - 0.582) <= 5e-3
        assert [t.schoology_standard for t in payload.top_focus[:3]] == [
            "MA.3.NSO.1.2",
            "MA.3.M.2.1",
            "MA.3.MP.1",
        ]


# ════════════════════════════════════════════════════════════════════════════
# ANCHORS — report grain / KPIs pinned to BASELINE.md.
# ════════════════════════════════════════════════════════════════════════════
class TestAnchors:
    async def test_grain_and_kpis(self, db: AsyncSession):
        payload = await _athenian_math_g3(db)
        cells = _body_cells(payload)
        assert len(cells) == 64  # (period × unit × standard)
        assert len({r.schoology_standard for _, _, r in cells}) == 37
        assert payload.kpis.units_covered == 20
        assert payload.kpis.periods_covered == 2
        assert [p.period for p in payload.periods] == [
            "Lesson Assessments",
            "Assessments",
        ]
        assert payload.filters_applied.threshold == 0.7
        assert payload.kpis.threshold_pct == "70.0%"

    async def test_period_distinct_counts(self, db: AsyncSession):
        # Per-period band counts are DISTINCT standard codes within the period
        # (not a sum of per-unit cells): ``standards_count`` = distinct codes
        # assessed in the period, ``flagged_count`` = distinct codes with ≥1
        # flagged cell in the period. BASELINE @70%: Lesson Assessments = 6 of
        # 37 flagged (across 17 units); Assessments = 1 of 6 (across 3 units).
        payload = await _athenian_math_g3(db)
        by_period = {p.period: p for p in payload.periods}
        lesson = by_period["Lesson Assessments"]
        assert lesson.standards_count == 37
        assert lesson.flagged_count == 6
        assessments = by_period["Assessments"]
        assert assessments.standards_count == 6
        assert assessments.flagged_count == 1


# ════════════════════════════════════════════════════════════════════════════
# c. SESSION DEFAULT (resolved server-side, never null) + Crestwell empty.
# ════════════════════════════════════════════════════════════════════════════
class TestSessionDefault:
    async def test_athenian_default_resolves_current_session(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        payload = await ReportService(db).build_forward_view(
            ForwardViewFilters(
                session=None, subject=SUBJECT, grade=GRADE, threshold=THRESHOLD
            )
        )
        # The default now resolves the CURRENT session, not the prior one: the
        # frontend resolves the latest session and sends it explicitly, and when
        # none is sent (direct API / CSV) the backend falls back to the school's
        # current session. Never null.
        assert payload.school.current_session == "2025-26"
        assert payload.filters_applied.session == "2025-26"
        assert payload.filters_applied.session is not None
        assert payload.periods, "Athenian current-year should have data"

    async def test_crestwell_prior_session_is_clean_empty_state(self, db: AsyncSession):
        await scope(db, CRESTWELL)
        # Pin the prior session EXPLICITLY: the default resolves the current
        # session now, so an empty-state check must request 2024-25 directly.
        payload = await ReportService(db).build_forward_view(
            ForwardViewFilters(session="2024-25", threshold=THRESHOLD)
        )
        assert payload.filters_applied.session == "2024-25"
        # Designed empty state — NOT an exception.
        assert payload.periods == []
        assert payload.kpis.standards_assessed == 0
        assert payload.kpis.flagged_standards == 0
        assert payload.top_focus == []
        # Payload still well-formed for the "View {current} instead" chip.
        assert payload.school.current_session
        assert payload.school.current_session != payload.filters_applied.session


# ════════════════════════════════════════════════════════════════════════════
# d. EXCLUSIONS — no unaligned / placeholder standard codes surface.
# ════════════════════════════════════════════════════════════════════════════
class TestExclusions:
    async def test_no_empty_or_other_standards(self, db: AsyncSession):
        payload = await _athenian_math_g3(db)
        codes = [r.schoology_standard for _, _, r in _body_cells(payload)]
        codes += [t.schoology_standard for t in payload.top_focus]
        assert codes, "expected standards in the anchor slice"
        for c in codes:
            assert c is not None
            assert c not in ("", "Other")


# ════════════════════════════════════════════════════════════════════════════
# e. ORDERING — worst-first (nulls last) within a unit; periods date-then-name.
# ════════════════════════════════════════════════════════════════════════════
class TestOrdering:
    async def test_units_worst_first_nulls_last(self, db: AsyncSession):
        payload = await _athenian_math_g3(db)
        for p in payload.periods:
            for u in p.units:
                gas = [r.grade_average for r in u.standards]
                non_null = [g for g in gas if g is not None]
                assert non_null == sorted(non_null), (
                    f"{p.period}/{u.unit} not ascending: {gas}"
                )
                # every None must come AFTER every non-None
                seen_null = False
                for g in gas:
                    if g is None:
                        seen_null = True
                    else:
                        assert not seen_null, f"{p.period}/{u.unit} null not last: {gas}"

    async def test_periods_ordered_by_earliest_date_then_name(self, db: AsyncSession):
        payload = await _athenian_math_g3(db)
        order = [(p.date_start, p.period) for p in payload.periods]
        # nulls-last on the date, then name — the SQL's ordering contract.
        expected = sorted(order, key=lambda t: (t[0] is None, t[0] or "", t[1]))
        assert order == expected


# ════════════════════════════════════════════════════════════════════════════
# f. DATA QUALITY — a section-filtered Forward View must not false-flag "missing".
# ════════════════════════════════════════════════════════════════════════════
class TestSectionAlignment:
    async def test_section_filter_does_not_false_flag_alignment_missing(
        self, db: AsyncSession
    ):
        """Section is a ``section_nid`` CSV, but the alignment-quality query
        matches ``dim_question_data.section`` (display labels), so passing the
        section there would never match → questions_total=0 → a false "alignment
        missing" banner. The builder computes DQ section-agnostically, so a
        section-filtered payload keeps a truthful, populated DQ block."""
        await scope(db, ATHENIAN)
        payload = await ReportService(db).build_forward_view(
            ForwardViewFilters(
                session=SESSION,
                subject=SUBJECT,
                grade=GRADE,
                section="7325370917",  # Vaughn — a populated Math G3 section
                threshold=THRESHOLD,
            )
        )
        assert payload.periods, "the section scope must have rollup data"
        assert payload.data_quality is not None
        assert payload.data_quality.questions_total > 0
        assert payload.data_quality.alignment_status != "missing"
