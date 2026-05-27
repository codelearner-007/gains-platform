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


# Shared filter fragment for school-wide rollup queries that scope by
# session / subject / grade / assessment_type / section against
# cube_question_summary (alias ``qs``). Inlined into the WITH-clause WHERE
# of get_school_strand_rollup + get_school_standard_rollup so both queries
# stay byte-identical and only need bind-dict params from
# ``_school_filter_params``.
_QS_SCHOOL_FILTER_SQL = """\
(CAST(:session_filter AS TEXT) IS NULL OR qs.session = CAST(:session_filter AS TEXT))
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
                      )"""


def _school_filter_params(
    session_filter: Optional[str],
    subject: Optional[str],
    grade: Optional[str],
    category: Optional[str],
    section: Optional[str],
) -> Dict[str, Any]:
    """Bind-dict for the shared 5-filter WHERE clause."""
    return {
        "session_filter": session_filter,
        "subject": subject,
        "grade": grade,
        "category": category,
        "section": section,
    }


# YTD filter clauses — cube_user_summary has session/grade/subject/assessment_type
# directly; section dereferences via dim_section.
_CUS_YTD_FILTER_SQL = """\
(CAST(:session_filter AS TEXT) IS NULL OR cus.session = CAST(:session_filter AS TEXT))
              AND (CAST(:subject AS TEXT) IS NULL OR cus.subject = CAST(:subject AS TEXT))
              AND (CAST(:grade AS TEXT) IS NULL OR cus.grade = CAST(:grade AS TEXT))
              AND (CAST(:category AS TEXT) IS NULL OR cus.assessment_type = CAST(:category AS TEXT))
              AND (
                    CAST(:section AS TEXT) IS NULL
                 OR cus.section_nid = CAST(:section AS TEXT)
                 OR EXISTS (
                      SELECT 1 FROM dim_section dsec
                      WHERE dsec.school_id = cus.school_id
                        AND dsec.item_id = cus.item_id
                        AND (
                          dsec.section_name = CAST(:section AS TEXT)
                       OR dsec.section_code = CAST(:section AS TEXT)
                       OR dsec.section_nid  = CAST(:section AS TEXT)
                        )
                    )
                  )"""

# YTD filter clause for cube_question_summary_overall — joins dim_subject for
# session/grade/subject/category since cqso only carries subject_id. Section
# filter is not meaningful at the per-question grain (section is a
# class-roster construct), so it is intentionally ignored here.
_CQSO_YTD_FILTER_SQL = """\
(CAST(:session_filter AS TEXT) IS NULL OR dsubj.session = CAST(:session_filter AS TEXT))
              AND (CAST(:subject AS TEXT) IS NULL OR dsubj.subject = CAST(:subject AS TEXT))
              AND (CAST(:grade AS TEXT) IS NULL OR dsubj.grade = CAST(:grade AS TEXT))
              AND (CAST(:category AS TEXT) IS NULL OR dsubj.assessment_type = CAST(:category AS TEXT))"""


