"""Repository for cube_* aggregate tables.

All cube reads honour RLS via the ``app.current_school_id`` GUC; nothing in
this repository imposes an explicit ``WHERE school_id = ...`` filter. The
caller MUST have invoked :func:`app.middleware.rls.get_db_with_rls` (or the
equivalent) on the session before calling these methods.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _row_to_dict(row: Any) -> Dict[str, Any]:
    return dict(row._mapping)


class CubeRepository:
    """Reads from the cube_* and supporting fact tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ────────────────────────────────────────────────────────────────────
    # School-level summary for one assessment (cube_school_summary)
    # ────────────────────────────────────────────────────────────────────
    async def get_school_summary_for_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        sql = text(
            """
            SELECT
                item_id,
                total_questions,
                total_standards,
                total_students,
                total_possible_point,
                total_score,
                grade_average,
                percentage_incorrect_answers
            FROM cube_school_summary
            WHERE item_id = :item_id
            LIMIT 1
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        row = result.first()
        return _row_to_dict(row) if row else None

    async def get_grade_summary_for_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        sql = text(
            """
            SELECT
                item_id,
                grade_average,
                percentage_incorrect_answers,
                grade_min,
                grade_max
            FROM cube_grade_summary
            WHERE item_id = :item_id
            LIMIT 1
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        row = result.first()
        return _row_to_dict(row) if row else None

    # ────────────────────────────────────────────────────────────────────
    # Question-level summaries (cube_question_summary +
    # cube_question_summary_overall)
    # ────────────────────────────────────────────────────────────────────
    async def get_questions_for_item(self, item_id: str) -> List[Dict[str, Any]]:
        """Per-question summary for an assessment, joined with the overall
        cube to pick up `description`/`standards`/`incorrect_*` columns.
        """
        sql = text(
            """
            SELECT
                qs.question_id,
                qs.question_no,
                qs.position_number,
                qs.question,
                qs.question_type,
                qs.correct_answer,
                qs.total_possible_point,
                qs.total_score,
                qs.grade_average,
                qs.percentage_incorrect_answers     AS percentage_incorrect,
                COALESCE(qso.incorrect_choice_details, qs.incorrect_choice_details, '') AS incorrect_choice_details,
                COALESCE(qso.incorrect_details_name, qs.incorrect_details_name, '')     AS incorrect_details_name,
                COALESCE(qso.standards, qs.standards, '')                               AS standards,
                COALESCE(qso.description, '')                                           AS description,
                qs.standard,
                qs.ukey,
                qs.identifier
            FROM cube_question_summary qs
            LEFT JOIN cube_question_summary_overall qso
              ON qso.school_id = qs.school_id
             AND qso.ukey = qs.ukey
            WHERE qs.item_id = :item_id
            ORDER BY NULLIF(regexp_replace(qs.question_no, '[^0-9]', '', 'g'), '')::int NULLS LAST,
                     qs.question_no
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        return [_row_to_dict(r) for r in result.all()]

    async def get_questions_overall_for_item(self, item_id: str) -> List[Dict[str, Any]]:
        """cube_question_summary_overall slice for one assessment.

        cube_qso is keyed by subject_id (cross-section overall) so we resolve
        ``ukey`` via cube_question_summary which is item-scoped.
        """
        sql = text(
            """
            SELECT
                qs.question_id,
                COALESCE(qso.question_no, qs.question_no)         AS question_no,
                qs.position_number,
                COALESCE(qso.question, qs.question)               AS question,
                qs.question_type,
                COALESCE(qso.correct_answer, qs.correct_answer)   AS correct_answer,
                COALESCE(qso.total_possible_point, qs.total_possible_point) AS total_possible_point,
                COALESCE(qso.total_score, qs.total_score)         AS total_score,
                COALESCE(qso.grade_average, qs.grade_average)     AS grade_average,
                COALESCE(qso.percentage_incorrect_answers, qs.percentage_incorrect_answers) AS percentage_incorrect,
                COALESCE(qso.incorrect_choice_details, qs.incorrect_choice_details, '') AS incorrect_choice_details,
                COALESCE(qso.incorrect_details_name, qs.incorrect_details_name, '')     AS incorrect_details_name,
                COALESCE(qso.standards, qs.standards, '')         AS standards,
                qs.standard                                       AS strand_raw,
                COALESCE(qso.description, '')                     AS description
            FROM cube_question_summary qs
            LEFT JOIN cube_question_summary_overall qso
              ON qso.school_id = qs.school_id
             AND qso.ukey = qs.ukey
            WHERE qs.item_id = :item_id
            ORDER BY NULLIF(regexp_replace(qs.question_no, '[^0-9]', '', 'g'), '')::int NULLS LAST,
                     qs.question_no
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # Incorrect-choice detail (cube_questionincorrectchoice_summary)
    # ────────────────────────────────────────────────────────────────────
    async def get_incorrect_choices_for_item(self, item_id: str) -> List[Dict[str, Any]]:
        sql = text(
            """
            WITH item_qids AS (
                SELECT DISTINCT question_id
                FROM cube_question_summary
                WHERE item_id = :item_id
            ),
            attempts AS (
                SELECT
                    question_id,
                    SUM(total_student) AS total_attempts
                FROM cube_questionincorrectchoice_summary
                WHERE question_id IN (SELECT question_id FROM item_qids)
                GROUP BY question_id
            )
            SELECT
                qic.question_id,
                qic.answer_submission,
                qic.total_student                                AS students_count,
                qic.total_student                                AS attempt_count_for_choice,
                COALESCE(a.total_attempts, 0)                    AS total_attempts_for_question,
                CASE WHEN COALESCE(a.total_attempts,0) > 0
                     THEN qic.total_student::numeric / a.total_attempts::numeric
                     ELSE 0 END                                  AS share_of_attempts,
                qic.total_score,
                qic.total_possible_point,
                qic.grade_average,
                qic.percentage_incorrect_answers                 AS percentage_incorrect_answers,
                CASE WHEN qic.total_possible_point > 0
                     AND qic.total_score >= qic.total_possible_point
                     THEN TRUE ELSE FALSE END                    AS is_correct
            FROM cube_questionincorrectchoice_summary qic
            JOIN item_qids iq ON iq.question_id = qic.question_id
            LEFT JOIN attempts a ON a.question_id = qic.question_id
            ORDER BY qic.question_id, qic.total_student DESC NULLS LAST
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # Standards (cube_standard_summary joined with dim_standard)
    # ────────────────────────────────────────────────────────────────────
    async def get_standards_for_item(self, item_id: str) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT
                cs.item_id,
                cs.strand_id,
                cs.identifier,
                cs.total_questions,
                cs.total_standards,
                cs.total_possible_point,
                cs.total_score,
                cs.grade_average,
                cs.percentage_incorrect_answers,
                ds_strand.strand                AS strand,
                ds_std.schoology_standard       AS schoology_standard,
                ds_std.description              AS description
            FROM cube_standard_summary cs
            LEFT JOIN dim_strand ds_strand
              ON ds_strand.strand_id = cs.strand_id
             AND ds_strand.identifier = cs.identifier
            LEFT JOIN LATERAL (
                SELECT description, schoology_standard
                FROM dim_standard
                WHERE identifier = cs.identifier
                LIMIT 1
            ) ds_std ON TRUE
            WHERE cs.item_id = :item_id
            ORDER BY ds_strand.strand NULLS LAST, cs.identifier
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        return [_row_to_dict(r) for r in result.all()]

    async def get_strand_rollup(self) -> List[Dict[str, Any]]:
        """Aggregate cube_standard_summary by strand for the school."""
        sql = text(
            """
            SELECT
                cs.strand_id,
                ds_strand.strand,
                COUNT(DISTINCT cs.item_id)             AS total_questions,
                COUNT(DISTINCT cs.identifier)          AS total_standards,
                SUM(cs.total_possible_point)           AS total_possible_point,
                SUM(cs.total_score)                    AS total_score,
                CASE WHEN SUM(cs.total_possible_point) > 0
                     THEN SUM(cs.total_score)::numeric / SUM(cs.total_possible_point)::numeric
                     ELSE 0 END                        AS grade_average,
                CASE WHEN SUM(cs.total_possible_point) > 0
                     THEN 1 - (SUM(cs.total_score)::numeric / SUM(cs.total_possible_point)::numeric)
                     ELSE 0 END                        AS percentage_incorrect_answers
            FROM cube_standard_summary cs
            LEFT JOIN dim_strand ds_strand
              ON ds_strand.strand_id = cs.strand_id
             AND ds_strand.identifier = cs.identifier
            GROUP BY cs.strand_id, ds_strand.strand
            ORDER BY ds_strand.strand NULLS LAST, cs.strand_id
            """
        )
        result = await self.session.execute(sql)
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # Per-assessment strand / standard rollups (Standards Deep Dive page
    # AND the QRA Strands/Standards summary tables).
    # ────────────────────────────────────────────────────────────────────
    async def get_strand_rollup_for_item(
        self, item_id: str
    ) -> List[Dict[str, Any]]:
        """One row per Strand for a given assessment.

        Replicates the PBIX measure ``Total Question Strand`` (DISTINCTCOUNT
        of question_no per strand) and ``Grade_Average_Standard_Measure``
        (AVG of cube_question_summary_overall.Grade_Average across the rows
        in that strand). Strands with NULL strand label are dropped.
        """
        sql = text(
            """
            WITH item_qs AS (
                SELECT DISTINCT
                    qs.school_id,
                    qs.ukey,
                    qs.identifier
                FROM cube_question_summary qs
                WHERE qs.item_id = :item_id
            ),
            strand_q AS (
                -- (strand, question) pairs; one row per (strand, ukey).
                SELECT DISTINCT
                    ds.strand,
                    ds.strand_id,
                    iq.ukey,
                    iq.identifier
                FROM item_qs iq
                JOIN dim_strand ds
                  ON ds.identifier = iq.identifier
                WHERE ds.strand IS NOT NULL
                  AND ds.strand <> ''
            ),
            qso_avg AS (
                SELECT ukey, AVG(grade_average) AS grade_average
                FROM cube_question_summary_overall
                GROUP BY ukey
            )
            SELECT
                sq.strand                                          AS strand,
                COUNT(DISTINCT sq.identifier)                      AS num_standards,
                COUNT(DISTINCT sq.ukey)                            AS num_questions,
                AVG(COALESCE(qa.grade_average, 0))                 AS grade_average
            FROM strand_q sq
            LEFT JOIN qso_avg qa ON qa.ukey = sq.ukey
            GROUP BY sq.strand
            ORDER BY sq.strand
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        return [_row_to_dict(r) for r in result.all()]

    async def get_standard_rollup_for_item(
        self, item_id: str
    ) -> List[Dict[str, Any]]:
        """One row per (strand, cPalms_Standard) for a given assessment.

        Falls back to ``schoology_standard`` for the cPalms label when the
        cPalms column is empty (matches PBIX behaviour where the per-row
        label in the Charticulator visual #36 is ``cPalms_Standard``,
        falling back to ``Schoology Short Standard``).
        """
        sql = text(
            """
            WITH item_qs AS (
                SELECT DISTINCT
                    qs.school_id,
                    qs.ukey,
                    qs.identifier
                FROM cube_question_summary qs
                WHERE qs.item_id = :item_id
            ),
            std_q AS (
                SELECT DISTINCT
                    iq.ukey,
                    iq.identifier,
                    ds.strand,
                    dst.cpalms_standard,
                    dst.schoology_standard
                FROM item_qs iq
                JOIN dim_strand ds
                  ON ds.identifier = iq.identifier
                LEFT JOIN LATERAL (
                    SELECT cpalms_standard, schoology_standard
                    FROM dim_standard
                    WHERE identifier = iq.identifier
                    LIMIT 1
                ) dst ON TRUE
                WHERE ds.strand IS NOT NULL
                  AND ds.strand <> ''
            ),
            qso_avg AS (
                SELECT ukey, AVG(grade_average) AS grade_average
                FROM cube_question_summary_overall
                GROUP BY ukey
            )
            SELECT
                COALESCE(NULLIF(sq.cpalms_standard, ''), sq.schoology_standard, '') AS cpalms_standard,
                COALESCE(sq.schoology_standard, '')                AS schoology_standard,
                sq.strand                                          AS strand,
                COUNT(DISTINCT sq.ukey)                            AS num_questions,
                AVG(COALESCE(qa.grade_average, 0))                 AS grade_average
            FROM std_q sq
            LEFT JOIN qso_avg qa ON qa.ukey = sq.ukey
            GROUP BY 1, 2, 3
            HAVING COALESCE(NULLIF(sq.cpalms_standard, ''), sq.schoology_standard, '') <> ''
            ORDER BY sq.strand, cpalms_standard
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # School-wide rollups (Standard Summary + Strand Summary)
    # ────────────────────────────────────────────────────────────────────
    async def get_school_wide_meta(self) -> Optional[Dict[str, Any]]:
        """School name + logo + the predominant session label.

        Returns the same shape as ``get_ytd_school_meta`` but exposed under
        a more general name so the standard/strand summary endpoints can
        share it with YTD without coupling.
        """
        sql = text(
            """
            SELECT
                COALESCE(s.name, '')                          AS name,
                COALESCE(s.logo_url, '')                      AS logo_url,
                COALESCE(MAX(dsubj.session), '')              AS current_session
            FROM dim_item di
            LEFT JOIN dim_subject dsubj
              ON dsubj.school_id = di.school_id
             AND dsubj.subject_id = di.subject_id
            LEFT JOIN public.schools s
              ON s.school_id = di.school_id
            GROUP BY s.name, s.logo_url
            LIMIT 1
            """
        )
        result = await self.session.execute(sql)
        row = result.first()
        return _row_to_dict(row) if row else None

    async def get_school_total_students(
        self,
        session_filter: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        category: Optional[str] = None,
        section: Optional[str] = None,
    ) -> int:
        """Distinct students within the chosen filter scope."""
        sql = text(
            """
            SELECT COUNT(DISTINCT cus.user_uid) AS total_students
            FROM cube_user_summary cus
            WHERE (CAST(:session_filter AS TEXT) IS NULL OR cus.session = CAST(:session_filter AS TEXT))
              AND (CAST(:subject AS TEXT) IS NULL OR cus.subject = CAST(:subject AS TEXT))
              AND (CAST(:grade AS TEXT) IS NULL OR cus.grade = CAST(:grade AS TEXT))
              AND (CAST(:category AS TEXT) IS NULL OR cus.assessment_type = CAST(:category AS TEXT))
              AND (
                    CAST(:section AS TEXT) IS NULL
                 OR EXISTS (
                      SELECT 1 FROM dim_section dsec
                      WHERE dsec.school_id = cus.school_id
                        AND dsec.section_nid = cus.section_nid
                        AND (
                          dsec.section_name = CAST(:section AS TEXT)
                       OR dsec.section_code = CAST(:section AS TEXT)
                       OR dsec.section_nid  = CAST(:section AS TEXT)
                        )
                    )
                  )
            """
        )
        result = await self.session.execute(
            sql,
            {
                "session_filter": session_filter,
                "subject": subject,
                "grade": grade,
                "category": category,
                "section": section,
            },
        )
        row = result.first()
        return int(row._mapping["total_students"]) if row else 0

    async def get_school_strand_rollup(
        self,
        session_filter: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        category: Optional[str] = None,
        section: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """One row per Strand aggregated across the filter scope.

        Mirrors the per-item ``get_strand_rollup_for_item`` but operates
        across all assessments matching the filter context. Filters are
        applied directly on cube_question_summary which carries denormalised
        session / subject / grade / assessment_type / section columns.
        """
        sql = text(
            """
            WITH scoped_qs AS (
                SELECT DISTINCT
                    qs.school_id,
                    qs.ukey,
                    qs.identifier,
                    qs.item_id,
                    qs.subject
                FROM cube_question_summary qs
                WHERE (CAST(:session_filter AS TEXT) IS NULL OR qs.session = CAST(:session_filter AS TEXT))
                  AND (CAST(:subject AS TEXT) IS NULL OR qs.subject = CAST(:subject AS TEXT))
                  AND (CAST(:grade AS TEXT) IS NULL OR qs.grade = CAST(:grade AS TEXT))
                  AND (CAST(:category AS TEXT) IS NULL OR qs.assessment_type = CAST(:category AS TEXT))
                  AND (
                        CAST(:section AS TEXT) IS NULL
                     OR qs.section = CAST(:section AS TEXT)
                     OR EXISTS (
                          SELECT 1 FROM dim_section dsec
                          WHERE dsec.school_id = qs.school_id
                            AND dsec.item_id = qs.item_id
                            AND (
                              dsec.section_name = CAST(:section AS TEXT)
                           OR dsec.section_code = CAST(:section AS TEXT)
                           OR dsec.section_nid  = CAST(:section AS TEXT)
                            )
                        )
                      )
            ),
            strand_q AS (
                SELECT DISTINCT
                    ds.strand,
                    sq.ukey,
                    sq.identifier,
                    sq.item_id,
                    sq.subject
                FROM scoped_qs sq
                JOIN dim_strand ds
                  ON ds.identifier = sq.identifier
                WHERE ds.strand IS NOT NULL
                  AND ds.strand <> ''
            ),
            qso_avg AS (
                SELECT ukey, AVG(grade_average) AS grade_average
                FROM cube_question_summary_overall
                GROUP BY ukey
            ),
            strand_subjects AS (
                SELECT strand, ARRAY_AGG(DISTINCT subject ORDER BY subject) AS subjects
                FROM strand_q
                WHERE subject IS NOT NULL AND subject <> ''
                GROUP BY strand
            )
            SELECT
                sq.strand                                          AS strand,
                COUNT(DISTINCT sq.identifier)                      AS num_standards,
                COUNT(DISTINCT sq.ukey)                            AS num_questions,
                COUNT(DISTINCT sq.item_id)                         AS num_assessments,
                AVG(COALESCE(qa.grade_average, 0))                 AS grade_average,
                COALESCE(ss.subjects, ARRAY[]::text[])             AS subjects
            FROM strand_q sq
            LEFT JOIN qso_avg qa ON qa.ukey = sq.ukey
            LEFT JOIN strand_subjects ss ON ss.strand = sq.strand
            GROUP BY sq.strand, ss.subjects
            ORDER BY sq.strand
            """
        )
        result = await self.session.execute(
            sql,
            {
                "session_filter": session_filter,
                "subject": subject,
                "grade": grade,
                "category": category,
                "section": section,
            },
        )
        return [_row_to_dict(r) for r in result.all()]

    async def get_school_standard_rollup(
        self,
        session_filter: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        category: Optional[str] = None,
        section: Optional[str] = None,
        strand: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """One row per cPalms_Standard aggregated across the filter scope.

        Joins through dim_standard for cluster / cognitive_complexity /
        description / curriculum subject / last-changed metadata. Used by
        BOTH the Standard Summary and the Strand Summary's per-strand
        drill table (the latter passes a strand filter).
        """
        sql = text(
            """
            WITH scoped_qs AS (
                SELECT DISTINCT
                    qs.school_id,
                    qs.ukey,
                    qs.identifier,
                    qs.item_id
                FROM cube_question_summary qs
                WHERE (CAST(:session_filter AS TEXT) IS NULL OR qs.session = CAST(:session_filter AS TEXT))
                  AND (CAST(:subject AS TEXT) IS NULL OR qs.subject = CAST(:subject AS TEXT))
                  AND (CAST(:grade AS TEXT) IS NULL OR qs.grade = CAST(:grade AS TEXT))
                  AND (CAST(:category AS TEXT) IS NULL OR qs.assessment_type = CAST(:category AS TEXT))
                  AND (
                        CAST(:section AS TEXT) IS NULL
                     OR qs.section = CAST(:section AS TEXT)
                     OR EXISTS (
                          SELECT 1 FROM dim_section dsec
                          WHERE dsec.school_id = qs.school_id
                            AND dsec.item_id = qs.item_id
                            AND (
                              dsec.section_name = CAST(:section AS TEXT)
                           OR dsec.section_code = CAST(:section AS TEXT)
                           OR dsec.section_nid  = CAST(:section AS TEXT)
                            )
                        )
                      )
            ),
            std_q AS (
                SELECT DISTINCT
                    iq.ukey,
                    iq.identifier,
                    iq.item_id,
                    ds.strand,
                    dst.cpalms_standard,
                    dst.schoology_standard,
                    dst.cluster,
                    dst.cognitive_complexity_rating,
                    dst.subject AS std_subject,
                    dst.custom_cleaned_description,
                    dst.description,
                    dst.last_change_date_time
                FROM scoped_qs iq
                LEFT JOIN dim_strand ds
                  ON ds.identifier = iq.identifier
                LEFT JOIN LATERAL (
                    SELECT cpalms_standard, schoology_standard, cluster,
                           cognitive_complexity_rating, subject,
                           custom_cleaned_description, description,
                           last_change_date_time
                    FROM dim_standard
                    WHERE identifier = iq.identifier
                    LIMIT 1
                ) dst ON TRUE
                WHERE COALESCE(NULLIF(dst.cpalms_standard, ''),
                               NULLIF(dst.schoology_standard, ''), '') <> ''
                  AND (CAST(:strand AS TEXT) IS NULL OR ds.strand = CAST(:strand AS TEXT))
            ),
            qso_avg AS (
                SELECT ukey, AVG(grade_average) AS grade_average
                FROM cube_question_summary_overall
                GROUP BY ukey
            )
            SELECT
                COALESCE(NULLIF(sq.cpalms_standard, ''), sq.schoology_standard, '') AS cpalms_standard,
                COALESCE(sq.schoology_standard, '')                AS schoology_standard,
                COALESCE(sq.strand, '')                            AS strand,
                COALESCE(sq.cluster, '')                           AS cluster,
                COALESCE(sq.cognitive_complexity_rating, '')       AS cognitive_complexity,
                COALESCE(NULLIF(sq.custom_cleaned_description, ''),
                         sq.description, '')                       AS description,
                COALESCE(sq.std_subject, '')                       AS subject,
                COUNT(DISTINCT sq.ukey)                            AS num_questions,
                COUNT(DISTINCT sq.item_id)                         AS num_assessments,
                AVG(COALESCE(qa.grade_average, 0))                 AS grade_average,
                MAX(sq.last_change_date_time)                      AS last_change_date_time
            FROM std_q sq
            LEFT JOIN qso_avg qa ON qa.ukey = sq.ukey
            GROUP BY 1, 2, 3, 4, 5, 6, 7
            ORDER BY 3 NULLS LAST, 1
            """
        )
        result = await self.session.execute(
            sql,
            {
                "session_filter": session_filter,
                "subject": subject,
                "grade": grade,
                "category": category,
                "section": section,
                "strand": strand,
            },
        )
        return [_row_to_dict(r) for r in result.all()]

    async def get_all_standards_for_school(self) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT
                cs.item_id,
                cs.strand_id,
                cs.identifier,
                cs.total_questions,
                cs.total_standards,
                cs.total_possible_point,
                cs.total_score,
                cs.grade_average,
                cs.percentage_incorrect_answers,
                ds_strand.strand,
                ds_std.schoology_standard,
                ds_std.description
            FROM cube_standard_summary cs
            LEFT JOIN dim_strand ds_strand
              ON ds_strand.strand_id = cs.strand_id
             AND ds_strand.identifier = cs.identifier
            LEFT JOIN LATERAL (
                SELECT description, schoology_standard
                FROM dim_standard
                WHERE identifier = cs.identifier
                LIMIT 1
            ) ds_std ON TRUE
            ORDER BY ds_strand.strand NULLS LAST, cs.identifier
            """
        )
        result = await self.session.execute(sql)
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # Helpers used by the composed report endpoint
    # ────────────────────────────────────────────────────────────────────
    async def get_assessment_meta(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Compose AssessmentMeta from dim_item, dim_section, dim_subject and
        the schools table.

        first_access / latest_attempt come from fact_student_submission. The
        course join goes through fact_student_submission.course_nid because
        dim_course doesn't carry an item_id link.
        """
        sql = text(
            """
            WITH item_course AS (
                SELECT DISTINCT course_nid
                FROM fact_student_submission
                WHERE item_id = :item_id
                LIMIT 1
            )
            SELECT
                di.item_id,
                COALESCE(di.item_name, '')             AS item_name,
                COALESCE(di.item_type, '')             AS item_type,
                di.subject_id,
                COALESCE(ds.section_nid, '')           AS section_nid,
                COALESCE(ds.section_code, '')          AS section_code,
                COALESCE(ds.section_name, di.section_name, '') AS section_name,
                COALESCE(ds.section_instructors, di.section_instructors, '') AS section_instructors,
                COALESCE(dc.course_nid, '')            AS course_nid,
                COALESCE(dc.course_name, '')           AS course_name,
                COALESCE(dc.course_code, '')           AS course_code,
                COALESCE(dsubj.subject, '')            AS subject,
                COALESCE(dsubj.grade, '')              AS grade,
                COALESCE(dsubj.session, '')            AS session,
                COALESCE(dsubj.assessment_type, '')    AS assessment_type,
                di.school_id,
                COALESCE(s.name, '')                   AS school_name,
                s.logo_url                             AS school_logo_url
            FROM dim_item di
            LEFT JOIN dim_section ds
              ON ds.school_id = di.school_id AND ds.item_id = di.item_id
            LEFT JOIN item_course ic ON TRUE
            LEFT JOIN dim_course dc
              ON dc.school_id = di.school_id AND dc.course_nid = ic.course_nid
            LEFT JOIN dim_subject dsubj
              ON dsubj.school_id = di.school_id AND dsubj.subject_id = di.subject_id
            LEFT JOIN public.schools s
              ON s.school_id = di.school_id
            WHERE di.item_id = :item_id
            LIMIT 1
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        row = result.first()
        if not row:
            return None
        meta = _row_to_dict(row)

        # First/latest access from the fact table, scoped to this item.
        access_sql = text(
            """
            SELECT
                MIN(first_access)   AS first_access,
                MAX(latest_attempt) AS latest_attempt
            FROM fact_student_submission
            WHERE item_id = :item_id
            """
        )
        access_row = (await self.session.execute(access_sql, {"item_id": item_id})).first()
        if access_row:
            meta["first_access"] = access_row._mapping["first_access"]
            meta["latest_attempt"] = access_row._mapping["latest_attempt"]
        else:
            meta["first_access"] = None
            meta["latest_attempt"] = None
        return meta

    async def get_students_for_item(self, item_id: str) -> List[Dict[str, Any]]:
        """Distinct students who submitted for an item, joined to dim_student.

        Falls back to fact_student_submission.user_name if the dim row is
        missing.
        """
        sql = text(
            """
            WITH item_users AS (
                SELECT DISTINCT user_uid, user_role_id, user_name
                FROM fact_student_submission
                WHERE item_id = :item_id
                  AND user_uid IS NOT NULL
            )
            SELECT
                iu.user_uid                                                  AS user_uid,
                COALESCE(NULLIF(ds.username, ''), '')                        AS username,
                COALESCE(NULLIF(ds.name_first, ''), split_part(iu.user_name, ' ', 1)) AS first_name,
                COALESCE(NULLIF(ds.name_last,  ''),
                         CASE WHEN position(' ' in COALESCE(iu.user_name,'')) > 0
                              THEN substring(iu.user_name from position(' ' in iu.user_name) + 1)
                              ELSE '' END)                                   AS last_name,
                COALESCE(iu.user_role_id, ds.role_id, '')                    AS user_role_id
            FROM item_users iu
            LEFT JOIN dim_student ds
              ON ds.uid = iu.user_uid
            ORDER BY last_name, first_name
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        return [_row_to_dict(r) for r in result.all()]

    async def get_raw_question_options_for_item(
        self, item_id: str
    ) -> List[Dict[str, Any]]:
        """Distractor-level rows from dim_question_data for this item."""
        sql = text(
            """
            SELECT
                COALESCE(item_id, '')              AS item_id,
                COALESCE(item_name, '')            AS item_name,
                COALESCE(question_id, '')          AS question_id,
                COALESCE(associated_question_id, '') AS associated_question_id,
                COALESCE(NULLIF(total_points, ''), '0')::numeric AS total_points,
                COALESCE(question_type, '')        AS question_type,
                COALESCE(question, '')             AS question,
                COALESCE(position_number, '')      AS position_number,
                COALESCE(sub_question, '')         AS sub_question,
                ''                                 AS answer_option,
                0::numeric                         AS answer_breakdown_count,
                0::numeric                         AS answer_breakdown_pct,
                COALESCE(correct_answer, '')       AS correct_answer,
                COALESCE(NULLIF(correctly_answered, ''), '0')::numeric    AS correctly_answered,
                COALESCE(NULLIF(most_points_earned,  ''), '0')::numeric   AS most_points_earned,
                COALESCE(NULLIF(least_points_earned, ''), '0')::numeric   AS least_points_earned,
                COALESCE(NULLIF(average_points_earned, ''), '0')::numeric AS average_points_earned
            FROM dim_question_data
            WHERE item_id = :item_id
            ORDER BY NULLIF(regexp_replace(COALESCE(question_no, ''), '[^0-9]', '', 'g'), '')::int NULLS LAST,
                     question_no
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # Year-To-Date Performance (cross-assessment, school-wide)
    # ────────────────────────────────────────────────────────────────────
    async def get_ytd_school_meta(self) -> Optional[Dict[str, Any]]:
        sql = text(
            """
            SELECT
                COALESCE(s.name, '')                          AS name,
                COALESCE(s.logo_url, '')                      AS logo_url,
                COALESCE(MAX(dsubj.session), '')              AS current_session,
                MIN(di.assessment_date)                       AS date_from,
                MAX(di.assessment_date)                       AS date_to,
                COUNT(DISTINCT di.item_id)                    AS total_assessments
            FROM dim_item di
            LEFT JOIN dim_subject dsubj
              ON dsubj.school_id = di.school_id
             AND dsubj.subject_id = di.subject_id
            LEFT JOIN public.schools s
              ON s.school_id = di.school_id
            GROUP BY s.name, s.logo_url
            LIMIT 1
            """
        )
        result = await self.session.execute(sql)
        row = result.first()
        return _row_to_dict(row) if row else None

    async def get_ytd_overall_kpis(self) -> Optional[Dict[str, Any]]:
        sql = text(
            """
            SELECT
                COUNT(DISTINCT cus.user_uid)                  AS total_students,
                COUNT(DISTINCT cus.item_id)                   AS total_assessments,
                COUNT(*)                                      AS total_questions_answered,
                CASE
                  WHEN SUM(cus.total_possible_point) > 0
                  THEN SUM(cus.total_score)::numeric
                       / SUM(cus.total_possible_point)::numeric
                  ELSE 0
                END                                           AS overall_avg
            FROM cube_user_summary cus
            """
        )
        result = await self.session.execute(sql)
        row = result.first()
        return _row_to_dict(row) if row else None

    async def get_ytd_timeline(self) -> List[Dict[str, Any]]:
        sql = text(
            """
            WITH per_date_subject AS (
                SELECT
                    di.assessment_date              AS d,
                    COALESCE(dsubj.subject, 'Other') AS subject,
                    SUM(cus.total_score)            AS s,
                    SUM(cus.total_possible_point)   AS p
                FROM cube_user_summary cus
                JOIN dim_item di
                  ON di.item_id = cus.item_id
                LEFT JOIN dim_subject dsubj
                  ON dsubj.school_id = di.school_id
                 AND dsubj.subject_id = di.subject_id
                WHERE di.assessment_date IS NOT NULL
                GROUP BY di.assessment_date, COALESCE(dsubj.subject, 'Other')
            ),
            per_date AS (
                SELECT
                    di.assessment_date                       AS d,
                    SUM(cus.total_score)                     AS s,
                    SUM(cus.total_possible_point)            AS p,
                    COUNT(DISTINCT cus.item_id)              AS items
                FROM cube_user_summary cus
                JOIN dim_item di
                  ON di.item_id = cus.item_id
                WHERE di.assessment_date IS NOT NULL
                GROUP BY di.assessment_date
            )
            SELECT
                pd.d                                          AS date,
                CASE WHEN pd.p > 0 THEN pd.s::numeric / pd.p::numeric ELSE 0 END AS overall_avg,
                pd.items                                      AS assessments_count,
                pds.subject                                   AS subject,
                CASE WHEN pds.p > 0 THEN pds.s::numeric / pds.p::numeric ELSE 0 END AS subject_avg
            FROM per_date pd
            LEFT JOIN per_date_subject pds
              ON pds.d = pd.d
            ORDER BY pd.d, pds.subject
            """
        )
        result = await self.session.execute(sql)
        return [_row_to_dict(r) for r in result.all()]

    async def get_ytd_grade_distribution(self) -> List[Dict[str, Any]]:
        sql = text(
            """
            WITH user_item AS (
                SELECT
                    cus.user_uid,
                    cus.item_id,
                    SUM(cus.total_score)            AS s,
                    SUM(cus.total_possible_point)   AS p
                FROM cube_user_summary cus
                GROUP BY cus.user_uid, cus.item_id
            ),
            user_item_pct AS (
                SELECT user_uid, item_id,
                       CASE WHEN p > 0 THEN s::numeric / p ELSE 0 END AS pct
                FROM user_item
            )
            SELECT
                di.assessment_date                                     AS date,
                COUNT(*) FILTER (WHERE ui.pct >= 0.8)                  AS band_high,
                COUNT(*) FILTER (WHERE ui.pct >= 0.7 AND ui.pct < 0.8) AS band_mid,
                COUNT(*) FILTER (WHERE ui.pct < 0.7)                   AS band_low
            FROM user_item_pct ui
            JOIN dim_item di
              ON di.item_id = ui.item_id
            WHERE di.assessment_date IS NOT NULL
            GROUP BY di.assessment_date
            ORDER BY di.assessment_date
            """
        )
        result = await self.session.execute(sql)
        return [_row_to_dict(r) for r in result.all()]

    async def get_ytd_student_progression(self) -> List[Dict[str, Any]]:
        sql = text(
            """
            WITH user_item AS (
                SELECT
                    cus.user_uid,
                    COALESCE(NULLIF(cus.user_name, ''), cus.user_uid) AS user_name,
                    di.assessment_date                                AS d,
                    cus.item_id,
                    SUM(cus.total_score)                              AS s,
                    SUM(cus.total_possible_point)                     AS p
                FROM cube_user_summary cus
                JOIN dim_item di
                  ON di.item_id = cus.item_id
                WHERE di.assessment_date IS NOT NULL
                GROUP BY cus.user_uid, cus.user_name, di.assessment_date, cus.item_id
            ),
            user_item_pct AS (
                SELECT
                    user_uid,
                    user_name,
                    d,
                    item_id,
                    CASE WHEN p > 0 THEN s::numeric / p ELSE 0 END AS pct
                FROM user_item
            ),
            ranked AS (
                SELECT
                    user_uid,
                    user_name,
                    item_id,
                    d,
                    pct,
                    ROW_NUMBER() OVER (
                        PARTITION BY user_uid ORDER BY d ASC, item_id ASC
                    ) AS rn_first,
                    ROW_NUMBER() OVER (
                        PARTITION BY user_uid ORDER BY d DESC, item_id DESC
                    ) AS rn_last,
                    COUNT(*) OVER (PARTITION BY user_uid) AS n
                FROM user_item_pct
            )
            SELECT
                user_uid,
                MAX(user_name)                                AS user_name,
                MAX(CASE WHEN rn_first = 1 THEN pct END)::numeric AS first_avg,
                MAX(CASE WHEN rn_last  = 1 THEN pct END)::numeric AS latest_avg,
                MAX(n)                                        AS assessments_taken
            FROM ranked
            GROUP BY user_uid
            ORDER BY user_name
            """
        )
        result = await self.session.execute(sql)
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # Incorrect Answer Details (drill-through from QRA, single question)
    # ────────────────────────────────────────────────────────────────────
    async def get_question_overall(
        self, item_id: str, question_id: str
    ) -> Optional[Dict[str, Any]]:
        """One question's overall metadata (joined to qso for description)."""
        sql = text(
            """
            SELECT
                qs.question_id,
                COALESCE(qso.question_no, qs.question_no)         AS question_no,
                COALESCE(qs.position_number, '')                  AS position_number,
                COALESCE(qso.question, qs.question)               AS question,
                COALESCE(qs.question_type, '')                    AS question_type,
                COALESCE(qso.correct_answer, qs.correct_answer)   AS correct_answer,
                COALESCE(qso.total_possible_point, qs.total_possible_point) AS total_possible_point,
                COALESCE(qso.total_score, qs.total_score)         AS total_score,
                COALESCE(qso.grade_average, qs.grade_average)     AS grade_average,
                COALESCE(qso.standards, qs.standards, '')         AS standards,
                COALESCE(qs.standard, '')                         AS strand_raw,
                COALESCE(qso.description, '')                     AS description
            FROM cube_question_summary qs
            LEFT JOIN cube_question_summary_overall qso
              ON qso.school_id = qs.school_id
             AND qso.ukey = qs.ukey
            WHERE qs.item_id = :item_id
              AND qs.question_id = :question_id
            LIMIT 1
            """
        )
        result = await self.session.execute(
            sql, {"item_id": item_id, "question_id": question_id}
        )
        row = result.first()
        return _row_to_dict(row) if row else None

    async def get_distractor_breakdown(
        self, item_id: str, question_id: str
    ) -> List[Dict[str, Any]]:
        """Per-answer-choice rollup for one question (cube_questionincorrectchoice_summary).

        Empty/null answer_submission rows are dropped (matches PBIX M filter).
        """
        sql = text(
            """
            WITH item_qids AS (
                SELECT DISTINCT question_id
                FROM cube_question_summary
                WHERE item_id = :item_id
                  AND question_id = :question_id
            ),
            choices AS (
                SELECT
                    qic.answer_submission,
                    SUM(qic.total_student)        AS students_count,
                    SUM(qic.total_score)          AS total_score,
                    SUM(qic.total_possible_point) AS total_possible_point
                FROM cube_questionincorrectchoice_summary qic
                JOIN item_qids iq ON iq.question_id = qic.question_id
                WHERE qic.answer_submission IS NOT NULL
                  AND qic.answer_submission <> ''
                GROUP BY qic.answer_submission
            ),
            totals AS (
                SELECT SUM(students_count) AS total_students FROM choices
            )
            SELECT
                c.answer_submission,
                c.students_count,
                CASE
                  WHEN t.total_students > 0
                  THEN c.students_count::numeric / t.total_students::numeric
                  ELSE 0
                END                                              AS share_of_attempts,
                CASE
                  WHEN c.total_possible_point > 0
                       AND c.total_score >= c.total_possible_point
                  THEN TRUE ELSE FALSE
                END                                              AS is_correct
            FROM choices c
            CROSS JOIN totals t
            ORDER BY c.students_count DESC NULLS LAST, c.answer_submission
            """
        )
        result = await self.session.execute(
            sql, {"item_id": item_id, "question_id": question_id}
        )
        return [_row_to_dict(r) for r in result.all()]

    async def get_per_student_attempts(
        self, item_id: str, question_id: str
    ) -> List[Dict[str, Any]]:
        """Every student × this question row for the IAD per-student table."""
        sql = text(
            """
            SELECT
                COALESCE(fss.user_uid, '')                       AS user_uid,
                COALESCE(NULLIF(fss.user_name, ''), '—')         AS user_name,
                COALESCE(fss.answer_submission, '')              AS answer_submission,
                COALESCE(fss.correct_answer, '')                 AS correct_answer,
                COALESCE(fss.points_received, 0)::numeric        AS points_received,
                COALESCE(fss.points_possible, 0)::numeric        AS points_possible,
                CASE
                  WHEN COALESCE(fss.points_possible, 0) > 0
                  THEN COALESCE(fss.points_received, 0)::numeric
                       / COALESCE(fss.points_possible, 0)::numeric
                  ELSE 0
                END                                              AS score_pct,
                CASE
                  WHEN COALESCE(fss.points_possible, 0) > 0
                       AND COALESCE(fss.points_received, 0) >= COALESCE(fss.points_possible, 0)
                  THEN TRUE ELSE FALSE
                END                                              AS is_correct,
                fss.latest_attempt
            FROM fact_student_submission fss
            WHERE fss.item_id = :item_id
              AND fss.question_id = :question_id
              AND fss.user_uid IS NOT NULL
            ORDER BY fss.user_name
            """
        )
        result = await self.session.execute(
            sql, {"item_id": item_id, "question_id": question_id}
        )
        return [_row_to_dict(r) for r in result.all()]

    async def get_ytd_strand_heatmap(self) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT
                ds.strand                                              AS strand,
                di.assessment_date                                     AS date,
                CASE WHEN SUM(cs.total_possible_point) > 0
                     THEN SUM(cs.total_score)::numeric
                          / SUM(cs.total_possible_point)::numeric
                     ELSE 0
                END                                                    AS grade_average
            FROM cube_standard_summary cs
            JOIN dim_item di
              ON di.item_id = cs.item_id
            JOIN dim_strand ds
              ON ds.strand_id = cs.strand_id
             AND ds.identifier = cs.identifier
            WHERE ds.strand IS NOT NULL
              AND di.assessment_date IS NOT NULL
            GROUP BY ds.strand, di.assessment_date
            ORDER BY ds.strand, di.assessment_date
            """
        )
        result = await self.session.execute(sql)
        return [_row_to_dict(r) for r in result.all()]
