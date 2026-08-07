"""Quiz-exclusion regression suite — READ-ONLY.

Evan (Athenian principal, 2026-07-31) asked to keep quiz data out of the
top-of-report "grade level average", or to differentiate it. Quizzes are NOT a
distinct grading category in the data (``dim_item.item_type`` is the constant
'Test/Quiz'; no ``assessment_type`` equals 'Quiz'); the only reliable,
cross-school signal is the WORD "quiz" in ``dim_subject.item_name``. This suite
pins that behaviour:

  * the Python and SQL encodings of the quiz rule agree (one rule, two forms);
  * ``get_school_overall_grade_average`` and ``get_subject_overview`` EXCLUDE
    quiz-named items;
  * schools without any quiz-named items (CFP, Crestwell) are a STRICT no-op;
  * ``get_school_total_questions`` still COUNTS quizzes — the exclusion is
    scoped to the grade average only, not the shared cqso filter.

Same discipline as ``test_report_calculations.py``: scope to a school via the
RLS GUC exactly as a request does (drop to the non-bypassing ``authenticated``
role so RLS is enforced), assert, and roll back — the dev DB is never mutated.

Run (safe — never truncates):
    cd backend && ./venv/bin/python -m pytest tests/reports/test_quiz_exclusion.py -q

NEVER run pytest outside ``tests/reports`` — the pipeline/ingestion conftests
TRUNCATE the dev DB.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.cube_repository import (
    QUIZ_ITEM_NAME_RE,
    QUIZ_ITEM_NAME_SQL_REGEX,
    CubeRepository,
)
from app.services.assessment_service import AssessmentService

# ── School ids ───────────────────────────────────────────────────────────────
ATHENIAN = "019eb11c-410a-7ffb-86e6-a0294c669670"
CFP = "019eb11c-413b-7a66-a7d8-a18f14736ede"
CRESTWELL = "019eb11c-413c-7ed9-872e-0fe5e9a947b6"
NO_QUIZ_SCHOOLS = [("CFP", CFP), ("Crestwell", CRESTWELL)]

# Canonical rule fixtures — the word "quiz"/"quizzes", case-insensitive,
# word-bounded. Must-not-match guards against substring false positives.
MUST_MATCH = [
    "quiz",
    "Quiz",
    "QUIZ 2",
    "Unit 3 Quiz",
    "Vocabulary Quiz #4",
    "3/6 POP Quiz Module 11",
    "M1W1 Vocab Quiz",
    "Chapter 9 Mid-Chapter Quiz",
    "Unit 1 Quizzes",
]
MUST_NOT_MATCH = [
    "Quizizz Practice",
    "Quizlet Review",
    "Quizzical Thinking",
    "Marquize Project",
    "Unit 3 Test",
    "Tell Me a Story: Weekly Assessment: Week 2",
    "",
]


async def scope(session: AsyncSession, school_id: str) -> None:
    """Scope EXACTLY as ``get_db_with_rls`` does: drop to ``authenticated`` (so
    RLS is enforced, not bypassed as the superuser test role would) and set the
    tenant GUC (SET LOCAL — released by the fixture rollback)."""
    await session.execute(text("SET LOCAL ROLE authenticated"))
    await session.execute(
        text("SELECT set_config('app.current_school_id', :s, true)"),
        {"s": school_id},
    )


def approx(a: float | None, b: float, tol: float = 1e-6) -> bool:
    return a is not None and abs(float(a) - float(b)) <= tol


async def _cqso_grade_avgs(db: AsyncSession):
    """Within the current RLS scope, re-derive the pooled cqso grade average
    inclusive vs quiz-excluded, plus the quiz row count. Uses the SAME regex
    constant as the repository, bound as a parameter."""
    return (
        await db.execute(
            text(
                """
                SELECT AVG(cqso.grade_average)::float AS inc,
                       AVG(cqso.grade_average) FILTER (
                         WHERE dsubj.item_name IS NULL
                            OR dsubj.item_name !~* :pat
                       )::float AS exq,
                       COUNT(*) FILTER (WHERE dsubj.item_name ~* :pat) AS nquiz
                FROM cube_question_summary_overall cqso
                LEFT JOIN dim_subject dsubj
                  ON dsubj.school_id = cqso.school_id
                 AND dsubj.subject_id = cqso.subject_id
                """
            ),
            {"pat": QUIZ_ITEM_NAME_SQL_REGEX},
        )
    ).first()


# ════════════════════════════════════════════════════════════════════════════
# 1. Rule parity — Python regex ≡ Postgres regex ≡ intent
# ════════════════════════════════════════════════════════════════════════════
class TestQuizRegexParity:
    async def test_python_and_sql_regex_agree(self, db: AsyncSession):
        for name in MUST_MATCH:
            py = bool(QUIZ_ITEM_NAME_RE.search(name))
            sql = bool(
                (
                    await db.execute(
                        text("SELECT CAST(:n AS TEXT) ~* :p"),
                        {"n": name, "p": QUIZ_ITEM_NAME_SQL_REGEX},
                    )
                ).scalar()
            )
            assert py is True, f"Python regex should MATCH {name!r}"
            assert sql is True, f"SQL regex should MATCH {name!r}"

        for name in MUST_NOT_MATCH:
            py = bool(QUIZ_ITEM_NAME_RE.search(name))
            sql = bool(
                (
                    await db.execute(
                        text("SELECT CAST(:n AS TEXT) ~* :p"),
                        {"n": name, "p": QUIZ_ITEM_NAME_SQL_REGEX},
                    )
                ).scalar()
            )
            assert py is False, f"Python regex should NOT match {name!r}"
            assert sql is False, f"SQL regex should NOT match {name!r}"


# ════════════════════════════════════════════════════════════════════════════
# 2. Grade average — Athenian excludes quizzes; other schools are a no-op
# ════════════════════════════════════════════════════════════════════════════
class TestGradeAverageExcludesQuizzes:
    async def test_athenian_excludes_quizzes(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        method = await CubeRepository(db).get_school_overall_grade_average()
        raw = await _cqso_grade_avgs(db)
        assert raw.nquiz > 0, "Athenian must have quiz-named items"
        # method == independently re-derived quiz-excluded average
        assert approx(method, raw.exq), (method, raw.exq)
        # exclusion actually moved the number (guards against a silent no-op)
        assert float(raw.exq) < float(raw.inc)

    @pytest.mark.parametrize("name,school", NO_QUIZ_SCHOOLS)
    async def test_no_quiz_schools_are_noop(
        self, db: AsyncSession, name: str, school: str
    ):
        await scope(db, school)
        method = await CubeRepository(db).get_school_overall_grade_average()
        raw = await _cqso_grade_avgs(db)
        assert raw.nquiz == 0, f"{name} should have no quiz-named items"
        # predicate is a strict no-op: excluded == inclusive, method == inclusive
        assert approx(raw.exq, raw.inc, 1e-9)
        assert approx(method, raw.inc)


# ════════════════════════════════════════════════════════════════════════════
# 3. Subject cards — same exclusion, no subject dropped/added
# ════════════════════════════════════════════════════════════════════════════
class TestSubjectOverviewExcludesQuizzes:
    async def _rederive_subject_avgs(self, db: AsyncSession) -> dict:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT dsubj.subject AS subject,
                           AVG(cqso.grade_average)::float AS g
                    FROM cube_question_summary_overall cqso
                    JOIN dim_subject dsubj
                      ON dsubj.school_id = cqso.school_id
                     AND dsubj.subject_id = cqso.subject_id
                    WHERE dsubj.subject IS NOT NULL AND dsubj.subject <> ''
                      AND (dsubj.item_name IS NULL OR dsubj.item_name !~* :pat)
                    GROUP BY dsubj.subject
                    """
                ),
                {"pat": QUIZ_ITEM_NAME_SQL_REGEX},
            )
        ).mappings()
        return {r["subject"]: r["g"] for r in rows}

    async def test_athenian_subject_cards_match_ex_quiz(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        cards = {
            r["subject"]: r["grade_average"]
            for r in await CubeRepository(db).get_subject_overview()
        }
        expected = await self._rederive_subject_avgs(db)
        # exact same set of subjects (no card silently dropped by the exclusion)
        assert set(cards) == set(expected), (set(cards) ^ set(expected))
        for subject, g in expected.items():
            assert approx(cards[subject], g), (subject, cards[subject], g)

    @pytest.mark.parametrize("name,school", NO_QUIZ_SCHOOLS)
    async def test_no_quiz_schools_subject_cards_unchanged(
        self, db: AsyncSession, name: str, school: str
    ):
        await scope(db, school)
        cards = {
            r["subject"]: r["grade_average"]
            for r in await CubeRepository(db).get_subject_overview()
        }
        # for a school with no quizzes the ex-quiz re-derivation == the cards
        expected = await self._rederive_subject_avgs(db)
        assert set(cards) == set(expected)
        for subject, g in expected.items():
            assert approx(cards[subject], g)


# ════════════════════════════════════════════════════════════════════════════
# 4. Total Questions still counts quizzes (exclusion scoped to the average only)
# ════════════════════════════════════════════════════════════════════════════
class TestTotalQuestionsUnaffected:
    async def test_total_questions_still_includes_quizzes(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        tq = await CubeRepository(db).get_school_total_questions()
        counts = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT cqso.ukey) AS inc,
                           COUNT(DISTINCT cqso.ukey) FILTER (
                             WHERE dsubj.item_name IS NULL
                                OR dsubj.item_name !~* :pat
                           ) AS exq
                    FROM cube_question_summary_overall cqso
                    LEFT JOIN dim_subject dsubj
                      ON dsubj.school_id = cqso.school_id
                     AND dsubj.subject_id = cqso.subject_id
                    """
                ),
                {"pat": QUIZ_ITEM_NAME_SQL_REGEX},
            )
        ).first()
        # Total Questions is the inclusive count (quizzes NOT dropped here)…
        assert int(tq) == int(counts.inc)
        # …and quizzes really do contribute questions, so exclusion would differ.
        assert int(counts.exq) < int(counts.inc)


# ════════════════════════════════════════════════════════════════════════════
# 5. By-Assessment grid — the `kind` partition drives the Assessments/Quizzes tabs
# ════════════════════════════════════════════════════════════════════════════
class TestByAssessmentKindPartition:
    async def test_athenian_partition_and_classification(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        svc = AssessmentService(db)
        all_p = await svc.list_assessment_summaries(kind="all", limit=1)
        a_p = await svc.list_assessment_summaries(kind="assessment", limit=1)
        q_p = await svc.list_assessment_summaries(kind="quiz", limit=1)
        assert q_p.total > 0, "Athenian must have quizzes"
        # exact partition: assessment ⊍ quiz = all (no overlap, nothing lost)
        assert a_p.total + q_p.total == all_p.total
        # kind omitted defaults to 'all' (backward-compatible)
        default_p = await svc.list_assessment_summaries(limit=1)
        assert default_p.total == all_p.total
        # classification: every quiz-tab row IS a quiz; no assessment-tab row is
        qrows = (await svc.list_assessment_summaries(kind="quiz", limit=2000)).rows
        arows = (
            await svc.list_assessment_summaries(kind="assessment", limit=2000)
        ).rows
        assert qrows and all(
            QUIZ_ITEM_NAME_RE.search(r.item_name or "") for r in qrows
        )
        assert not any(QUIZ_ITEM_NAME_RE.search(r.item_name or "") for r in arows)

    async def test_partition_holds_under_a_filter(self, db: AsyncSession):
        # A+Q==ALL must survive an extra scope (session), not just the bare set.
        await scope(db, ATHENIAN)
        svc = AssessmentService(db)
        sess = (
            await db.execute(
                text(
                    "SELECT session FROM dim_subject WHERE session IS NOT NULL "
                    "GROUP BY session ORDER BY count(*) DESC LIMIT 1"
                )
            )
        ).scalar()
        a = (
            await svc.list_assessment_summaries(
                kind="assessment", session_filter=sess, limit=1
            )
        ).total
        q = (
            await svc.list_assessment_summaries(
                kind="quiz", session_filter=sess, limit=1
            )
        ).total
        allt = (
            await svc.list_assessment_summaries(
                kind="all", session_filter=sess, limit=1
            )
        ).total
        assert a + q == allt

    @pytest.mark.parametrize("name,school", NO_QUIZ_SCHOOLS)
    async def test_no_quiz_schools_have_empty_quiz_tab(
        self, db: AsyncSession, name: str, school: str
    ):
        await scope(db, school)
        svc = AssessmentService(db)
        q = await svc.list_assessment_summaries(kind="quiz", limit=1)
        allt = await svc.list_assessment_summaries(kind="all", limit=1)
        a = await svc.list_assessment_summaries(kind="assessment", limit=1)
        assert q.total == 0, f"{name} has no quizzes → empty Quizzes tab"
        assert a.total == allt.total


# ════════════════════════════════════════════════════════════════════════════
# 6. Quiz-only pooled average (the Quizzes-tab stat) — blank when no quizzes
# ════════════════════════════════════════════════════════════════════════════
class TestQuizOnlyAverage:
    async def test_athenian_quiz_average_present(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        v = await CubeRepository(db).get_school_overall_grade_average(
            quiz_mode="only"
        )
        assert v is not None and 0.0 < float(v) <= 1.0

    @pytest.mark.parametrize("name,school", NO_QUIZ_SCHOOLS)
    async def test_no_quiz_schools_quiz_average_is_none(
        self, db: AsyncSession, name: str, school: str
    ):
        await scope(db, school)
        v = await CubeRepository(db).get_school_overall_grade_average(
            quiz_mode="only"
        )
        assert v is None


# ════════════════════════════════════════════════════════════════════════════
# 7. All-quiz scope → grade average is None (blank "—"), never a spurious 0.0%
# ════════════════════════════════════════════════════════════════════════════
class TestAllQuizScopeBlank:
    async def test_all_quiz_scope_exclude_average_is_none(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        # Discover a (subject, grade, category) scope that is entirely quizzes
        # (no non-quiz items) — data-agnostic so a reseed can't rot the anchor.
        row = (
            await db.execute(
                text(
                    """
                    SELECT dsubj.subject, dsubj.grade, dsubj.assessment_type
                    FROM cube_question_summary_overall cqso
                    JOIN dim_subject dsubj
                      ON dsubj.school_id = cqso.school_id
                     AND dsubj.subject_id = cqso.subject_id
                    WHERE dsubj.subject IS NOT NULL
                    GROUP BY 1, 2, 3
                    HAVING count(*) FILTER (WHERE dsubj.item_name !~* :pat) = 0
                       AND count(*) FILTER (WHERE dsubj.item_name ~* :pat) > 0
                    LIMIT 1
                    """
                ),
                {"pat": QUIZ_ITEM_NAME_SQL_REGEX},
            )
        ).first()
        if row is None:
            pytest.skip("no all-quiz scope in current data")
        subject, grade, category = row
        repo = CubeRepository(db)
        # exclude → None (the hero renders "—"), NOT a misleading 0.0
        ex = await repo.get_school_overall_grade_average(
            subject=subject, grade=grade, category=category
        )
        assert ex is None, (subject, grade, category, ex)
        # …while the quiz-only average IS present (data exists, all quizzes).
        only = await repo.get_school_overall_grade_average(
            subject=subject, grade=grade, category=category, quiz_mode="only"
        )
        assert only is not None and 0.0 < float(only) <= 1.0
