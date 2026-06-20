"""Report-calculation regression suite — the safety net for report numbers.

Two layers, both READ-ONLY:

1. GOLDEN ANCHORS — pin the exact, audited values for three reference
   assessments so any change that moves a report number is caught. The values
   were verified against the legacy SSRS paginated PDFs in
   ``data/sample reports/`` (report audit, 2026-06). Differences vs those PDFs
   are data-vintage only (the DB rebuilt from the backup has a few more
   students); the *formulas* match legacy to the digit.

2. CROSS-CHECK INVARIANTS — re-derive each report number INDEPENDENTLY from the
   raw ``fact_student_submission`` (a different code path than the cube
   repository) and assert the report agrees. These are data-agnostic: they keep
   protecting the calculations even if the seed/data changes, because both
   sides move together only when the math is right.

Run just this suite (safe — never truncates):
    cd backend && ./venv/bin/python -m pytest tests/reports -q

Anchor assessments (subject_id = section-agnostic merged identity):
  WEEK2  Athenian "Tell Me a Story: Weekly Assessment: Week 2" (3 sections)
  CH11   CFP "Chapter 11 Test: Geometry: Three-Dimensional Solids" (4 sections)
  SINGLE Athenian "Module 8 Week 2 Vocabulary Quiz" (1 section — merge no-op)
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.cube_repository import CubeRepository
from app.services.report_service import ReportService

# ── Schools / assessments ───────────────────────────────────────────────────
ATHENIAN = "019eb11c-410a-7ffb-86e6-a0294c669670"
CFP = "019eb11c-413b-7a66-a7d8-a18f14736ede"

WEEK2 = "28b31cfda8d02c9b5d15a0efcc3c497a15ee103b573a27e8829551ad91027295"
CH11 = "338a466ecab81d90b0110977af13a54304ef0f6efea1815d8525e16896f4a840"
SINGLE = "00cc81b6c649340659be1ed67ae00198ad51d9c645551a41ec3f86fc76d08b21"

SUBJECT_SCHOOL = {WEEK2: ATHENIAN, CH11: CFP, SINGLE: ATHENIAN}


async def scope(session: AsyncSession, school_id: str) -> None:
    """Scope the session to a school via the RLS GUC (as a request does)."""
    await session.execute(
        text("SELECT set_config('app.current_school_id', :s, true)"),
        {"s": school_id},
    )


def approx(a: float | None, b: float, tol: float = 5e-4) -> bool:
    return a is not None and abs(float(a) - b) <= tol


# ════════════════════════════════════════════════════════════════════════════
# Independent re-derivation helpers (raw fact → expected report numbers).
# Deliberately NOT routed through CubeRepository so a regression there is caught.
# ════════════════════════════════════════════════════════════════════════════
async def _fact_per_user_question(session: AsyncSession, subject_id: str):
    """Deduped per-(user, question_no) fraction for a merged assessment.

    Mirrors the canonical collapse (DISTINCT ON user/question/position, sum
    points per (user, question_no) via the section question_id→question_no map),
    pooled across the assessment's section copies. Returns rows of
    (section_instructors, question_no, user_uid, pct)."""
    sql = text(
        """
        WITH items AS (
            SELECT item_id, section_instructors
            FROM dim_item WHERE subject_id = :sid
        ),
        qmap AS (
            SELECT DISTINCT question_id, question_no
            FROM cube_question_summary
            WHERE item_id IN (SELECT item_id FROM items)
        ),
        fd AS (
            SELECT DISTINCT ON (f.user_uid, f.question_id, f.position_number)
                   f.user_uid, f.item_id, f.question_id, f.position_number,
                   f.points_received, f.points_possible
            FROM fact_student_submission f
            WHERE f.item_id IN (SELECT item_id FROM items)
              AND f.points_possible > 0
            ORDER BY f.user_uid, f.question_id, f.position_number, f.identifier NULLS LAST
        )
        SELECT it.section_instructors, q.question_no, fd.user_uid,
               SUM(fd.points_received)::numeric / NULLIF(SUM(fd.points_possible), 0) AS pct
        FROM fd
        JOIN qmap q ON q.question_id = fd.question_id
        JOIN items it ON it.item_id = fd.item_id
        GROUP BY it.section_instructors, q.question_no, fd.user_uid
        """
    )
    return list((await session.execute(sql, {"sid": subject_id})).mappings())


# ════════════════════════════════════════════════════════════════════════════
# 1. GOLDEN ANCHORS
# ════════════════════════════════════════════════════════════════════════════
class TestGoldenKpis:
    async def test_week2_canonical_kpis(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        k = await CubeRepository(db).get_canonical_kpis_for_item(WEEK2)
        assert k is not None
        assert int(k["total_students"]) == 55
        assert int(k["total_questions"]) == 22
        assert int(k["total_standards"]) == 8
        assert approx(k["total_possible_point"], 1190.0, 0.01)
        assert approx(k["total_score"], 975.0, 0.01)
        assert approx(k["grade_average"], 0.819712, 1e-4)
        assert approx(k["grade_min"], 0.545455, 1e-4)
        assert approx(k["grade_max"], 1.0, 1e-4)

    async def test_ch11_merged_kpis(self, db: AsyncSession):
        """4 CFP sections pool to one assessment: 65 students, 700/775."""
        await scope(db, CFP)
        k = await CubeRepository(db).get_canonical_kpis_for_item(CH11)
        assert int(k["total_students"]) == 65
        assert int(k["total_questions"]) == 8
        assert approx(k["total_possible_point"], 775.0, 0.01)
        assert approx(k["total_score"], 700.0, 0.01)  # 699.9994 float
        assert approx(k["grade_average"], 0.901923, 1e-4)

    async def test_single_section_kpis(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        k = await CubeRepository(db).get_canonical_kpis_for_item(SINGLE)
        assert int(k["total_students"]) == 18
        assert int(k["total_questions"]) == 2
        assert approx(k["total_possible_point"], 2304.0, 0.01)
        assert approx(k["total_score"], 2280.0, 0.01)
        assert approx(k["grade_average"], 0.989583, 1e-4)


class TestGoldenQra:
    async def test_week2_qra_per_question(self, db: AsyncSession):
        """QRA % correct for three questions (canonical per-question grade)."""
        await scope(db, ATHENIAN)
        rows = await CubeRepository(db).get_canonical_per_question_grades(WEEK2)
        by_q = {r["question_id"]: float(r["grade_average"]) for r in rows}
        assert approx(by_q["1"], 0.636364, 1e-4)  # 35/55
        assert approx(by_q["2"], 0.545455, 1e-4)  # 30/55  (legacy PDF 52.8% = 28/53, +2 students)
        assert approx(by_q["3"], 0.814815, 1e-4)

    async def test_week2_by_teacher(self, db: AsyncSession):
        """Per-(teacher, question) % correct — matches legacy By-Teacher PDF."""
        await scope(db, ATHENIAN)
        rows = await CubeRepository(db).get_qra_by_teacher_rows(WEEK2)
        cell = {
            (r["section_instructors"], r["question_no"]): float(r["grade_average"])
            for r in rows
        }
        assert approx(cell[("Elizabeth Sedlak", "1")], 0.500, 2e-3)
        assert approx(cell[("Elizabeth Sedlak", "2")], 0.625, 2e-3)
        assert approx(cell[("Elizabeth Sedlak", "17")], 0.4375, 2e-3)
        assert approx(cell[("Mason Reeder", "2")], 0.550, 2e-3)
        assert approx(cell[("Taylor Almendinger", "17")], 0.842, 2e-3)

    async def test_week2_by_standard_teacher_c31(self, db: AsyncSession):
        """ELA.1.C.3.1 standard average + per-teacher averages (legacy 85.8%)."""
        await scope(db, ATHENIAN)
        p = await ReportService(db).build_qra_by_standard_teacher(WEEK2)
        grp = next(g for g in p.standard_groups if g.cpalms_standard == "ELA.1.C.3.1")
        assert approx(grp.standard_average, 0.860, 2e-3)
        tg = {t.section_instructor: float(t.teacher_standard_average) for t in grp.teacher_groups}
        assert approx(tg["Elizabeth Sedlak"], 0.844, 2e-3)
        assert approx(tg["Mason Reeder"], 0.842, 2e-3)
        assert approx(tg["Taylor Almendinger"], 0.895, 2e-3)


class TestGoldenQsr:
    async def test_week2_qsr_teacher_subtotals(self, db: AsyncSession):
        """Points-model per-teacher subtotal + grand total (legacy 77.8/82.8…)."""
        await scope(db, ATHENIAN)
        p = await ReportService(db).build_question_summary_matrix_points(WEEK2)
        sub = {g.section_instructor: float(g.teacher_score_pct) for g in p.teacher_groups}
        assert approx(sub["Elizabeth Sedlak"], 0.7784, 1e-3)
        assert approx(sub["Mason Reeder"], 0.8286, 1e-3)
        assert approx(sub["Taylor Almendinger"], 0.8445, 1e-3)
        assert approx(p.grand_total.score_pct, 0.8193, 1e-3)
        assert approx(p.grand_total.possible_points, 1190.0, 0.01)
        assert approx(p.grand_total.correct_count, 975.0, 0.01)


# ════════════════════════════════════════════════════════════════════════════
# 2. CROSS-CHECK INVARIANTS (data-agnostic)
# ════════════════════════════════════════════════════════════════════════════
class TestInvariants:
    @pytest.mark.parametrize("sid", [WEEK2, CH11, SINGLE])
    async def test_by_teacher_matches_independent_fact(self, db: AsyncSession, sid: str):
        """Every (teacher, question) % in the By-Teacher report equals an
        independent per-student fraction-correct computed straight from the
        raw fact. Catches any drift in the report query's math."""
        await scope(db, SUBJECT_SCHOOL[sid])
        # Independent: mean of per-student pct per (teacher, question_no).
        fact = await _fact_per_user_question(db, sid)
        agg: dict[tuple[str, str], list[float]] = {}
        for r in fact:
            agg.setdefault((r["section_instructors"], r["question_no"]), []).append(
                float(r["pct"])
            )
        expected = {k: sum(v) / len(v) for k, v in agg.items()}
        # Report path:
        rows = await CubeRepository(db).get_qra_by_teacher_rows(sid)
        report = {
            (r["section_instructors"], r["question_no"]): float(r["grade_average"])
            for r in rows
            if r["grade_average"] is not None
        }
        assert report, "by-teacher report returned no rows"
        for key, val in report.items():
            assert key in expected, f"report cell {key} not in fact"
            assert approx(val, expected[key], 1e-3), f"{key}: report {val} != fact {expected[key]}"

    @pytest.mark.parametrize("sid", [WEEK2, CH11, SINGLE])
    async def test_merge_no_double_count(self, db: AsyncSession, sid: str):
        """Merged Total Students == legacy SUMX(SUMMARIZE(Item_ID,
        MAX(Total_Students))) AND, when sections are disjoint, == the distinct
        student count over the union — i.e. the section merge never double-counts."""
        await scope(db, SUBJECT_SCHOOL[sid])
        merged = int((await CubeRepository(db).get_canonical_kpis_for_item(sid))["total_students"])
        row = (await db.execute(text(
            """
            WITH items AS (SELECT item_id FROM dim_item WHERE subject_id = :sid)
            SELECT
              (SELECT COALESCE(SUM(ts),0) FROM (
                  SELECT item_id, MAX(total_students) ts FROM cube_school_summary
                  WHERE subject_id = :sid AND item_id IS NOT NULL GROUP BY item_id) z) AS sumx,
              (SELECT COUNT(DISTINCT user_uid) FROM fact_student_submission
                  WHERE item_id IN (SELECT item_id FROM items)) AS distinct_union
            """
        ), {"sid": sid})).mappings().one()
        assert merged == int(row["sumx"]), "Total Students != legacy SUMX formula"
        # No student is enrolled in 2 sections of these assessments → SUMX == distinct.
        assert int(row["sumx"]) == int(row["distinct_union"]), "section merge double-counted students"

    async def test_single_section_parity(self, db: AsyncSession):
        """A 1-section assessment's merged numbers == the per-item fact read —
        the merge must be a no-op there (no inflation)."""
        await scope(db, ATHENIAN)
        merged = await CubeRepository(db).get_canonical_kpis_for_item(SINGLE)
        row = (await db.execute(text(
            """
            WITH fd AS (
                SELECT DISTINCT ON (user_uid, question_id, position_number)
                       user_uid, question_id, points_received, points_possible
                FROM fact_student_submission
                WHERE item_id = (SELECT item_id FROM dim_item WHERE subject_id = :sid LIMIT 1)
                  AND points_possible > 0
                ORDER BY user_uid, question_id, position_number, identifier NULLS LAST
            )
            SELECT COUNT(DISTINCT user_uid) AS students,
                   COUNT(DISTINCT question_id) AS questions
            FROM fd
            """
        ), {"sid": SINGLE})).mappings().one()
        assert int(merged["total_students"]) == int(row["students"])
        assert int(merged["total_questions"]) == int(row["questions"])

    @pytest.mark.parametrize("sid", [WEEK2, CH11])
    async def test_twin_invariant_holds(self, db: AsyncSession, sid: str):
        """Re-aggregating the per-item twin cube over item_id reproduces the
        section-merged base cqso byte-for-byte (the R3 number-parity guard the
        merge relies on)."""
        await scope(db, SUBJECT_SCHOOL[sid])
        bad = (await db.execute(text(
            """
            SELECT COUNT(*) AS n FROM (
              SELECT b.ukey,
                     SUM(t.total_score) AS tw_score, b.total_score AS base_score,
                     SUM(t.total_possible_point) AS tw_pp, b.total_possible_point AS base_pp
              FROM cube_question_summary_overall_by_item t
              JOIN cube_question_summary_overall b
                ON b.subject_id = t.subject_id AND b.ukey = t.ukey
              WHERE t.subject_id = :sid
              GROUP BY b.ukey, b.total_score, b.total_possible_point
              HAVING ABS(SUM(t.total_score) - b.total_score) > 0.001
                  OR ABS(SUM(t.total_possible_point) - b.total_possible_point) > 0.001
            ) x
            """
        ), {"sid": sid})).scalar_one()
        assert bad == 0, "twin re-aggregation diverges from base cqso"

    @pytest.mark.parametrize("sid", [WEEK2, CH11])
    async def test_cqso_one_row_per_ukey(self, db: AsyncSession, sid: str):
        """Base cqso must be exactly one merged row per ukey for a subject — the
        property the merged QRA/IAD reads depend on."""
        await scope(db, SUBJECT_SCHOOL[sid])
        dupes = (await db.execute(text(
            "SELECT COUNT(*) FROM (SELECT ukey FROM cube_question_summary_overall "
            "WHERE subject_id = :sid GROUP BY ukey HAVING COUNT(*) > 1) x"
        ), {"sid": sid})).scalar_one()
        assert dupes == 0

    async def test_by_std_teacher_standard_avg_is_mean_of_cells(self, db: AsyncSession):
        """Standard Average == mean of its (teacher × question) cells — the
        legacy ``Avg(% correct)`` over the standard group."""
        await scope(db, ATHENIAN)
        p = await ReportService(db).build_qra_by_standard_teacher(WEEK2)
        for g in p.standard_groups:
            cells = [
                float(q.grade_average)
                for t in g.teacher_groups
                for q in t.questions
                if q.grade_average is not None
            ]
            if not cells:
                continue
            assert approx(g.standard_average, sum(cells) / len(cells), 2e-3), (
                f"{g.cpalms_standard}: standard_average != mean of cells"
            )

    @pytest.mark.parametrize("sid", [WEEK2, CH11, SINGLE])
    async def test_qsr_grand_total_matches_fact(self, db: AsyncSession, sid: str):
        """QSR grand total (points model) == SUM(received)/SUM(possible) computed
        straight from the deduped fact across all sections."""
        await scope(db, SUBJECT_SCHOOL[sid])
        p = await ReportService(db).build_question_summary_matrix_points(sid)
        if not p.per_student_available:
            pytest.skip("cube-only school (no per-student fact)")
        row = (await db.execute(text(
            """
            WITH items AS (SELECT item_id FROM dim_item WHERE subject_id = :sid),
            fd AS (
                SELECT DISTINCT ON (user_uid, question_id)
                       points_received, points_possible
                FROM fact_student_submission
                WHERE item_id IN (SELECT item_id FROM items) AND points_possible > 0
                ORDER BY user_uid, question_id, submission DESC NULLS LAST,
                         latest_attempt DESC NULLS LAST
            )
            SELECT SUM(points_received) AS rec, SUM(points_possible) AS poss FROM fd
            """
        ), {"sid": sid})).mappings().one()
        exp = float(row["rec"]) / float(row["poss"])
        assert approx(p.grand_total.score_pct, exp, 1e-3)

    async def test_kpi_dashboard_matches_report(self, db: AsyncSession):
        """The dashboard By-Assessment grade-average bar for an assessment equals
        the report's canonical KPI grade-average (two different code paths must
        not disagree)."""
        await scope(db, ATHENIAN)
        repo = CubeRepository(db)
        canon = await repo.get_canonical_kpis_for_item(WEEK2)
        rows, _ = await repo.get_assessment_summary_page(
            q="Tell Me a Story: Weekly Assessment: Week 2", limit=50
        )
        match = next((r for r in rows if r["item_id"] == WEEK2), None)
        assert match is not None, "assessment not found in dashboard grid"
        assert approx(match["grade_average"], float(canon["grade_average"]), 1e-4)
        assert int(match["total_students"]) == int(canon["total_students"])


