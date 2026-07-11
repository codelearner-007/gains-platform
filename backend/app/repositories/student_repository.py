"""Repository for per-student reporting.

Every read honours RLS via the ``app.current_school_id`` GUC (the caller MUST
use :func:`app.middleware.rls.get_db_with_rls`); nothing here filters
``school_id`` explicitly.

Two grains, both derived straight from ``fact_student_submission`` — cube
columns are never trusted for per-student scoring:

* **Totals** (overall / per-subject / per-assessment %) use ``fact_dedup`` =
  ``DISTINCT ON (user_uid, question_id, position_number) … ORDER BY submission
  DESC NULLS LAST, identifier NULLS LAST`` with ``points_possible > 0``, then
  points-based ``SUM(pr)/SUM(pp)``. Picking ONE identifier per (question,
  position) collapses the 9-part-PK standard-alias fan-out so a question's
  points are counted once. The ``submission DESC`` tie-break resolves retakes
  (the same cell has one row per attempt with different points) to the LATEST
  attempt — deterministic, and the honest measure of current mastery. This
  matches ``CubeRepository.get_canonical_kpis_for_item`` except that the
  canonical omits the attempt tie-break (so it is non-deterministic for the rare
  retaken cell); per-student figures therefore reconcile with the assessment
  reports to the digit except on those cells, where per-student is the more
  correct (latest-attempt) value.
* **Per-standard / per-strand mastery** attributes each (question, position) to
  ALL of its standards: ``DISTINCT ON (user_uid, question_id, position_number,
  identifier) … ORDER BY submission DESC`` (latest attempt) then grouped by
  identifier; strand rollup maps identifier→strand via ``dim_standard``. Mirrors
  the platform's standard-summary attribution and the demo's standards view.

Subject identity is ``(subject, grade)`` read from ``dim_subject`` (which
carries the course/subject override labels the slicers use); the *assessment*
identity is ``subject_id`` (merged, section-agnostic).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repository import row_to_dict as _row_to_dict

# Shared filter fragment scoping the fact to the current slicer selection. All
# subject/grade/session/assessment_type predicates hit ``dim_subject`` (alias
# ``dsub``) — NOT the fact's denormalised columns — so a course-overridden
# subject (e.g. "HS Physics") matches the slicer value. Section hits the fact
# directly; instructor dereferences through ``dim_item``.
_FACT_SCOPE_SQL = """\
f.points_possible IS NOT NULL AND f.points_possible > 0
              AND (CAST(:session AS TEXT)  IS NULL OR dsub.session         = CAST(:session AS TEXT))
              AND (CAST(:subject AS TEXT)  IS NULL OR dsub.subject         = CAST(:subject AS TEXT))
              AND (CAST(:grade AS TEXT)    IS NULL OR dsub.grade           = CAST(:grade AS TEXT))
              AND (CAST(:category AS TEXT) IS NULL OR dsub.assessment_type = CAST(:category AS TEXT))
              AND (CAST(:section AS TEXT)  IS NULL OR f.section            = CAST(:section AS TEXT))
              AND (CAST(:instructor AS TEXT) IS NULL OR EXISTS (
                    SELECT 1 FROM dim_item di
                    JOIN unnest(string_to_array(di.section_instructors, ',')) AS _ins(name)
                      ON btrim(_ins.name) = btrim(CAST(:instructor AS TEXT))
                    WHERE di.school_id = f.school_id AND di.item_id = f.item_id))"""


class StudentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ──────────────────────────────────────────────────────────────────
    # Browse roster — one summary row per student in the filter scope.
    # ──────────────────────────────────────────────────────────────────
    async def browse_students(
        self,
        session: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        category: Optional[str] = None,
        section: Optional[str] = None,
        instructor: Optional[str] = None,
        q: Optional[str] = None,
        sort_sql: str = "lower(name)",
        dir_sql: str = "ASC",
        limit: int = 25,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """One page of the "By Students" roster + the full scoped total.

        Per student: overall % (grain B, points SUM/SUM), the per-(subject,grade)
        chips, distinct grades, assessment count (DISTINCT subject_id), and the
        standards mastery split (green/yellow/pink). ``sort_sql``/``dir_sql`` are
        pre-validated literals from the service whitelist (interpolated, so they
        MUST NOT be raw input); everything else is bound.
        """
        order_by = f"{sort_sql} {dir_sql} NULLS LAST, uid ASC"
        sql = text(
            f"""
            WITH fd AS (
                SELECT DISTINCT ON (f.user_uid, f.item_id, f.question_id, f.position_number)
                       f.user_uid, f.subject_id,
                       dsub.subject AS subject, dsub.grade AS grade,
                       f.points_received AS pr, f.points_possible AS pp
                FROM fact_student_submission f
                JOIN dim_subject dsub
                  ON dsub.school_id = f.school_id AND dsub.subject_id = f.subject_id
                WHERE {_FACT_SCOPE_SQL}
                ORDER BY f.user_uid, f.item_id, f.question_id, f.position_number,
                         f.submission DESC NULLS LAST, f.identifier NULLS LAST
            ),
            per_sg AS (
                SELECT user_uid, subject, grade,
                       SUM(pr) AS pr, SUM(pp) AS pp,
                       COUNT(DISTINCT subject_id) AS n_assess
                FROM fd
                GROUP BY user_uid, subject, grade
            ),
            -- Merge each subject's grades into ONE (dominant grade = most
            -- assessments), so a stray cross-grade misfiling (e.g. an ELA test
            -- mis-filed under the Grade-8 folder for a Grade-6 student) folds
            -- into the real subject instead of splitting it.
            per_subject AS (
                SELECT user_uid, subject,
                       SUM(pr) AS pr, SUM(pp) AS pp, SUM(n_assess) AS n_assess,
                       (ARRAY_AGG(grade ORDER BY n_assess DESC, grade))[1] AS grade
                FROM per_sg
                GROUP BY user_uid, subject
            ),
            per_student AS (
                SELECT user_uid,
                       ROUND(100.0 * SUM(pr) / NULLIF(SUM(pp), 0), 1) AS overall_pct,
                       COUNT(*) AS n_subjects,
                       SUM(n_assess) AS n_assessments,
                       ARRAY_AGG(DISTINCT grade) FILTER (WHERE grade IS NOT NULL) AS grades,
                       JSON_AGG(
                         JSON_BUILD_OBJECT(
                           'subject', subject, 'grade', grade,
                           'pct', ROUND(100.0 * pr / NULLIF(pp, 0), 1))
                         ORDER BY subject) AS subjects
                FROM per_subject
                GROUP BY user_uid
            ),
            -- Per-standard mastery (all-attribution grain): one row per
            -- (student, question, position, identifier), latest attempt.
            std AS (
                SELECT DISTINCT ON (f.user_uid, f.item_id, f.question_id, f.position_number, f.identifier)
                       f.user_uid, f.question_id, f.position_number,
                       f.identifier, f.points_received AS pr, f.points_possible AS pp
                FROM fact_student_submission f
                JOIN dim_subject dsub
                  ON dsub.school_id = f.school_id AND dsub.subject_id = f.subject_id
                WHERE {_FACT_SCOPE_SQL}
                  AND f.identifier IS NOT NULL AND f.identifier <> ''
                ORDER BY f.user_uid, f.item_id, f.question_id, f.position_number, f.identifier,
                         f.submission DESC NULLS LAST
            ),
            per_std AS (
                SELECT user_uid, identifier,
                       SUM(pr) / NULLIF(SUM(pp), 0) AS frac
                FROM std
                GROUP BY user_uid, identifier
            ),
            mastery AS (
                SELECT user_uid,
                       COUNT(*) FILTER (WHERE frac >= 0.8) AS green,
                       COUNT(*) FILTER (WHERE frac >= 0.7 AND frac < 0.8) AS yellow,
                       COUNT(*) FILTER (WHERE frac < 0.7) AS pink,
                       COUNT(*) AS total
                FROM per_std
                GROUP BY user_uid
            ),
            final AS (
                SELECT ps.user_uid AS uid,
                       COALESCE(NULLIF(dst.name_display, ''),
                                NULLIF(TRIM(COALESCE(dst.name_first, '') || ' '
                                            || COALESCE(dst.name_last, '')), ''),
                                ps.user_uid) AS name,
                       ps.overall_pct, ps.n_subjects, ps.n_assessments,
                       ps.grades, ps.subjects,
                       COALESCE(m.green, 0) AS green,
                       COALESCE(m.yellow, 0) AS yellow,
                       COALESCE(m.pink, 0) AS pink,
                       COALESCE(m.total, 0) AS mastery_total,
                       COUNT(*) OVER() AS total
                FROM per_student ps
                LEFT JOIN dim_student dst
                       ON dst.uid = ps.user_uid
                      AND dst.school_id = NULLIF(current_setting('app.current_school_id', true), '')::uuid
                LEFT JOIN mastery m ON m.user_uid = ps.user_uid
            )
            SELECT * FROM final
            WHERE (CAST(:q AS TEXT) IS NULL OR name ILIKE '%' || CAST(:q AS TEXT) || '%')
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
            """
        )
        params = {
            "session": session,
            "subject": subject,
            "grade": grade,
            "category": category,
            "section": section,
            "instructor": instructor,
            "q": q,
            "limit": limit,
            "offset": offset,
        }
        result = await self.session.execute(sql, params)
        rows = [_row_to_dict(r) for r in result.all()]
        total = int(rows[0]["total"]) if rows else 0
        for r in rows:
            r.pop("total", None)
        return rows, total

    # ──────────────────────────────────────────────────────────────────
    # Full report — one student across all subjects.
    # ──────────────────────────────────────────────────────────────────
    async def get_student_identity(self, uid: str) -> Optional[Dict[str, Any]]:
        sql = text(
            """
            SELECT uid,
                   COALESCE(NULLIF(name_display, ''),
                            NULLIF(TRIM(COALESCE(name_first, '') || ' '
                                        || COALESCE(name_last, '')), ''),
                            uid) AS name,
                   COALESCE(NULLIF(name_first_preferred, ''), name_first) AS first,
                   name_last AS last,
                   grad_year, gender
            FROM dim_student
            WHERE uid = :uid
            LIMIT 1
            """
        )
        result = await self.session.execute(sql, {"uid": uid})
        row = result.first()
        return _row_to_dict(row) if row else None

    async def get_subject_totals(
        self, uid: str, session: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Per-subject totals for one student (grain B). Grades are MERGED into
        one row per subject (dominant grade = most assessments) so a stray
        cross-grade misfiling does not spawn a phantom subject; carries the
        comma-joined assessment types the student sat in that subject."""
        sql = text(
            """
            WITH fd AS (
                SELECT DISTINCT ON (f.user_uid, f.item_id, f.question_id, f.position_number)
                       dsub.subject AS subject, dsub.grade AS grade,
                       dsub.assessment_type AS atype, f.subject_id,
                       f.points_received AS pr, f.points_possible AS pp
                FROM fact_student_submission f
                JOIN dim_subject dsub
                  ON dsub.school_id = f.school_id AND dsub.subject_id = f.subject_id
                WHERE f.user_uid = :uid
                  AND f.points_possible IS NOT NULL AND f.points_possible > 0
                  AND (CAST(:session AS TEXT) IS NULL OR dsub.session = CAST(:session AS TEXT))
                ORDER BY f.user_uid, f.item_id, f.question_id, f.position_number,
                         f.submission DESC NULLS LAST, f.identifier NULLS LAST
            ),
            dom AS (
                SELECT DISTINCT ON (subject) subject, grade AS dominant_grade
                FROM (SELECT subject, grade, COUNT(DISTINCT subject_id) na
                      FROM fd GROUP BY subject, grade) g
                ORDER BY subject, na DESC, grade
            )
            SELECT fd.subject,
                   (SELECT dominant_grade FROM dom d WHERE d.subject = fd.subject) AS grade,
                   string_agg(DISTINCT fd.atype, ', ' ORDER BY fd.atype)
                     FILTER (WHERE fd.atype IS NOT NULL AND fd.atype <> '') AS assessment_types,
                   SUM(fd.pr) AS score, SUM(fd.pp) AS possible,
                   COUNT(*) AS n_questions,
                   COUNT(DISTINCT fd.subject_id) AS n_assessments
            FROM fd
            GROUP BY fd.subject
            ORDER BY fd.subject
            """
        )
        result = await self.session.execute(sql, {"uid": uid, "session": session})
        return [_row_to_dict(r) for r in result.all()]

    async def get_assessments(
        self, uid: str, session: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Per-assessment (merged ``subject_id``) rows for one student, grain B,
        with the merged assessment name (dim_subject.item_name) and earliest
        section date (MIN dim_item.assessment_date)."""
        sql = text(
            """
            WITH fd AS (
                SELECT DISTINCT ON (f.user_uid, f.item_id, f.question_id, f.position_number)
                       dsub.subject AS subject, dsub.grade AS grade, f.subject_id,
                       f.points_received AS pr, f.points_possible AS pp
                FROM fact_student_submission f
                JOIN dim_subject dsub
                  ON dsub.school_id = f.school_id AND dsub.subject_id = f.subject_id
                WHERE f.user_uid = :uid
                  AND f.points_possible IS NOT NULL AND f.points_possible > 0
                  AND (CAST(:session AS TEXT) IS NULL OR dsub.session = CAST(:session AS TEXT))
                ORDER BY f.user_uid, f.item_id, f.question_id, f.position_number,
                         f.submission DESC NULLS LAST, f.identifier NULLS LAST
            ),
            agg AS (
                SELECT subject, grade, subject_id,
                       SUM(pr) AS score, SUM(pp) AS possible, COUNT(*) AS n_questions
                FROM fd GROUP BY subject, grade, subject_id
            )
            SELECT a.subject, a.grade, a.subject_id AS item_id,
                   dsub.item_name AS name,
                   a.n_questions, a.score, a.possible,
                   (SELECT MIN(di.assessment_date) FROM dim_item di
                     WHERE di.subject_id = a.subject_id) AS date
            FROM agg a
            JOIN dim_subject dsub ON dsub.subject_id = a.subject_id
            ORDER BY date NULLS LAST, name
            """
        )
        result = await self.session.execute(sql, {"uid": uid, "session": session})
        return [_row_to_dict(r) for r in result.all()]

    async def get_standards(
        self, uid: str, session: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Per-standard mastery for one student (all-attribution grain), joined
        to the latest ``dim_standard`` metadata."""
        sql = text(
            """
            WITH std AS (
                SELECT DISTINCT ON (f.user_uid, f.item_id, f.question_id, f.position_number, f.identifier)
                       f.user_uid, f.question_id, f.position_number,
                       dsub.subject AS subject, dsub.grade AS grade,
                       f.identifier, f.points_received AS pr, f.points_possible AS pp
                FROM fact_student_submission f
                JOIN dim_subject dsub
                  ON dsub.school_id = f.school_id AND dsub.subject_id = f.subject_id
                WHERE f.user_uid = :uid
                  AND f.points_possible IS NOT NULL AND f.points_possible > 0
                  AND f.identifier IS NOT NULL AND f.identifier <> ''
                  AND (CAST(:session AS TEXT) IS NULL OR dsub.session = CAST(:session AS TEXT))
                ORDER BY f.user_uid, f.item_id, f.question_id, f.position_number, f.identifier,
                         f.submission DESC NULLS LAST
            ),
            agg AS (
                SELECT subject, identifier,
                       SUM(pr) AS pr, SUM(pp) AS pp, COUNT(*) AS n_questions
                FROM std GROUP BY subject, identifier
            ),
            meta AS (
                SELECT DISTINCT ON (identifier) identifier, schoology_standard,
                       description, custom_cleaned_description, strand, cluster,
                       cognitive_complexity_rating, direct_link
                FROM dim_standard
                ORDER BY identifier, last_change_date_time DESC NULLS LAST
            )
            SELECT a.subject, a.identifier,
                   COALESCE(NULLIF(m.schoology_standard, ''), a.identifier) AS code,
                   COALESCE(NULLIF(m.custom_cleaned_description, ''),
                            NULLIF(m.description, ''), a.identifier) AS description,
                   m.strand, m.cluster,
                   m.cognitive_complexity_rating AS complexity,
                   m.direct_link,
                   a.n_questions,
                   ROUND(100.0 * a.pr / NULLIF(a.pp, 0), 1) AS pct
            FROM agg a
            LEFT JOIN meta m ON m.identifier = a.identifier
            ORDER BY a.subject, pct ASC NULLS LAST
            """
        )
        result = await self.session.execute(sql, {"uid": uid, "session": session})
        return [_row_to_dict(r) for r in result.all()]

    async def get_strands(
        self, uid: str, session: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Per-strand rollup for one student (all-attribution grain)."""
        sql = text(
            """
            WITH meta AS (
                SELECT DISTINCT ON (identifier) identifier,
                       COALESCE(NULLIF(strand, ''), 'General') AS strand
                FROM dim_standard
                ORDER BY identifier, last_change_date_time DESC NULLS LAST
            ),
            -- One row per (student, question, position, identifier), latest
            -- attempt, tagged with its strand …
            ded AS (
                SELECT DISTINCT ON (f.user_uid, f.item_id, f.question_id, f.position_number, f.identifier)
                       f.user_uid, f.question_id, f.position_number,
                       dsub.subject AS subject, dsub.grade AS grade,
                       COALESCE(m.strand, 'General') AS strand,
                       f.points_received AS pr, f.points_possible AS pp
                FROM fact_student_submission f
                JOIN dim_subject dsub
                  ON dsub.school_id = f.school_id AND dsub.subject_id = f.subject_id
                LEFT JOIN meta m ON m.identifier = f.identifier
                WHERE f.user_uid = :uid
                  AND f.points_possible IS NOT NULL AND f.points_possible > 0
                  AND f.identifier IS NOT NULL AND f.identifier <> ''
                  AND (CAST(:session AS TEXT) IS NULL OR dsub.session = CAST(:session AS TEXT))
                ORDER BY f.user_uid, f.item_id, f.question_id, f.position_number, f.identifier,
                         f.submission DESC NULLS LAST
            ),
            -- … then collapse the standard-alias fan-out within a strand so a
            -- (question, position) counts once per strand it touches.
            st AS (
                SELECT DISTINCT user_uid, question_id, position_number,
                       subject, strand, pr, pp
                FROM ded
            )
            SELECT subject, strand,
                   COUNT(*) AS n_questions,
                   ROUND(100.0 * SUM(pr) / NULLIF(SUM(pp), 0), 1) AS pct
            FROM st
            GROUP BY subject, strand
            ORDER BY subject, pct ASC NULLS LAST
            """
        )
        result = await self.session.execute(sql, {"uid": uid, "session": session})
        return [_row_to_dict(r) for r in result.all()]

    async def get_class_markers(
        self, session: Optional[str] = None
    ) -> Dict[str, Any]:
        """School-wide peer-cohort averages (grain B, mean of per-student %s)
        computed in a SINGLE fact dedup: by (subject, grade), by assessment
        (subject_id), and overall. Used as the "vs class" markers.

        ``fd`` is MATERIALIZED so the school-wide dedup runs once and the three
        rollups read the shared result (≈1.1s vs 3× that if re-scanned)."""
        sql = text(
            """
            WITH fd AS MATERIALIZED (
                SELECT DISTINCT ON (f.user_uid, f.item_id, f.question_id, f.position_number)
                       f.user_uid, dsub.subject AS subject, dsub.grade AS grade,
                       f.subject_id, f.points_received AS pr, f.points_possible AS pp
                FROM fact_student_submission f
                JOIN dim_subject dsub
                  ON dsub.school_id = f.school_id AND dsub.subject_id = f.subject_id
                WHERE f.points_possible IS NOT NULL AND f.points_possible > 0
                  AND (CAST(:session AS TEXT) IS NULL OR dsub.session = CAST(:session AS TEXT))
                ORDER BY f.user_uid, f.item_id, f.question_id, f.position_number,
                         f.submission DESC NULLS LAST, f.identifier NULLS LAST
            ),
            per_subj AS (
                SELECT subject, grade, user_uid, SUM(pr) pr, SUM(pp) pp
                FROM fd GROUP BY subject, grade, user_uid
            ),
            per_asmt AS (
                SELECT subject_id, user_uid, SUM(pr) pr, SUM(pp) pp
                FROM fd GROUP BY subject_id, user_uid
            ),
            per_ovr AS (
                SELECT user_uid, SUM(pr) pr, SUM(pp) pp FROM fd GROUP BY user_uid
            )
            SELECT
              (SELECT JSON_AGG(JSON_BUILD_OBJECT(
                        'subject', subject, 'grade', grade,
                        'class_pct', cp, 'n_students', n))
                 FROM (SELECT subject, grade,
                              ROUND(AVG(100.0 * pr / NULLIF(pp, 0))::numeric, 1) cp,
                              COUNT(*) n
                       FROM per_subj GROUP BY subject, grade) s) AS by_subject,
              (SELECT JSON_AGG(JSON_BUILD_OBJECT('subject_id', subject_id, 'class_pct', cp))
                 FROM (SELECT subject_id,
                              ROUND(AVG(100.0 * pr / NULLIF(pp, 0))::numeric, 1) cp
                       FROM per_asmt GROUP BY subject_id) a) AS by_assessment,
              (SELECT JSON_BUILD_OBJECT(
                        'class_pct', ROUND(AVG(100.0 * pr / NULLIF(pp, 0))::numeric, 1),
                        'n_students', COUNT(*))
                 FROM per_ovr) AS overall
            """
        )
        result = await self.session.execute(sql, {"session": session})
        row = result.first()
        return _row_to_dict(row) if row else {}
