"""Per-student report regression suite — safety net for the new grain-B numbers.

Two READ-ONLY layers (same discipline as ``test_report_calculations.py``):

1. GOLDEN ANCHORS — pin the canonical grain-B figures for five CFP students
   spanning the distribution (verified live 2026-07). NOTE these intentionally
   differ from the one-off demo (``.planning/student-report-demo``), which used
   a non-canonical ``user_id_ques_id`` grain (Arthur 91.5 vs canonical 89.9).
2. CROSS-CHECK INVARIANTS — re-derive each number INDEPENDENTLY from raw
   ``fact_student_submission`` (a different path than StudentRepository) and
   assert the service agrees.

Run (safe — never truncates):
    cd backend && ./venv/bin/python -m pytest tests/reports/test_student_reports.py -q
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError
from app.services.student_service import StudentService

CFP = "019eb11c-413b-7a66-a7d8-a18f14736ede"
ATHENIAN = "019eb11c-410a-7ffb-86e6-a0294c669670"
SESSION = "2025-26"
# Aldon (Athenian, Grade 6) has 20 ELA Grade-6 assessments + 1 ELA assessment
# mis-filed under the Grade-8 export folder ("Through an Animal's Eyes Unit
# Test", taken only by Grade-6 students). Subjects must merge by name.
ALDON = "132721640"

# uid → (name, overall %). Grain: DISTINCT ON (user, question, position) with
# LATEST attempt (submission DESC) and session via dim_subject (slicer parity),
# points-based SUM/SUM. Deterministic; verified live 2026-07.
STUDENTS = {
    "116903200": ("Arthur De Oliveira", 90.9),
    "131833913": ("Charlize Hall", 83.0),
    "124292916": ("Azim Peralta", 80.8),
    "116907520": ("Bruno Rodriguez", 73.3),
    "124292876": ("Theodore Allen", 67.8),
}
SCHOOL_CLASS_AVG = 71.7  # mean of per-student latest-attempt overall %, n=421
ARTHUR = "116903200"
ARTHUR_SUBJECTS = {  # (subject, grade) → pct
    ("Algebra", "Grade 8"): 91.7,
    ("ELA", "Grade 8"): 84.4,
    ("History", "Grade 8"): 98.9,
    ("Math", "Grade 7"): 49.1,
    ("Science", "Grade 8"): 93.3,
}


async def scope(session: AsyncSession, school_id: str) -> None:
    """Scope EXACTLY as ``get_db_with_rls`` does: drop to the ``authenticated``
    role (so RLS is enforced, not bypassed as a superuser would) and set the
    tenant GUC. Without the role switch a superuser connection bypasses RLS and
    the school-wide class markers would pool every tenant."""
    await session.execute(text("SET LOCAL ROLE authenticated"))
    await session.execute(
        text("SELECT set_config('app.current_school_id', :s, true)"),
        {"s": school_id},
    )


def approx(a: float | None, b: float, tol: float = 0.06) -> bool:
    """1-dp figures compared with a small tolerance (rounding slack)."""
    return a is not None and abs(float(a) - b) <= tol


# ── Independent re-derivation (raw fact, NOT via StudentRepository) ──────────
# Same grain-B definition (session via dim_subject) but a structurally distinct
# query, so a regression in StudentRepository is caught.
async def _overall(session: AsyncSession, uid: str) -> float | None:
    sql = text(
        """
        WITH fd AS (
            SELECT DISTINCT ON (f.user_uid, f.item_id, f.question_id, f.position_number)
                   f.points_received AS pr, f.points_possible AS pp
            FROM fact_student_submission f
            JOIN dim_subject d
              ON d.school_id = f.school_id AND d.subject_id = f.subject_id
            WHERE f.user_uid = :uid AND d.session = :sess AND f.points_possible > 0
            ORDER BY f.user_uid, f.item_id, f.question_id, f.position_number,
                     f.submission DESC NULLS LAST, f.identifier NULLS LAST
        )
        SELECT 100.0 * SUM(pr) / NULLIF(SUM(pp), 0) FROM fd
        """
    )
    v = (await session.execute(sql, {"uid": uid, "sess": SESSION})).scalar()
    return float(v) if v is not None else None


# ════════════════════════════════════════════════════════════════════════════
# 1. GOLDEN ANCHORS
# ════════════════════════════════════════════════════════════════════════════
class TestGoldenStudentReport:
    @pytest.mark.parametrize("uid", list(STUDENTS))
    async def test_overall_anchor(self, db: AsyncSession, uid: str):
        await scope(db, CFP)
        report = await StudentService(db).build_student_report(uid, SESSION)
        name, expected = STUDENTS[uid]
        assert report.has_data is True
        assert report.overall.pct is not None
        assert approx(report.overall.pct, expected, tol=0.15), (
            f"{name}: {report.overall.pct} != {expected}"
        )

    async def test_arthur_subject_breakdown(self, db: AsyncSession):
        await scope(db, CFP)
        report = await StudentService(db).build_student_report(ARTHUR, SESSION)
        got = {(s.subject, s.grade): s.pct for s in report.subjects}
        assert len(report.subjects) == 5
        for key, expected in ARTHUR_SUBJECTS.items():
            assert key in got, f"missing subject {key}"
            assert approx(got[key], expected, tol=0.15), (
                f"{key}: {got[key]} != {expected}"
            )

    async def test_school_class_avg(self, db: AsyncSession):
        await scope(db, CFP)
        report = await StudentService(db).build_student_report(ARTHUR, SESSION)
        assert approx(report.overall.class_pct, SCHOOL_CLASS_AVG, tol=0.1)
        assert report.overall.class_n_students == 421


# ════════════════════════════════════════════════════════════════════════════
# 2. CROSS-CHECK INVARIANTS (service vs independent raw-fact re-derivation)
# ════════════════════════════════════════════════════════════════════════════
class TestCrossChecks:
    @pytest.mark.parametrize("uid", list(STUDENTS))
    async def test_overall_matches_raw_fact(self, db: AsyncSession, uid: str):
        await scope(db, CFP)
        report = await StudentService(db).build_student_report(uid, SESSION)
        raw = await _overall(db, uid)
        assert raw is not None
        assert approx(report.overall.pct, round(raw, 1))

    async def test_overall_reconciles_with_subject_points(self, db: AsyncSession):
        """Overall points = Σ subject points (no double-count across subjects)."""
        await scope(db, CFP)
        report = await StudentService(db).build_student_report(ARTHUR, SESSION)
        s_score = sum((s.score or 0) for s in report.subjects)
        s_poss = sum((s.possible or 0) for s in report.subjects)
        assert approx(report.overall.score, round(s_score, 1), tol=0.2)
        assert approx(report.overall.possible, round(s_poss, 1), tol=0.2)
        assert report.overall.pct == round(100.0 * s_score / s_poss, 1)


# ════════════════════════════════════════════════════════════════════════════
# 3. BROWSE ROSTER
# ════════════════════════════════════════════════════════════════════════════
class TestBrowse:
    async def test_roster_contains_student_with_overall(self, db: AsyncSession):
        await scope(db, CFP)
        page = await StudentService(db).browse_students(
            session_filter=SESSION, sort="name", limit=200
        )
        assert page.total >= 400
        by_uid = {r.uid: r for r in page.rows}
        # Arthur is in the first 200 alphabetical rows.
        row = by_uid.get(ARTHUR)
        assert row is not None
        # Browse must agree with the full report (both latest-attempt, grain B).
        report = await StudentService(db).build_student_report(ARTHUR, SESSION)
        assert approx(row.overall_pct, report.overall.pct, tol=0.05)
        assert approx(row.overall_pct, 90.9, tol=0.15)
        assert row.n_subjects == 5
        assert row.mastery.total == (
            row.mastery.green + row.mastery.yellow + row.mastery.pink
        )

    async def test_sort_overall_desc_top_is_highest(self, db: AsyncSession):
        await scope(db, CFP)
        page = await StudentService(db).browse_students(
            session_filter=SESSION, sort="overall", direction="desc", limit=5
        )
        pcts = [r.overall_pct for r in page.rows if r.overall_pct is not None]
        assert pcts == sorted(pcts, reverse=True)

    async def test_search_by_name(self, db: AsyncSession):
        await scope(db, CFP)
        page = await StudentService(db).browse_students(
            session_filter=SESSION, q="Arthur De Oliveira", limit=50
        )
        assert any(r.uid == ARTHUR for r in page.rows)


# ════════════════════════════════════════════════════════════════════════════
# 4. EDGE CASES
# ════════════════════════════════════════════════════════════════════════════
class TestEdgeCases:
    async def test_unknown_student_404(self, db: AsyncSession):
        await scope(db, CFP)
        with pytest.raises(ResourceNotFoundError):
            await StudentService(db).build_student_report("nonexistent-uid", SESSION)

    async def test_bands_are_valid(self, db: AsyncSession):
        await scope(db, CFP)
        report = await StudentService(db).build_student_report(ARTHUR, SESSION)
        valid = {"green", "yellow", "pink", "na"}
        assert report.overall.band in valid
        for s in report.subjects:
            assert s.band in valid
            for st in s.standards:
                assert st.band in valid
            for a in s.assessments:
                assert a.band in valid


# ════════════════════════════════════════════════════════════════════════════
# 5. CROSS-GRADE MISFILING MERGE (credibility): a stray Grade-8-tagged ELA
#    assessment for a Grade-6 student must fold into ONE ELA subject, not spawn
#    a phantom "ELA (8)" — while staying visible in the assessment history.
# ════════════════════════════════════════════════════════════════════════════
class TestCrossGradeMerge:
    async def test_stray_grade_folds_into_subject(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        report = await StudentService(db).build_student_report(ALDON, SESSION)
        names = [s.subject for s in report.subjects]
        # subjects are unique by name (no ELA split into two cards)
        assert len(names) == len(set(names)), names
        assert names.count("ELA") == 1
        # no phantom Grade-8 subject for this Grade-6 student
        assert all(s.grade != "Grade 8" for s in report.subjects), names
        ela = next(s for s in report.subjects if s.subject == "ELA")
        assert ela.grade == "Grade 6"  # dominant grade
        # transparency: the mis-filed assessment is still shown under ELA
        assert any("Through an Animal" in a.name for a in ela.assessments)

    async def test_arthur_still_five_distinct_subjects(self, db: AsyncSession):
        # A student whose subjects are each a single grade is unaffected.
        await scope(db, CFP)
        report = await StudentService(db).build_student_report(ARTHUR, SESSION)
        assert report.overall.n_subjects == 5
        assert len({s.subject for s in report.subjects}) == 5