# ════════════════════════════════════════════════════════════════════════════
# 3. REMAINING REPORT TYPES — IAD (drill-through), SDD, YTD
# ════════════════════════════════════════════════════════════════════════════
class TestIadSddYtd:
    async def test_week2_iad_q2(self, db: AsyncSession):
        """Incorrect Answer Details for Q2: pooled distractor counts match the
        legacy PDF exactly (13 / 11 / 1); only the correct count is +2 from the
        2 extra students (data vintage). 55 attempts, 30 correct, 25 wrong."""
        await scope(db, ATHENIAN)
        p = await ReportService(db).build_incorrect_answer_details(WEEK2, "2")
        assert approx(p.question.grade_average, 0.545455, 1e-4)
        assert p.kpis.total_attempts == 55
        assert p.kpis.correct_count == 30
        assert p.kpis.incorrect_count == 25
        assert p.kpis.distinct_answers == 4
        assert len(p.student_attempts) == 55
        by_ans = {d.answer_submission: d.students_count for d in p.distractors}
        # Wrong-answer distribution is identical to the legacy SSRS QRA PDF.
        stomps = next(v for k, v in by_ans.items() if "stomps" in k.lower())
        yawns = next(v for k, v in by_ans.items() if "yawns" in k.lower())
        assert stomps == 13
        assert yawns == 11
        # Counts are a partition of the attempts.
        assert sum(by_ans.values()) == 55

    async def test_week2_sdd_rollups(self, db: AsyncSession):
        """Standards Deep Dive: merged KPI + strand/standard rollup counts and a
        pinned per-standard grade (ELA.1.C.3.1 ≈ 86.1%)."""
        await scope(db, ATHENIAN)
        p = await ReportService(db).build_standards_deep_dive(WEEK2)
        assert p.kpis.total_students == 55
        assert len(p.standards_rollup) == 8
        assert len(p.strands_rollup) == 4
        c31 = next(s for s in p.standards_rollup if s.schoology_standard == "ELA.1.C.3.1")
        assert approx(c31.grade_average, 0.8611, 2e-3)

    async def test_ytd_builds_with_data(self, db: AsyncSession):
        """YTD Longitudinal builds a non-empty matrix for a real filter combo and
        the grand-total points are internally consistent (correct ≤ possible)."""
        from app.schemas.reports import YTDFilters

        await scope(db, ATHENIAN)
        p = await ReportService(db).build_year_to_date_performance(
            YTDFilters(
                session="2025-26",
                category="Lesson  Assessments",
                subject="ELA",
                grade="Grade 2",
            )
        )
        assert len(p.standards) > 0, "YTD returned no standard columns"
        assert len(p.teacher_groups) > 0, "YTD returned no teacher rows"
        gt = p.grand_total
        assert gt.points_possible > 0
        assert 0 <= gt.points_received <= gt.points_possible
        assert approx(gt.score_pct, gt.points_received / gt.points_possible, 1e-3)