class CubeRepository:
    """Reads from the cube_* and supporting fact tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ────────────────────────────────────────────────────────────────────
    # Canonical KPI helper for one assessment.
    #
    # Single source of truth for the KPI strip shown on QRA + SDD (and any
    # future per-assessment report). Replicates the legacy PBIX DAX
    # semantics that the read-only audit (see
    # ``.hermes/report-parity/FRESH-RCA-2026-05-18-stable-formulas.md``)
    # identified, namely:
    #
    #   * Total Students   = ``cube_school_summary.total_students``.
    #   * Total Questions  = ``DISTINCTCOUNT(Question_No)`` over the
    #     per-question canonical CTE (one row per question_id).
    #   * Total Standards  = ``COUNT(DISTINCT standard)`` over
    #     ``dim_question_data`` for the item — counts raw long-form
    #     ``standards_val`` labels, matching legacy
    #     ``DISTINCTCOUNT(cube_question_summary_overall[Standards])``.
    #   * Grade Average / Min / Max = computed from per-(question, user)
    #     collapsed scores on ``fact_student_submission``. The fact is
    #     deduped per ``(user_uid, question_id, position_number)`` first
    #     so the 9-part PK's standard-alias fan-out (an architectural
    #     choice that inflates fact 2.43×) does not bias the average.
    #     Each question's average is then taken across students,
    #     followed by AVG/MIN/MAX across questions. Mirrors the legacy
    #     DAX ``AVERAGE / MAXX / MINX VALUES(Question_No)`` semantics
    #     with a per-user collapse to undo the alias fan-out.
    #   * total_possible_point / total_score pass through from
    #     ``cube_school_summary``.
    #
    # Both QRA and SDD MUST call this helper for their KPI strips so
    # they cannot diverge. Per-assessment regression tests assert
    # this for item ``8359960427`` (12 standards / ~65.4% / ~96.3% /
    # ~27.8%) and the single-strand control ``7892351049``.
    # ────────────────────────────────────────────────────────────────────
    async def get_canonical_kpis_for_item(
        self, item_id: str
    ) -> Optional[Dict[str, Any]]:
        sql = text(
            """
            WITH fact_dedup AS (
                SELECT DISTINCT ON (user_uid, question_id, position_number)
                       user_uid, question_id, position_number,
                       points_received, points_possible
                FROM fact_student_submission
                WHERE item_id = :item_id
                  AND points_possible IS NOT NULL
                  AND points_possible > 0
                ORDER BY user_uid, question_id, position_number, identifier NULLS LAST
            ),
            per_user_q AS (
                SELECT question_id, user_uid,
                       SUM(points_received)::numeric
                         / NULLIF(SUM(points_possible), 0) AS pct
                FROM fact_dedup
                GROUP BY question_id, user_uid
            ),
            per_q AS (
                SELECT question_id, AVG(pct) AS qga
                FROM per_user_q
                GROUP BY question_id
            ),
            school AS (
                SELECT total_students, total_possible_point, total_score
                FROM cube_school_summary
                WHERE item_id = :item_id
                LIMIT 1
            ),
            std AS (
                SELECT COUNT(DISTINCT standard) AS total_standards
                FROM dim_question_data
                WHERE item_id = :item_id
                  AND standard IS NOT NULL
                  AND standard NOT IN ('', 'null')
            )
            SELECT
                (SELECT total_students FROM school)        AS total_students,
                (SELECT COUNT(*) FROM per_q)               AS total_questions,
                (SELECT total_standards FROM std)          AS total_standards,
                (SELECT AVG(qga) FROM per_q)               AS grade_average,
                (SELECT MAX(qga) FROM per_q)               AS grade_max,
                (SELECT MIN(qga) FROM per_q)               AS grade_min,
                (SELECT total_possible_point FROM school)  AS total_possible_point,
                (SELECT total_score FROM school)           AS total_score
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        row = result.first()
        return _row_to_dict(row) if row else None

    async def get_canonical_per_question_grades(
        self, item_id: str
    ) -> List[Dict[str, Any]]:
        """Per-question grade_average using the canonical per-user collapse.

        Used to override the per-question grade on the QRA question table
        for multi-select / multi-position questions whose
        ``cube_question_summary.grade_average`` reflects row-grain
        SUM/SUM (e.g. Q12 = 35/146 = 23.97%) rather than per-student
        average (27.78%). This matches the KPI strip's per-question grain
        so the per-question table cannot disagree with the Lowest/Highest
        KPI for the same item.
        """
        sql = text(
            """
            WITH fact_dedup AS (
                SELECT DISTINCT ON (user_uid, question_id, position_number)
                       user_uid, question_id, position_number,
                       points_received, points_possible
                FROM fact_student_submission
                WHERE item_id = :item_id
                  AND points_possible IS NOT NULL
                  AND points_possible > 0
                ORDER BY user_uid, question_id, position_number, identifier NULLS LAST
            ),
            per_user_q AS (
                SELECT question_id, user_uid,
                       SUM(points_received)::numeric
                         / NULLIF(SUM(points_possible), 0) AS pct
                FROM fact_dedup
                GROUP BY question_id, user_uid
            )
            SELECT question_id, AVG(pct) AS grade_average
            FROM per_user_q
            GROUP BY question_id
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        return [_row_to_dict(r) for r in result.all()]

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
    async def get_questions_overall_for_item(self, item_id: str) -> List[Dict[str, Any]]:
        """One row per (item_id, question_id) for an assessment.

        ``cube_question_summary`` carries one row per (question × sub-question)
        and ``cube_question_summary_overall`` carries one row per (school × ukey
        × section/replication) — a naive LEFT JOIN multiplies the result set
        (Q1 → 4 rows, Q13 → 16, etc.). We pre-aggregate both sides:

        * ``qs_agg`` picks the first sub-question row per question_id (text
          fields) and ``qs_num`` AVGs/SUMs the numerics across sub-questions.
        * ``qso_agg`` picks one row per (school_id, ukey) and ``qso_num``
          AVGs/SUMs the per-section numerics. This mirrors the
          ``AVG(grade_average)`` aggregation the strand/standard rollup
          queries already use against the same table.
        """
        sql = text(
            """
            WITH qs_agg AS (
                SELECT DISTINCT ON (item_id, question_id)
                    school_id, item_id, question_id, ukey, question_no,
                    position_number, question, question_type, correct_answer,
                    standard
                FROM cube_question_summary
                WHERE item_id = :item_id
                ORDER BY item_id, question_id,
                         NULLIF(regexp_replace(COALESCE(position_number, ''), '[^0-9]', '', 'g'), '')::int NULLS LAST,
                         position_number
            ),
            qs_num AS (
                SELECT item_id, question_id,
                       AVG(grade_average)                AS grade_average,
                       AVG(percentage_incorrect_answers) AS percentage_incorrect,
                       SUM(total_possible_point)         AS total_possible_point,
                       SUM(total_score)                  AS total_score,
                       MAX(NULLIF(incorrect_choice_details, '')) AS incorrect_choice_details,
                       MAX(NULLIF(incorrect_details_name, ''))   AS incorrect_details_name
                FROM cube_question_summary
                WHERE item_id = :item_id
                GROUP BY item_id, question_id
            ),
            -- Aggregate ALL Schoology standards per question. cube_question_summary
            -- carries only one alias per question (collapsed via LATERAL LIMIT 1
            -- against dim_question_data in 09_cubes/cube_question_summary.sql).
            -- dim_question_data retains every alias the parser emitted, so we
            -- read directly from it to recover the full list. Newline-joined so
            -- the frontend can render one standard per line.
            qd_standards AS (
                SELECT
                    item_id,
                    question_id,
                    STRING_AGG(DISTINCT standard, E'\n' ORDER BY standard) AS standards
                FROM dim_question_data
                WHERE item_id = :item_id
                  AND standard IS NOT NULL AND standard <> ''
                GROUP BY item_id, question_id
            ),
            -- Mirrors legacy DAX `CombineDescriptionsColumn`
            -- (04_dax_measures.dax:1200-1254). Legacy concatenates all
            -- distinct standards, takes the alphabetical-first non-"Other"
            -- one, and looks up that single standard's description. We
            -- replicate that here in SQL because cube_question_summary
            -- collapses to a single (lex-min identifier) standard per
            -- question — losing the alphabetical-first standard's
            -- description that legacy renders. Source the text from
            -- dim_standard directly, keyed by the chosen Schoology code.
            qd_first_standard AS (
                SELECT
                    item_id,
                    question_id,
                    MIN(standard) FILTER (
                        WHERE standard IS NOT NULL
                          AND standard <> ''
                          AND LOWER(standard) <> 'other'
                    ) AS first_standard
                FROM dim_question_data
                WHERE item_id = :item_id
                GROUP BY item_id, question_id
            ),
            qd_description AS (
                SELECT
                    qfs.item_id,
                    qfs.question_id,
                    -- MAX() guards against the rare case where the seed
                    -- has two dim_standard rows for the same
                    -- schoology_standard (duplicate alias on a single
                    -- identifier); descriptions are expected identical.
                    MAX(ds.description) AS description
                FROM qd_first_standard qfs
                LEFT JOIN dim_standard ds
                  ON ds.schoology_standard = qfs.first_standard
                GROUP BY qfs.item_id, qfs.question_id
            ),
            qso_agg AS (
                SELECT DISTINCT ON (school_id, ukey)
                    school_id, ukey, question_no, question, correct_answer,
                    incorrect_choice_details, incorrect_details_name,
                    description
                FROM cube_question_summary_overall
                ORDER BY school_id, ukey
            ),
            qso_num AS (
                SELECT school_id, ukey,
                       AVG(grade_average)                AS grade_average,
                       AVG(percentage_incorrect_answers) AS percentage_incorrect,
                       SUM(total_possible_point)         AS total_possible_point,
                       SUM(total_score)                  AS total_score
                FROM cube_question_summary_overall
                GROUP BY school_id, ukey
            )
            SELECT
                qs.question_id,
                COALESCE(qso.question_no, qs.question_no)                       AS question_no,
                qs.position_number,
                COALESCE(qso.question, qs.question)                             AS question,
                qs.question_type,
                COALESCE(qso.correct_answer, qs.correct_answer)                 AS correct_answer,
                COALESCE(qsn.total_possible_point, qson.total_possible_point)   AS total_possible_point,
                COALESCE(qsn.total_score, qson.total_score)                     AS total_score,
                COALESCE(qsn.grade_average, qson.grade_average)                 AS grade_average,
                COALESCE(qsn.percentage_incorrect, qson.percentage_incorrect)   AS percentage_incorrect,
                COALESCE(qso.incorrect_choice_details, qsn.incorrect_choice_details, '') AS incorrect_choice_details,
                COALESCE(qso.incorrect_details_name, qsn.incorrect_details_name, '')     AS incorrect_details_name,
                COALESCE(qdst.standards, '')                                    AS standards,
                qs.standard                                                     AS strand_raw,
                COALESCE(qdd.description, qso.description, '')                  AS description
            FROM qs_agg qs
            LEFT JOIN qs_num         qsn  ON qsn.item_id    = qs.item_id  AND qsn.question_id = qs.question_id
            LEFT JOIN qd_standards   qdst ON qdst.item_id   = qs.item_id  AND qdst.question_id = qs.question_id
            LEFT JOIN qd_description qdd  ON qdd.item_id    = qs.item_id  AND qdd.question_id  = qs.question_id
            LEFT JOIN qso_agg        qso  ON qso.school_id  = qs.school_id AND qso.ukey       = qs.ukey
            LEFT JOIN qso_num        qson ON qson.school_id = qs.school_id AND qson.ukey      = qs.ukey
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

    # ────────────────────────────────────────────────────────────────────
    # Per-assessment strand / standard rollups (Standards Deep Dive interactive page
    # AND the QRA Strands/Standards summary tables).
    # ────────────────────────────────────────────────────────────────────
    async def get_strand_rollup_for_item(
        self, item_id: str
    ) -> List[Dict[str, Any]]:
        """One row per Strand for a given assessment.

        Per ``_pbix_extract/50_sdd_spec.md`` §4.5 the per-strand row strip
        reports ``COUNT(DISTINCT question_no)`` and the question-weighted
        grade average. Sourced from ``cube_question_summary`` joined to
        ``dim_standard`` for the strand label.

        ``num_standards`` is counted at the **schoology_standard grain** —
        the Schoology canonical long form rendered by
        ``get_standard_rollup_for_item``. Each unique Schoology code per
        strand contributes one entry.

        Restricts identifiers via an exact-match join on the item's
        ``dim_question_data.standard`` set so unaligned assessments yield
        zero strand rows.
        """
        sql = text(
            """
            WITH item_codes AS (
                SELECT DISTINCT standard AS code
                FROM dim_question_data
                WHERE item_id = :item_id
                  AND standard IS NOT NULL
                  AND standard NOT IN ('', 'null')
            ),
            labeled AS (
                SELECT DISTINCT
                    ds.identifier,
                    ds.schoology_standard,
                    ds.strand
                FROM dim_standard ds
                JOIN item_codes ic ON ds.schoology_standard = ic.code
                WHERE ds.strand IS NOT NULL AND ds.strand <> ''
                  AND ds.schoology_standard IS NOT NULL
                  AND ds.schoology_standard <> ''
            ),
            strand_standards AS (
                SELECT
                    strand,
                    COUNT(DISTINCT schoology_standard) AS num_standards
                FROM labeled
                GROUP BY strand
            ),
            strand_metrics AS (
                SELECT
                    ds.strand                              AS strand,
                    COUNT(DISTINCT cqs.question_no)        AS num_questions,
                    AVG(cqs.grade_average)                 AS grade_average
                FROM cube_question_summary cqs
                JOIN dim_standard ds
                  ON ds.identifier = cqs.identifier
                JOIN labeled l
                  ON l.identifier = cqs.identifier
                WHERE cqs.item_id = :item_id
                  AND ds.strand IS NOT NULL
                  AND ds.strand <> ''
                GROUP BY ds.strand
            )
            SELECT
                sm.strand          AS strand,
                ss.num_standards   AS num_standards,
                sm.num_questions   AS num_questions,
                sm.grade_average   AS grade_average
            FROM strand_metrics sm
            JOIN strand_standards ss ON ss.strand = sm.strand
            ORDER BY sm.strand
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        return [_row_to_dict(r) for r in result.all()]

    async def get_standard_rollup_for_item(
        self, item_id: str
    ) -> List[Dict[str, Any]]:
        """One row per Schoology canonical standard for a given assessment.

        Each ``schoology_standard`` code that the assessment's
        ``standards_val`` set resolves to renders as its own row
        (e.g. ``MA.912.AR.3.1`` and ``AI.MA.912.AR.3.1`` both render
        because the item carries both aliases). This is the long
        Schoology canonical form — the same string Schoology emits in
        its raw Question-Data CSV.

        Restricts the output to exact-match dim_standard rows whose
        ``schoology_standard`` appears in ``dim_question_data.standard``
        for this item.

        ``num_questions`` = ``COUNT(DISTINCT question_no)`` per matched
        identifier. ``grade_average`` = AVG of per-question grade_average
        from ``cube_question_summary`` for the identifier.
        """
        sql = text(
            """
            WITH item_codes AS (
                SELECT DISTINCT standard AS code
                FROM dim_question_data
                WHERE item_id = :item_id
                  AND standard IS NOT NULL
                  AND standard NOT IN ('', 'null')
            ),
            labeled AS (
                SELECT DISTINCT
                    ds.identifier,
                    ds.schoology_standard,
                    ds.strand
                FROM dim_standard ds
                JOIN item_codes ic ON ds.schoology_standard = ic.code
                WHERE ds.strand IS NOT NULL AND ds.strand <> ''
                  AND ds.schoology_standard IS NOT NULL
                  AND ds.schoology_standard <> ''
            ),
            per_identifier AS (
                SELECT
                    cqs.identifier,
                    COUNT(DISTINCT cqs.question_no) AS num_questions,
                    AVG(cqs.grade_average)          AS grade_average
                FROM cube_question_summary cqs
                WHERE cqs.item_id = :item_id
                GROUP BY cqs.identifier
            )
            SELECT
                l.schoology_standard                                         AS schoology_standard,
                l.strand                                                     AS strand,
                MAX(COALESCE(p.num_questions, 0))                            AS num_questions,
                MAX(COALESCE(p.grade_average, 0))                            AS grade_average
            FROM labeled l
            LEFT JOIN per_identifier p ON p.identifier = l.identifier
            GROUP BY l.schoology_standard, l.strand
            ORDER BY l.strand, l.schoology_standard
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        return [_row_to_dict(r) for r in result.all()]

    async def get_standard_bands_for_item(
        self, item_id: str
    ) -> List[Dict[str, Any]]:
        """One row per schoology_standard for the SDD 100%-stacked band charts.

        Per PBIX spec (``50_sdd_spec.md`` §4.4) the three band panels
        ("At Target", "Approaching", "Needs Attention") render bars keyed
        on the Schoology canonical standard. Service layer buckets the
        returned rows into high/mid/low based on the standard 70/80
        thresholds.

        Uses the same exact-match restriction as
        ``get_standard_rollup_for_item`` so band bars and the per-standard
        table render the same set of Schoology codes.
        """
        sql = text(
            """
            WITH item_codes AS (
                SELECT DISTINCT standard AS code
                FROM dim_question_data
                WHERE item_id = :item_id
                  AND standard IS NOT NULL
                  AND standard NOT IN ('', 'null')
            ),
            labeled AS (
                SELECT DISTINCT
                    ds.identifier,
                    ds.schoology_standard,
                    ds.strand
                FROM dim_standard ds
                JOIN item_codes ic ON ds.schoology_standard = ic.code
                WHERE ds.strand IS NOT NULL AND ds.strand <> ''
                  AND ds.schoology_standard IS NOT NULL
                  AND ds.schoology_standard <> ''
            ),
            per_identifier AS (
                SELECT
                    cqs.identifier,
                    COUNT(DISTINCT cqs.question_no) AS num_questions,
                    AVG(cqs.grade_average)          AS grade_average
                FROM cube_question_summary cqs
                WHERE cqs.item_id = :item_id
                GROUP BY cqs.identifier
            )
            SELECT
                l.schoology_standard                                         AS schoology_standard,
                l.strand                                                     AS strand,
                MAX(COALESCE(p.num_questions, 0))                            AS num_questions,
                MAX(COALESCE(p.grade_average, 0))                            AS grade_average
            FROM labeled l
            LEFT JOIN per_identifier p ON p.identifier = l.identifier
            GROUP BY l.schoology_standard, l.strand
            ORDER BY l.schoology_standard
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # School-wide rollups (Standard Summary + Strand Summary)
    # ────────────────────────────────────────────────────────────────────
    async def get_school_wide_meta(self) -> Optional[Dict[str, Any]]:
        """School id + name + logo + the predominant session label.

        Returns the same shape as ``get_ytd_school_meta`` but exposed under
        a more general name so the standard/strand summary endpoints can
        share it with YTD without coupling.
        """
        sql = text(
            """
            SELECT
                di.school_id::text                            AS school_id,
                COALESCE(s.name, '')                          AS name,
                COALESCE(s.logo_url, '')                      AS logo_url,
                COALESCE(MAX(dsubj.session), '')              AS current_session
            FROM dim_item di
            LEFT JOIN dim_subject dsubj
              ON dsubj.school_id = di.school_id
             AND dsubj.subject_id = di.subject_id
            LEFT JOIN public.schools s
              ON s.school_id = di.school_id
            GROUP BY di.school_id, s.name, s.logo_url
            LIMIT 1
            """
        )
        result = await self.session.execute(sql)
        row = result.first()
        return _row_to_dict(row) if row else None

    async def get_school_total_assessments(
        self,
        session_filter: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        category: Optional[str] = None,
        section: Optional[str] = None,
    ) -> int:
        """Distinct assessments (item_ids) within the chosen filter scope."""
        sql = text(
            f"""
            SELECT COUNT(DISTINCT cus.item_id) AS total_assessments
            FROM cube_user_summary cus
            WHERE {_CUS_YTD_FILTER_SQL}
            """
        )
        result = await self.session.execute(
            sql,
            _school_filter_params(session_filter, subject, grade, category, section),
        )
        row = result.first()
        return int(row._mapping["total_assessments"]) if row else 0

    async def get_school_overall_grade_average(
        self,
        session_filter: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        category: Optional[str] = None,
        section: Optional[str] = None,
    ) -> float:
        """Re-aggregated AVG(cqso.grade_average) over filter scope.

        Mirrors DAX ``Grade_Average_Standard_Measure``. Section filter
        ignored at this grain (section is a class-roster construct,
        questions are below it).
        """
        sql = text(
            f"""
            SELECT COALESCE(AVG(cqso.grade_average), 0)::float AS overall_avg
            FROM cube_question_summary_overall cqso
            LEFT JOIN dim_subject dsubj
              ON dsubj.school_id = cqso.school_id
             AND dsubj.subject_id = cqso.subject_id
            WHERE {_CQSO_YTD_FILTER_SQL}
            """
        )
        result = await self.session.execute(
            sql,
            _school_filter_params(session_filter, subject, grade, category, section),
        )
        row = result.first()
        return float(row._mapping["overall_avg"]) if row else 0.0

    async def get_school_total_questions(
        self,
        session_filter: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        category: Optional[str] = None,
        section: Optional[str] = None,
    ) -> int:
        """DISTINCTCOUNT(ukey) over cube_question_summary_overall.

        Matches PBIX DAX ``Total Question = DISTINCTCOUNT(cqso[Question_No])``.
        Section filter ignored at this grain (questions are below section).
        """
        sql = text(
            f"""
            SELECT COUNT(DISTINCT cqso.ukey) AS total_questions
            FROM cube_question_summary_overall cqso
            LEFT JOIN dim_subject dsubj
              ON dsubj.school_id = cqso.school_id
             AND dsubj.subject_id = cqso.subject_id
            WHERE {_CQSO_YTD_FILTER_SQL}
            """
        )
        result = await self.session.execute(
            sql,
            _school_filter_params(session_filter, subject, grade, category, section),
        )
        row = result.first()
        return int(row._mapping["total_questions"]) if row else 0

    async def get_school_data_refreshed_at(self) -> Optional[str]:
        """Most-recent dim_standard.last_change_date_time, ISO formatted.

        Surfaced as the "Data refreshed" footer line on report pages.
        """
        sql = text(
            """
            SELECT MAX(last_change_date_time) AS d
            FROM dim_standard
            """
        )
        result = await self.session.execute(sql)
        row = result.first()
        if row is None:
            return None
        d = row._mapping["d"]
        return d.isoformat() if d else None

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
            _school_filter_params(session_filter, subject, grade, category, section),
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
            f"""
            WITH scoped_qs AS (
                SELECT DISTINCT
                    qs.school_id,
                    qs.ukey,
                    qs.identifier,
                    qs.item_id,
                    qs.subject
                FROM cube_question_summary qs
                WHERE {_QS_SCHOOL_FILTER_SQL}
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
            _school_filter_params(session_filter, subject, grade, category, section),
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
            f"""
            WITH scoped_qs AS (
                SELECT DISTINCT
                    qs.school_id,
                    qs.ukey,
                    qs.identifier,
                    qs.item_id,
                    qs.grade
                FROM cube_question_summary qs
                WHERE {_QS_SCHOOL_FILTER_SQL}
            ),
            std_q AS (
                SELECT DISTINCT
                    iq.ukey,
                    iq.identifier,
                    iq.item_id,
                    iq.grade,
                    ds.strand,
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
                    SELECT schoology_standard, cluster,
                           cognitive_complexity_rating, subject,
                           custom_cleaned_description, description,
                           last_change_date_time
                    FROM dim_standard
                    WHERE identifier = iq.identifier
                    LIMIT 1
                ) dst ON TRUE
                WHERE COALESCE(NULLIF(dst.schoology_standard, ''), '') <> ''
                  AND (CAST(:strand AS TEXT) IS NULL OR ds.strand = CAST(:strand AS TEXT))
            ),
            qso_avg AS (
                SELECT ukey, AVG(grade_average) AS grade_average
                FROM cube_question_summary_overall
                GROUP BY ukey
            )
            SELECT
                COALESCE(sq.schoology_standard, '')                AS schoology_standard,
                COALESCE(sq.strand, '')                            AS strand,
                COALESCE(sq.cluster, '')                           AS cluster,
                COALESCE(sq.cognitive_complexity_rating, '')       AS cognitive_complexity,
                COALESCE(NULLIF(sq.custom_cleaned_description, ''),
                         sq.description, '')                       AS description,
                COALESCE(sq.std_subject, '')                       AS subject,
                COALESCE(
                    array_agg(DISTINCT NULLIF(sq.grade, ''))
                      FILTER (WHERE NULLIF(sq.grade, '') IS NOT NULL),
                    ARRAY[]::text[]
                )                                                  AS grades,
                COUNT(DISTINCT sq.ukey)                            AS num_questions,
                COUNT(DISTINCT sq.item_id)                         AS num_assessments,
                AVG(COALESCE(qa.grade_average, 0))                 AS grade_average,
                MAX(sq.last_change_date_time)                      AS last_change_date_time
            FROM std_q sq
            LEFT JOIN qso_avg qa ON qa.ukey = sq.ukey
            GROUP BY 1, 2, 3, 4, 5, 6
            ORDER BY 2 NULLS LAST, 1
            """
        )
        result = await self.session.execute(
            sql,
            {
                **_school_filter_params(
                    session_filter, subject, grade, category, section
                ),
                "strand": strand,
            },
        )
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # Standards-alignment data quality
    # ────────────────────────────────────────────────────────────────────
    #
    # When the Schoology Test/Quiz "Export Stats" CSV ships zero Standards
    # columns (because instructors never aligned questions to learning
    # objectives in Schoology), dim_question_data.standard / identifier
    # stay NULL and every downstream join silently drops the row. The
    # methods below quantify that gap so the UI can render a precise
    # empty state and an admin can find the items that need alignment.
    # Counted at the (item_id, question_id) grain so we're not biased by
    # answer-option multiplicity.

    async def get_alignment_quality_for_item(
        self, item_id: str
    ) -> Dict[str, int]:
        """Count distinct questions vs. distinct aligned-questions for one item.

        Returns four counters at the (item_id, question_id) grain so the
        service layer can distinguish *why* an item has zero alignment:

        * ``questions_total`` — total distinct question rows on the item.
        * ``questions_with_alignment`` — distinct questions whose ``standard``
          label resolved to a ``dim_standard.identifier`` via the exact-match
          join in ``dim_question_data``.
        * ``nonempty_standards_count`` — distinct non-null, non-empty raw
          standard labels seen in the source CSV. ``0`` means the Schoology
          "Export Stats" CSV shipped zero ``Standards{N}`` columns (Category
          A in the empty-state RCA: instructor never used "Align Learning
          Objective"). ``>0`` with zero ``questions_with_alignment`` means
          labels exist but none mapped (Category B: label like
          ``"Social Studies"`` that isn't a real CPALMS code).
        * ``distinct_unmatched_label_count`` — distinct raw labels that
          failed the exact-match join (``identifier IS NULL``). Used to gate
          the Category-B copy and to size the unmatched-label list in
          ``_build_alignment_data_quality_for_item``.
        """
        sql = text(
            """
            SELECT
                COUNT(DISTINCT question_id) AS questions_total,
                COUNT(DISTINCT question_id)
                  FILTER (WHERE identifier IS NOT NULL)
                  AS questions_with_alignment,
                COUNT(DISTINCT standard)
                  FILTER (WHERE standard IS NOT NULL AND standard <> '')
                  AS nonempty_standards_count,
                COUNT(DISTINCT standard)
                  FILTER (
                    WHERE standard IS NOT NULL
                      AND standard <> ''
                      AND identifier IS NULL
                  )
                  AS distinct_unmatched_label_count
            FROM dim_question_data
            WHERE item_id = :item_id
            """
        )
        row = (await self.session.execute(sql, {"item_id": item_id})).first()
        if row is None:
            return {
                "questions_total": 0,
                "questions_with_alignment": 0,
                "nonempty_standards_count": 0,
                "distinct_unmatched_label_count": 0,
            }
        d = _row_to_dict(row)
        return {
            "questions_total": int(d.get("questions_total") or 0),
            "questions_with_alignment": int(d.get("questions_with_alignment") or 0),
            "nonempty_standards_count": int(d.get("nonempty_standards_count") or 0),
            "distinct_unmatched_label_count": int(
                d.get("distinct_unmatched_label_count") or 0
            ),
        }

    async def get_unmatched_alignment_labels_for_item(
        self, item_id: str, limit: int = 5
    ) -> List[str]:
        """Return distinct raw standard labels that failed to map to a CPALMS code.

        Used by ``_build_alignment_data_quality_for_item`` when
        ``cause == "labels_not_mapped"`` so the empty-state card can list
        the offending labels (e.g. ``"Social Studies"`` on a Grade K Math
        assessment). Sorted alphabetically; capped at ``limit`` so a
        pathological item with hundreds of malformed labels doesn't bloat
        the payload.
        """
        sql = text(
            """
            SELECT DISTINCT standard
            FROM dim_question_data
            WHERE item_id = :item_id
              AND standard IS NOT NULL
              AND standard <> ''
              AND identifier IS NULL
            ORDER BY standard
            LIMIT :limit
            """
        )
        result = await self.session.execute(
            sql, {"item_id": item_id, "limit": int(limit)}
        )
        return [str(r[0]) for r in result.all() if r[0] is not None]

    async def get_school_alignment_quality(
        self,
        *,
        session_filter: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        category: Optional[str] = None,
        section: Optional[str] = None,
    ) -> Dict[str, int]:
        """Aggregate alignment coverage across all items matching the filters."""
        sql = text(
            """
            WITH per_item AS (
                SELECT
                    dqd.item_id,
                    COUNT(DISTINCT dqd.question_id) AS qs_total,
                    COUNT(DISTINCT dqd.question_id)
                      FILTER (WHERE dqd.identifier IS NOT NULL) AS qs_aligned
                FROM dim_question_data dqd
                WHERE (CAST(:session_filter AS TEXT) IS NULL OR dqd.session = CAST(:session_filter AS TEXT))
                  AND (CAST(:subject AS TEXT) IS NULL OR dqd.subject = CAST(:subject AS TEXT))
                  AND (CAST(:grade AS TEXT) IS NULL OR dqd.grade = CAST(:grade AS TEXT))
                  AND (CAST(:category AS TEXT) IS NULL OR dqd.assessment_type = CAST(:category AS TEXT))
                  AND (CAST(:section AS TEXT) IS NULL OR dqd.section = CAST(:section AS TEXT))
                GROUP BY dqd.item_id
            )
            SELECT
                COUNT(*)                                       AS items_total,
                COUNT(*) FILTER (WHERE qs_aligned > 0)         AS items_with_alignment,
                COALESCE(SUM(qs_total), 0)                     AS questions_total,
                COALESCE(SUM(qs_aligned), 0)                   AS questions_with_alignment
            FROM per_item
            """
        )
        params = _school_filter_params(
            session_filter, subject, grade, category, section
        )
        row = (await self.session.execute(sql, params)).first()
        if row is None:
            return {
                "items_total": 0,
                "items_with_alignment": 0,
                "questions_total": 0,
                "questions_with_alignment": 0,
            }
        d = _row_to_dict(row)
        return {
            "items_total": int(d.get("items_total") or 0),
            "items_with_alignment": int(d.get("items_with_alignment") or 0),
            "questions_total": int(d.get("questions_total") or 0),
            "questions_with_alignment": int(d.get("questions_with_alignment") or 0),
        }

    async def list_alignment_quality_by_item(self) -> List[Dict[str, Any]]:
        """Per-item alignment-coverage rows for the admin DQ list.

        Joins ``dim_question_data`` to ``dim_item`` for the item_name +
        item_type display fields. ``subject`` / ``grade`` come from
        ``dim_question_data`` (already overridden / normalised at staging).
        """
        sql = text(
            """
            WITH per_item AS (
                SELECT
                    dqd.item_id,
                    MAX(dqd.subject) AS subject,
                    MAX(dqd.grade)   AS grade,
                    COUNT(DISTINCT dqd.question_id) AS qs_total,
                    COUNT(DISTINCT dqd.question_id)
                      FILTER (WHERE dqd.identifier IS NOT NULL) AS qs_aligned
                FROM dim_question_data dqd
                GROUP BY dqd.item_id
            )
            SELECT
                pi.item_id,
                COALESCE(di.item_name, '') AS item_name,
                di.item_type,
                pi.subject,
                pi.grade,
                pi.qs_total::int          AS questions_total,
                pi.qs_aligned::int        AS questions_with_alignment
            FROM per_item pi
            LEFT JOIN dim_item di USING (item_id)
            ORDER BY pi.qs_aligned, di.item_name
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

    # ────────────────────────────────────────────────────────────────────
    # Year To Date - Longitudinal Report (cross-assessment, school-wide)
    # ────────────────────────────────────────────────────────────────────
    async def get_ytd_school_meta(
        self,
        session_filter: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        category: Optional[str] = None,
        section: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        # School meta + course/unit + assessment-type list for legacy PBIX
        # multiRowCard chrome (H2 Course+Unit, H2 Assessment Type).
        sql = text(
            f"""
            WITH scoped AS (
                SELECT DISTINCT cus.school_id, cus.item_id, cus.subject,
                                cus.grade, cus.session, cus.assessment_type,
                                cus.item_name
                FROM cube_user_summary cus
                WHERE {_CUS_YTD_FILTER_SQL}
            )
            SELECT
                COALESCE(s.name, '')                          AS name,
                COALESCE(s.logo_url, '')                      AS logo_url,
                COALESCE(
                    (SELECT MAX(session) FROM scoped),
                    ''
                )                                              AS current_session,
                COALESCE(
                    (SELECT string_agg(label, ' | ' ORDER BY label)
                     FROM (
                       SELECT DISTINCT NULLIF(
                           trim(both ' / ' from
                             concat_ws(' / ',
                               NULLIF(subject, ''),
                               NULLIF(grade, '')
                             )
                           ),
                           ''
                       ) AS label
                       FROM scoped
                     ) cu
                     WHERE cu.label IS NOT NULL
                    ),
                    ''
                )                                              AS course_unit,
                COALESCE(
                    (SELECT array_agg(at.assessment_type ORDER BY at.assessment_type)
                     FROM (
                       SELECT DISTINCT assessment_type
                       FROM scoped
                       WHERE assessment_type IS NOT NULL
                         AND assessment_type <> ''
                     ) at
                    ),
                    ARRAY[]::text[]
                )                                              AS assessment_types,
                (SELECT MIN(di.assessment_date)
                   FROM dim_item di
                   JOIN scoped sc ON sc.school_id = di.school_id AND sc.item_id = di.item_id
                )                                              AS date_from,
                (SELECT MAX(di.assessment_date)
                   FROM dim_item di
                   JOIN scoped sc ON sc.school_id = di.school_id AND sc.item_id = di.item_id
                )                                              AS date_to,
                (SELECT COUNT(DISTINCT item_id) FROM scoped)    AS total_assessments
            FROM public.schools s
            LIMIT 1
            """
        )
        result = await self.session.execute(
            sql,
            _school_filter_params(
                session_filter, subject, grade, category, section
            ),
        )
        row = result.first()
        return _row_to_dict(row) if row else None

    async def get_ytd_overall_kpis(
        self,
        session_filter: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        category: Optional[str] = None,
        section: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        # Legacy "Key Measures" card (PBIX multiRowCard, _layout.full.json ord 8):
        #   Total Questions  = DISTINCTCOUNT(question)        — over cqso
        #   Total Students   = DISTINCTCOUNT(user_uid)        — over cube_user_summary
        #   Score            = SUM(total_score)                — over cube_user_summary
        #   Points Possible  = SUM(total_possible_point)       — over cube_user_summary
        #   % Correct        = AVG(grade_average)              — over cqso
        #                      (DAX: AVERAGE('cqso'[Grade_Average]))
        sql = text(
            f"""
            WITH cus_scoped AS (
                SELECT cus.user_uid, cus.item_id,
                       cus.total_score, cus.total_possible_point
                FROM cube_user_summary cus
                WHERE {_CUS_YTD_FILTER_SQL}
            ),
            cqso_scoped AS (
                SELECT cqso.ukey, cqso.grade_average
                FROM cube_question_summary_overall cqso
                LEFT JOIN dim_subject dsubj
                  ON dsubj.school_id = cqso.school_id
                 AND dsubj.subject_id = cqso.subject_id
                WHERE {_CQSO_YTD_FILTER_SQL}
            )
            SELECT
                (SELECT COUNT(DISTINCT ukey) FROM cqso_scoped)              AS total_questions,
                (SELECT COUNT(DISTINCT user_uid) FROM cus_scoped)            AS total_students,
                (SELECT COALESCE(SUM(total_score), 0) FROM cus_scoped)       AS total_points_earned,
                (SELECT COALESCE(SUM(total_possible_point), 0) FROM cus_scoped)
                                                                              AS total_points_possible,
                (SELECT COALESCE(AVG(grade_average), 0) FROM cqso_scoped)   AS overall_avg,
                (SELECT COUNT(DISTINCT item_id) FROM cus_scoped)             AS total_assessments
            """
        )
        result = await self.session.execute(
            sql,
            _school_filter_params(
                session_filter, subject, grade, category, section
            ),
        )
        row = result.first()
        return _row_to_dict(row) if row else None

    async def get_ytd_timeline(
        self,
        session_filter: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        category: Optional[str] = None,
        section: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        sql = text(
            f"""
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
                  AND {_CUS_YTD_FILTER_SQL}
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
                  AND {_CUS_YTD_FILTER_SQL}
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
        result = await self.session.execute(
            sql,
            _school_filter_params(
                session_filter, subject, grade, category, section
            ),
        )
        return [_row_to_dict(r) for r in result.all()]

    async def get_ytd_grade_distribution(
        self,
        session_filter: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        category: Optional[str] = None,
        section: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        sql = text(
            f"""
            WITH user_item AS (
                SELECT
                    cus.user_uid,
                    cus.item_id,
                    SUM(cus.total_score)            AS s,
                    SUM(cus.total_possible_point)   AS p
                FROM cube_user_summary cus
                WHERE {_CUS_YTD_FILTER_SQL}
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
        result = await self.session.execute(
            sql,
            _school_filter_params(
                session_filter, subject, grade, category, section
            ),
        )
        return [_row_to_dict(r) for r in result.all()]

    async def get_ytd_student_progression(
        self,
        session_filter: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        category: Optional[str] = None,
        section: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        sql = text(
            f"""
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
                  AND {_CUS_YTD_FILTER_SQL}
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
        result = await self.session.execute(
            sql,
            _school_filter_params(
                session_filter, subject, grade, category, section
            ),
        )
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # Incorrect Answer Details (drill-through from QRA, single question)
    # ────────────────────────────────────────────────────────────────────
    async def get_question_overall(
        self, item_id: str, question_id: str
    ) -> Optional[Dict[str, Any]]:
        """One question's overall metadata (joined to qso for description).

        Same dedup pattern as :meth:`get_questions_overall_for_item` to avoid
        the qs × qso cartesian product when a question has multiple
        sub-question rows or qso has multiple per-section rows.

        Standards: ``STRING_AGG`` over ``dim_question_data`` so every alias
        the parser emitted reaches the frontend. Description follows the
        legacy ``CombineDescriptionsColumn`` DAX: alphabetical-first non-
        "Other" standard, then look up its row in ``dim_standard``.
        """
        sql = text(
            """
            WITH qs_pick AS (
                SELECT school_id, item_id, question_id, ukey, position_number,
                       question_type, standard
                FROM cube_question_summary
                WHERE item_id = :item_id AND question_id = :question_id
                ORDER BY NULLIF(regexp_replace(COALESCE(position_number, ''), '[^0-9]', '', 'g'), '')::int NULLS LAST,
                         position_number
                LIMIT 1
            ),
            qs_agg AS (
                SELECT item_id, question_id,
                       MAX(question)                                  AS question,
                       MAX(correct_answer)                            AS correct_answer,
                       AVG(grade_average)                             AS grade_average,
                       SUM(total_possible_point)                      AS total_possible_point,
                       SUM(total_score)                               AS total_score,
                       MIN(NULLIF(question_no, ''))                   AS question_no
                FROM cube_question_summary
                WHERE item_id = :item_id AND question_id = :question_id
                GROUP BY item_id, question_id
            ),
            qd_standards AS (
                SELECT
                    item_id,
                    question_id,
                    STRING_AGG(DISTINCT standard, E'\n' ORDER BY standard) AS standards
                FROM dim_question_data
                WHERE item_id = :item_id
                  AND question_id = :question_id
                  AND standard IS NOT NULL AND standard <> ''
                GROUP BY item_id, question_id
            ),
            qd_first_standard AS (
                SELECT
                    item_id,
                    question_id,
                    MIN(standard) FILTER (
                        WHERE standard IS NOT NULL
                          AND standard <> ''
                          AND LOWER(standard) <> 'other'
                    ) AS first_standard
                FROM dim_question_data
                WHERE item_id = :item_id
                  AND question_id = :question_id
                GROUP BY item_id, question_id
            ),
            qd_description AS (
                SELECT
                    qfs.item_id,
                    qfs.question_id,
                    MAX(ds.description) AS description
                FROM qd_first_standard qfs
                LEFT JOIN dim_standard ds
                  ON ds.schoology_standard = qfs.first_standard
                GROUP BY qfs.item_id, qfs.question_id
            ),
            qso_pick AS (
                SELECT DISTINCT ON (school_id, ukey)
                       school_id, ukey, question_no, question, correct_answer
                FROM cube_question_summary_overall
                ORDER BY school_id, ukey
            ),
            qso_num AS (
                SELECT school_id, ukey,
                       AVG(grade_average)        AS grade_average,
                       SUM(total_possible_point) AS total_possible_point,
                       SUM(total_score)          AS total_score
                FROM cube_question_summary_overall
                GROUP BY school_id, ukey
            )
            SELECT
                qsp.question_id,
                COALESCE(qso.question_no, qsa.question_no)                  AS question_no,
                COALESCE(qsp.position_number, '')                           AS position_number,
                COALESCE(qso.question, qsa.question)                        AS question,
                COALESCE(qsp.question_type, '')                             AS question_type,
                COALESCE(qso.correct_answer, qsa.correct_answer)            AS correct_answer,
                COALESCE(qsa.total_possible_point, qson.total_possible_point) AS total_possible_point,
                COALESCE(qsa.total_score, qson.total_score)                 AS total_score,
                COALESCE(qsa.grade_average, qson.grade_average)             AS grade_average,
                COALESCE(qdst.standards, '')                                AS standards,
                COALESCE(qsp.standard, '')                                  AS strand_raw,
                COALESCE(qdd.description, '')                               AS description
            FROM qs_pick qsp
            JOIN qs_agg qsa
              ON qsa.item_id = qsp.item_id AND qsa.question_id = qsp.question_id
            LEFT JOIN qd_standards qdst
              ON qdst.item_id = qsp.item_id AND qdst.question_id = qsp.question_id
            LEFT JOIN qd_description qdd
              ON qdd.item_id  = qsp.item_id AND qdd.question_id  = qsp.question_id
            LEFT JOIN qso_pick qso
              ON qso.school_id = qsp.school_id AND qso.ukey = qsp.ukey
            LEFT JOIN qso_num qson
              ON qson.school_id = qsp.school_id AND qson.ukey = qsp.ukey
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

        ``answer_submission`` arrives prefixed with a randomised option
        letter ("a. ", "b. ", …) — Schoology shuffles option positions per
        student, so the same logical answer can appear under 4 different
        letters. The cube preserves the raw string for legacy parity (per
        notebook lines 1772-1798), so we strip the prefix and re-aggregate
        here at the read layer — same precedent as
        ``get_canonical_kpis_for_item`` which collapses the
        (user, question, position_number) alias fan-out before averaging.
        """
        sql = text(
            r"""
            WITH item_qids AS (
                SELECT DISTINCT question_id
                FROM cube_question_summary
                WHERE item_id = :item_id
                  AND question_id = :question_id
            ),
            choices AS (
                SELECT
                    regexp_replace(qic.answer_submission, '^\s*[a-zA-Z]\.\s+', '')
                                                          AS answer_submission,
                    SUM(qic.total_student)                AS students_count,
                    SUM(qic.total_score)                  AS total_score,
                    SUM(qic.total_possible_point)         AS total_possible_point
                FROM cube_questionincorrectchoice_summary qic
                JOIN item_qids iq ON iq.question_id = qic.question_id
                WHERE qic.answer_submission IS NOT NULL
                  AND qic.answer_submission <> ''
                GROUP BY regexp_replace(qic.answer_submission, '^\s*[a-zA-Z]\.\s+', '')
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
        """Every student × this question row for the IAD per-student table.

        `fact_student_submission` is keyed at `(user, question, standard)`
        grain, so every question with N Schoology standards produces N rows
        per (student, submission). All N rows in a cluster share identical
        points_received / points_possible / answer_submission — only the
        standard column differs. We collapse with DISTINCT ON to restore
        one row per (user, submission) for display.

        ``answer_submission`` / ``correct_answer`` arrive prefixed with the
        random option-letter ("b. …") that Schoology shuffled for this
        student. The letter is per-submission metadata, not part of the
        answer's identity, so we strip it for display — same handling as
        :meth:`get_distractor_breakdown`.
        """
        sql = text(
            r"""
            SELECT
                user_uid,
                user_name,
                answer_submission,
                correct_answer,
                points_received,
                points_possible,
                score_pct,
                is_correct,
                latest_attempt
            FROM (
                SELECT DISTINCT ON (fss.user_uid, fss.submission)
                    COALESCE(fss.user_uid, '')                       AS user_uid,
                    COALESCE(NULLIF(fss.user_name, ''), '—')         AS user_name,
                    regexp_replace(
                        COALESCE(fss.answer_submission, ''),
                        '^\s*[a-zA-Z]\.\s+', ''
                    )                                                AS answer_submission,
                    regexp_replace(
                        COALESCE(fss.correct_answer, ''),
                        '^\s*[a-zA-Z]\.\s+', ''
                    )                                                AS correct_answer,
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
                ORDER BY fss.user_uid, fss.submission
            ) deduped
            ORDER BY user_name
            """
        )
        result = await self.session.execute(
            sql, {"item_id": item_id, "question_id": question_id}
        )
        return [_row_to_dict(r) for r in result.all()]

    async def get_ytd_strand_heatmap(
        self,
        session_filter: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        category: Optional[str] = None,
        section: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # cube_standard_summary is at (school_id, item_id, strand_id, …) grain;
        # we scope through dim_item → dim_subject for the 4 dim-subject filters
        # and dim_section for section.
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
            LEFT JOIN dim_subject dsubj
              ON dsubj.school_id = di.school_id
             AND dsubj.subject_id = di.subject_id
            JOIN dim_strand ds
              ON ds.strand_id = cs.strand_id
             AND ds.identifier = cs.identifier
            WHERE ds.strand IS NOT NULL
              AND di.assessment_date IS NOT NULL
              AND (CAST(:session_filter AS TEXT) IS NULL OR dsubj.session = CAST(:session_filter AS TEXT))
              AND (CAST(:subject AS TEXT) IS NULL OR dsubj.subject = CAST(:subject AS TEXT))
              AND (CAST(:grade AS TEXT) IS NULL OR dsubj.grade = CAST(:grade AS TEXT))
              AND (CAST(:category AS TEXT) IS NULL OR dsubj.assessment_type = CAST(:category AS TEXT))
              AND (
                    CAST(:section AS TEXT) IS NULL
                 OR EXISTS (
                      SELECT 1 FROM dim_section dsec
                      WHERE dsec.school_id = di.school_id
                        AND dsec.item_id = di.item_id
                        AND (
                          dsec.section_name = CAST(:section AS TEXT)
                       OR dsec.section_code = CAST(:section AS TEXT)
                       OR dsec.section_nid  = CAST(:section AS TEXT)
                        )
                    )
                  )
            GROUP BY ds.strand, di.assessment_date
            ORDER BY ds.strand, di.assessment_date
            """
        )
        result = await self.session.execute(
            sql,
            _school_filter_params(
                session_filter, subject, grade, category, section
            ),
        )
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # Paginated reports (PBIX ord 6/7/16, 11, 12, 13)
    # ────────────────────────────────────────────────────────────────────
    async def get_question_summary_matrix_rows(
        self, item_id: str
    ) -> List[Dict[str, Any]]:
        """One row per (student, question) for the QSR matrix.

        Joins ``fact_student_submission`` to ``cube_question_summary`` for
        canonical question metadata and to ``dim_standard`` for the CPALMS
        long-form alias used as the column-group header. All dim joins
        include the ``school_id`` predicate as defense-in-depth even though
        RLS is enabled on every tenant-scoped table.
        """
        sql = text(
            """
            WITH per_question AS (
                SELECT DISTINCT ON (qs.question_id)
                    qs.school_id,
                    qs.question_id,
                    qs.question_no,
                    qs.position_number,
                    qs.correct_answer,
                    qs.standards,
                    qs.standard
                FROM cube_question_summary qs
                WHERE qs.item_id = :item_id
                ORDER BY qs.question_id,
                         NULLIF(regexp_replace(COALESCE(qs.question_no, ''), '[^0-9]', '', 'g'), '')::int NULLS LAST
            ),
            -- Per-(user, question) latest attempt, so re-takes don't double-count.
            -- fss.submission is UUID v7 (time-ordered) per CLAUDE.md.
            per_attempt AS (
                SELECT DISTINCT ON (fss.user_uid, fss.question_id)
                    fss.school_id,
                    fss.user_uid,
                    fss.user_name,
                    fss.section_nid,
                    fss.question_id,
                    fss.points_received,
                    fss.points_possible
                FROM fact_student_submission fss
                WHERE fss.item_id = :item_id
                ORDER BY fss.user_uid, fss.question_id,
                         fss.submission DESC NULLS LAST,
                         fss.latest_attempt DESC NULLS LAST
            )
            SELECT
                pa.user_uid,
                pa.user_name,
                COALESCE(NULLIF(dsec.section_instructors, ''), 'Unassigned')
                                                            AS section_instructors,
                pa.question_id,
                pa.points_received,
                pa.points_possible,
                pq.question_no,
                NULLIF(regexp_replace(COALESCE(pq.question_no, ''), '[^0-9]', '', 'g'), '')::int
                                                            AS sorting_question_no,
                pq.position_number,
                pq.correct_answer,
                pq.standards,
                pq.standard                                  AS schoology_standard,
                ds.cpalms_standard
            FROM per_attempt pa
            JOIN per_question pq ON pq.question_id = pa.question_id
            LEFT JOIN dim_section dsec
              ON dsec.section_nid = pa.section_nid
             AND dsec.school_id = pa.school_id
            -- dim_standard is global (no school_id) — RLS not applicable.
            LEFT JOIN dim_standard ds
              ON ds.schoology_standard = pq.standard
            ORDER BY section_instructors, pa.user_name,
                     NULLIF(regexp_replace(COALESCE(pq.question_no, ''), '[^0-9]', '', 'g'), '')::int NULLS LAST,
                     pq.question_no
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        return [_row_to_dict(r) for r in result.all()]

    async def get_qra_by_teacher_rows(
        self, item_id: str
    ) -> List[Dict[str, Any]]:
        """Per-(section_instructor × question) grain for ord 12.

        Collapses ``cube_question_summary``'s standards-alias fan-out with
        ``DISTINCT ON`` so ``grade_average`` is the cube row's value, not an
        AVG across alias copies. Standards list (multiple Schoology codes
        per question) is aggregated from ``dim_question_data`` — mirrors the
        canonical ``get_questions_overall_for_item`` semantics.
        """
        sql = text(
            """
            WITH qs AS (
                SELECT DISTINCT ON (item_id, section_instructors, question_id)
                    item_id, school_id, section_instructors, question_id,
                    question_no,
                    NULLIF(regexp_replace(COALESCE(question_no, ''), '[^0-9]', '', 'g'), '')::int
                                                              AS sorting_question_no,
                    position_number, question, correct_answer, standard,
                    grade_average,
                    NULLIF(incorrect_choice_details, '') AS incorrect_choice_details,
                    NULLIF(incorrect_details_name, '')   AS incorrect_details_name
                FROM cube_question_summary
                WHERE item_id = :item_id
                ORDER BY item_id, section_instructors, question_id,
                         NULLIF(regexp_replace(COALESCE(position_number, ''), '[^0-9]', '', 'g'), '')::int NULLS LAST,
                         position_number
            ),
            qd_standards AS (
                SELECT
                    school_id,
                    item_id,
                    question_id,
                    STRING_AGG(DISTINCT standard, E'\n' ORDER BY standard) AS standards
                FROM dim_question_data
                WHERE item_id = :item_id
                  AND standard IS NOT NULL AND standard <> ''
                GROUP BY school_id, item_id, question_id
            )
            SELECT
                qs.section_instructors,
                qs.question_id,
                qs.question_no,
                qs.sorting_question_no,
                qs.position_number,
                qs.question,
                qs.correct_answer,
                qs.standard,
                COALESCE(qds.standards, qs.standard) AS standards,
                qs.grade_average,
                qs.incorrect_choice_details,
                qs.incorrect_details_name
            FROM qs
            LEFT JOIN qd_standards qds
              ON qds.item_id = qs.item_id
             AND qds.question_id = qs.question_id
             AND qds.school_id = qs.school_id
            ORDER BY qs.section_instructors,
                     qs.grade_average ASC NULLS LAST,
                     qs.sorting_question_no NULLS LAST, qs.question_no
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        return [_row_to_dict(r) for r in result.all()]

    async def get_qra_by_standard_teacher_rows(
        self, item_id: str
    ) -> List[Dict[str, Any]]:
        """Per-(cpalms_standard × section_instructor × question) grain for ord 13.

        Adds two window-aggregates: ``standard_avg`` across teachers within a
        standard, and ``teacher_standard_avg`` for one teacher within a
        standard. Standards labels come from ``dim_standard.cpalms_standard``;
        per-question ``grade_average`` collapses standards-alias fan-out via
        ``DISTINCT ON``.
        """
        sql = text(
            """
            WITH base AS (
                SELECT DISTINCT ON (item_id, section_instructors, question_id)
                    item_id, school_id, section_instructors, question_id,
                    question_no,
                    NULLIF(regexp_replace(COALESCE(question_no, ''), '[^0-9]', '', 'g'), '')::int
                                                              AS sorting_question_no,
                    position_number, question, correct_answer,
                    standard,
                    grade_average,
                    NULLIF(incorrect_choice_details, '') AS incorrect_choice_details,
                    NULLIF(incorrect_details_name, '')   AS incorrect_details_name
                FROM cube_question_summary
                WHERE item_id = :item_id
                ORDER BY item_id, section_instructors, question_id,
                         NULLIF(regexp_replace(COALESCE(position_number, ''), '[^0-9]', '', 'g'), '')::int NULLS LAST,
                         position_number
            ),
            qd_standards AS (
                SELECT
                    school_id,
                    item_id,
                    question_id,
                    STRING_AGG(DISTINCT standard, E'\n' ORDER BY standard) AS standards
                FROM dim_question_data
                WHERE item_id = :item_id
                  AND standard IS NOT NULL AND standard <> ''
                GROUP BY school_id, item_id, question_id
            )
            SELECT
                COALESCE(NULLIF(ds.cpalms_standard, ''), b.standard) AS cpalms_standard,
                ds.description                                       AS standard_description,
                b.section_instructors,
                b.question_id,
                b.question_no,
                b.sorting_question_no,
                b.position_number,
                b.question,
                b.correct_answer,
                b.standard,
                COALESCE(qds.standards, b.standard)                  AS standards,
                b.grade_average,
                b.incorrect_choice_details,
                b.incorrect_details_name,
                AVG(b.grade_average) OVER (
                    PARTITION BY COALESCE(NULLIF(ds.cpalms_standard, ''), b.standard),
                                 b.section_instructors
                )                                                     AS teacher_standard_avg,
                AVG(b.grade_average) OVER (
                    PARTITION BY COALESCE(NULLIF(ds.cpalms_standard, ''), b.standard)
                )                                                     AS standard_avg
            FROM base b
            -- dim_standard is global (no school_id) — RLS not applicable.
            LEFT JOIN dim_standard ds
              ON ds.schoology_standard = b.standard
            LEFT JOIN qd_standards qds
              ON qds.item_id = b.item_id
             AND qds.question_id = b.question_id
             AND qds.school_id = b.school_id
            ORDER BY cpalms_standard, b.section_instructors,
                     b.grade_average ASC NULLS LAST,
                     b.sorting_question_no NULLS LAST, b.question_no
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        return [_row_to_dict(r) for r in result.all()]
