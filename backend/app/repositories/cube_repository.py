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

from app.repositories.base_repository import row_to_dict as _row_to_dict


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

# Instructor filter — exact match against ONE comma-split element of the
# (comma-joined) ``dim_item.section_instructors`` list (alias ``di``). Mirrors
# the split in ``dim_repository.list_instructors`` so a selected full name
# matches exactly (no substring over-match). Shared by the By-Assessment and
# By-Strand dashboard grids.
_DI_INSTRUCTOR_FILTER_SQL = """(CAST(:instructor AS TEXT) IS NULL OR EXISTS (
                  SELECT 1 FROM unnest(string_to_array(di.section_instructors, ',')) AS _ins(name)
                  WHERE btrim(_ins.name) = btrim(CAST(:instructor AS TEXT))
              ))"""


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
        self, subject_id: str
    ) -> Optional[Dict[str, Any]]:
        """MERGED canonical KPIs for one assessment (all section copies pooled).

        The merge key is ``subject_id`` (section-agnostic). Fact/per-question
        reads widen to the full section set
        (``item_id IN (SELECT item_id FROM dim_item WHERE subject_id = ...)``)
        so every section's students pool into one assessment; the merged totals
        come from the ``(school_id, subject_id)`` GROUPING-SETS rollup row
        (``item_id IS NULL``) of ``cube_school_summary``. ``Total Students``
        mirrors the legacy DAX ``SUMX(SUMMARIZE(cube_school_summary, Item_ID,
        MAX(Total_Students)))`` — the per-section student counts summed. A
        single-section assessment (one item_id == one subject_id) is
        byte-identical to the pre-merge per-item read.
        """
        sql = text(
            """
            WITH items AS (
                SELECT item_id FROM dim_item WHERE subject_id = :subject_id
            ),
            -- Map each per-section fact question_id to its section-agnostic
            -- question_no (the merged question identity). question_no is the
            -- legacy DISTINCTCOUNT(Question_No) grain and equals the old
            -- single-section question_id count, so a single-section assessment
            -- is unchanged.
            qid_qno AS (
                SELECT DISTINCT question_id, question_no
                FROM cube_question_summary
                WHERE item_id IN (SELECT item_id FROM items)
            ),
            fact_dedup AS (
                SELECT DISTINCT ON (user_uid, question_id, position_number)
                       user_uid, question_id, position_number,
                       points_received, points_possible
                FROM fact_student_submission
                WHERE item_id IN (SELECT item_id FROM items)
                  AND points_possible IS NOT NULL
                  AND points_possible > 0
                ORDER BY user_uid, question_id, position_number, identifier NULLS LAST
            ),
            per_user_q AS (
                SELECT qq.question_no, fd.user_uid,
                       SUM(fd.points_received)::numeric
                         / NULLIF(SUM(fd.points_possible), 0) AS pct
                FROM fact_dedup fd
                JOIN qid_qno qq ON qq.question_id = fd.question_id
                GROUP BY qq.question_no, fd.user_uid
            ),
            per_q AS (
                SELECT question_no, AVG(pct) AS qga
                FROM per_user_q
                GROUP BY question_no
            ),
            -- MERGED school totals. total_possible_point / total_score come
            -- from the (school_id, subject_id) GROUPING-SETS rollup row
            -- (item_id IS NULL) — already SUM(points) across every section.
            -- total_students mirrors legacy SUMX(SUMMARIZE(Item_ID,
            -- MAX(Total_Students))): sum the per-section student counts (MAX
            -- de-dups the multi-subject duplicate rows a single item can carry
            -- — e.g. Brightview 7566518630). A single-section assessment
            -- collapses to the lone per-item value.
            school AS (
                SELECT
                    (
                        SELECT COALESCE(SUM(ts), 0)
                        FROM (
                            SELECT item_id, MAX(total_students) AS ts
                            FROM cube_school_summary
                            WHERE subject_id = :subject_id
                              AND item_id IS NOT NULL
                            GROUP BY item_id
                        ) per_item
                    )                                AS total_students,
                    rollup.total_possible_point,
                    rollup.total_score
                FROM (
                    SELECT total_possible_point, total_score
                    FROM cube_school_summary
                    WHERE subject_id = :subject_id AND item_id IS NULL
                    LIMIT 1
                ) rollup
            ),
            std AS (
                SELECT COUNT(DISTINCT standard) AS total_standards
                FROM dim_question_data
                WHERE item_id IN (SELECT item_id FROM items)
                  AND standard IS NOT NULL
                  AND standard NOT IN ('', 'null')
            ),
            -- Cube fallback for fact-less (parquet-loaded) schools. The fact
            -- table is empty for items loaded directly from stage3 cube
            -- parquet, so the per-(question,user) collapse above yields no
            -- rows. For those assessments derive Total Questions from the
            -- per-question cube (DISTINCTCOUNT(Question_No) across sections)
            -- and the merged grade average from the cube_school_summary
            -- subject rollup; min/max from the per-question merged averages.
            cube_q AS (
                SELECT COUNT(DISTINCT question_no) AS total_questions
                FROM cube_question_summary
                WHERE item_id IN (SELECT item_id FROM items)
            ),
            -- MERGED per-question average (points-weighted across sections):
            -- pool every section's points for a given question_no, then
            -- SUM(score)/SUM(possible). Drives the fact-less min/max.
            cube_perq AS (
                SELECT question_no,
                       SUM(total_score)::numeric
                         / NULLIF(SUM(total_possible_point), 0) AS qga
                FROM cube_question_summary
                WHERE item_id IN (SELECT item_id FROM items)
                GROUP BY question_no
            ),
            cube_ga AS (
                SELECT
                    (
                        SELECT total_score::numeric
                                 / NULLIF(total_possible_point, 0)
                        FROM cube_school_summary
                        WHERE subject_id = :subject_id AND item_id IS NULL
                        LIMIT 1
                    )                  AS grade_average,
                    MAX(qga)           AS grade_max,
                    MIN(qga)           AS grade_min
                FROM cube_perq
            ),
            fact_present AS (
                SELECT EXISTS (SELECT 1 FROM per_q) AS has_fact
            )
            SELECT
                (SELECT total_students FROM school)        AS total_students,
                CASE WHEN (SELECT has_fact FROM fact_present)
                     THEN (SELECT COUNT(*) FROM per_q)
                     ELSE (SELECT total_questions FROM cube_q)
                END                                        AS total_questions,
                (SELECT total_standards FROM std)          AS total_standards,
                CASE WHEN (SELECT has_fact FROM fact_present)
                     THEN (SELECT AVG(qga) FROM per_q)
                     ELSE (SELECT grade_average FROM cube_ga)
                END                                        AS grade_average,
                CASE WHEN (SELECT has_fact FROM fact_present)
                     THEN (SELECT MAX(qga) FROM per_q)
                     ELSE (SELECT grade_max FROM cube_ga)
                END                                        AS grade_max,
                CASE WHEN (SELECT has_fact FROM fact_present)
                     THEN (SELECT MIN(qga) FROM per_q)
                     ELSE (SELECT grade_min FROM cube_ga)
                END                                        AS grade_min,
                (SELECT total_possible_point FROM school)  AS total_possible_point,
                (SELECT total_score FROM school)           AS total_score
            """
        )
        result = await self.session.execute(sql, {"subject_id": subject_id})
        row = result.first()
        return _row_to_dict(row) if row else None

    async def get_assessment_summary_page(
        self,
        session_filter: Optional[str] = None,
        category: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        section: Optional[str] = None,
        instructor: Optional[str] = None,
        q: Optional[str] = None,
        sort_sql: str = "assessment_date",
        dir_sql: str = "DESC",
        # Internal fallback only — the service always passes the route's limit
        # (DEFAULT_SUMMARY_PAGE_SIZE). Kept defaulted to satisfy arg ordering.
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        """ONE page of the dashboard "Assessments Summary — By Assessment" grid,
        plus the full filter-scoped total.

        Server-side pagination (``limit``/``offset``), sort (``sort_sql`` +
        ``dir_sql``) and name search (``q``) so schools with thousands of
        assessments only ever transfer one page. Per-item grade_average is the
        AVG of the item's ``cube_question_summary`` grade_averages, which equals
        the canonical per-(question, user) fact collapse to the digit but reads a
        few indexed cube rows per item instead of re-aggregating the fact table
        every page (≈43s → <1s on a full-year school). ``total`` is
        ``COUNT(*) OVER()`` of the scoped set (pre-LIMIT).

        ``sort_sql``/``dir_sql`` MUST be pre-validated literals from the route's
        whitelist (never raw user input) — they are interpolated, not bound.
        RLS scopes every base table to the caller's school.
        """
        order_by = f"{sort_sql} {dir_sql} NULLS LAST, subject_id ASC"
        sql = text(
            f"""
            -- One row per section copy that passes the filters. The section /
            -- instructor slicers narrow this set (PowerBI cross-filter
            -- semantics): with no slicer every section is included and the
            -- merged numbers span the whole assessment; with a slicer the
            -- merged numbers recompute over the matching sections only.
            WITH scoped_items AS (
                SELECT di.item_id, di.item_name, di.item_type, di.subject_id,
                       ds.subject, ds.grade, ds.session, ds.assessment_type,
                       di.section_name, di.section_instructors, di.assessment_date
                FROM dim_item di
                LEFT JOIN dim_subject ds
                  ON ds.school_id = di.school_id AND ds.subject_id = di.subject_id
                WHERE (CAST(:session_filter AS TEXT) IS NULL OR ds.session = CAST(:session_filter AS TEXT))
                  AND (CAST(:category AS TEXT) IS NULL OR ds.assessment_type = CAST(:category AS TEXT))
                  AND (CAST(:subject AS TEXT)  IS NULL OR ds.subject         = CAST(:subject AS TEXT))
                  AND (CAST(:grade AS TEXT)    IS NULL OR ds.grade           = CAST(:grade AS TEXT))
                  AND (CAST(:section AS TEXT)  IS NULL OR di.section_name    = CAST(:section AS TEXT))
                  AND {_DI_INSTRUCTOR_FILTER_SQL}
                  AND (CAST(:q AS TEXT)        IS NULL OR di.item_name ILIKE '%' || CAST(:q AS TEXT) || '%')
            ),
            -- MERGE: collapse all section copies of an assessment to ONE row,
            -- keyed on subject_id (= uuid_6 of school/subject/type/grade/
            -- session/item_name, section-agnostic; 1:1 with item_name within a
            -- subject). item_name is identical across the copies; sections and
            -- instructors are unioned for display; assessment_date is the
            -- earliest (legacy OrderBy Min(assessment_date)).
            scoped AS (
                SELECT
                    subject_id,
                    MIN(item_name)        AS item_name,
                    MIN(item_type)        AS item_type,
                    MIN(subject)          AS subject,
                    MIN(grade)            AS grade,
                    MIN(session)          AS session,
                    MIN(assessment_type)  AS assessment_type,
                    string_agg(DISTINCT section_name, ', '
                               ORDER BY section_name)        AS section_name,
                    string_agg(DISTINCT section_instructors, ', '
                               ORDER BY section_instructors) AS section_instructors,
                    MIN(assessment_date)  AS assessment_date
                FROM scoped_items
                GROUP BY subject_id
            ),
            -- Merged grade_average per assessment: pool every section's points
            -- per question_no (SUM(score)/SUM(possible)), then AVG over
            -- questions. Equals the canonical per-(question, user) fact collapse
            -- to the digit (points_possible is constant per question across
            -- sections), so the dashboard bar agrees with the report KPI strip.
            item_ga AS (
                SELECT subject_id, AVG(qga) AS grade_average
                FROM (
                    SELECT subject_id, question_no,
                           SUM(total_score)::numeric
                             / NULLIF(SUM(total_possible_point), 0) AS qga
                    FROM cube_question_summary
                    WHERE item_id IN (SELECT item_id FROM scoped_items)
                    GROUP BY subject_id, question_no
                ) per_q
                GROUP BY subject_id
            ),
            -- Merged Total Students = legacy SUMX(SUMMARIZE(Item_ID,
            -- MAX(Total_Students))): per-section student maxes summed across the
            -- assessment's sections. MAX de-dups the multi-subject duplicate
            -- rows one item can carry.
            students AS (
                SELECT subject_id, SUM(ts) AS total_students
                FROM (
                    SELECT subject_id, item_id, MAX(total_students) AS ts
                    FROM cube_school_summary
                    WHERE item_id IN (SELECT item_id FROM scoped_items)
                    GROUP BY subject_id, item_id
                ) per_item
                GROUP BY subject_id
            ),
            enriched AS (
                -- The merged report identity is subject_id; it is surfaced in the
                -- ``item_id`` field so the existing frontend/report plumbing
                -- (links, report endpoints, exports — all keyed on ``item_id``)
                -- carries the section-agnostic key unchanged. One grid row per
                -- assessment (no per-section duplicates).
                SELECT s.subject_id AS item_id,
                       s.subject_id,
                       s.item_name, s.item_type,
                       s.subject, s.grade, s.session, s.assessment_type,
                       s.section_name, s.section_instructors, s.assessment_date,
                       ig.grade_average,
                       st.total_students,
                       COUNT(*) OVER() AS total
                FROM scoped s
                LEFT JOIN item_ga ig ON ig.subject_id = s.subject_id
                LEFT JOIN students st ON st.subject_id = s.subject_id
            )
            SELECT * FROM enriched
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
            """
        )
        result = await self.session.execute(
            sql,
            {
                "session_filter": session_filter,
                "category": category,
                "subject": subject,
                "grade": grade,
                "section": section,
                "instructor": instructor,
                "q": q,
                "limit": limit,
                "offset": offset,
            },
        )
        rows = [_row_to_dict(r) for r in result.all()]
        total = int(rows[0]["total"]) if rows else 0
        for r in rows:
            r.pop("total", None)
        return rows, total

    async def get_canonical_per_question_grades(
        self, subject_id: str
    ) -> List[Dict[str, Any]]:
        """Per-question grade_average using the canonical per-user collapse,
        MERGED across all section copies of the assessment.

        Used to override the per-question grade on the QRA question table
        for multi-select / multi-position questions whose
        ``cube_question_summary.grade_average`` reflects row-grain
        SUM/SUM (e.g. Q12 = 35/146 = 23.97%) rather than per-student
        average (27.78%). This matches the KPI strip's per-question grain
        so the per-question table cannot disagree with the Lowest/Highest
        KPI for the same assessment. Widening the fact filter to the section
        set pools every section's students per question.
        """
        sql = text(
            """
            WITH items AS (
                SELECT item_id FROM dim_item WHERE subject_id = :subject_id
            ),
            -- Map each per-section fact question_id to its section-agnostic
            -- question_no (the merged QRA question identity), so the override
            -- returned here joins the question_no-keyed question rows.
            qid_qno AS (
                SELECT DISTINCT question_id, question_no
                FROM cube_question_summary
                WHERE item_id IN (SELECT item_id FROM items)
            ),
            fact_dedup AS (
                SELECT DISTINCT ON (user_uid, question_id, position_number)
                       user_uid, question_id, position_number,
                       points_received, points_possible
                FROM fact_student_submission
                WHERE item_id IN (SELECT item_id FROM items)
                  AND points_possible IS NOT NULL
                  AND points_possible > 0
                ORDER BY user_uid, question_id, position_number, identifier NULLS LAST
            ),
            per_user_q AS (
                SELECT qq.question_no, fd.user_uid,
                       SUM(fd.points_received)::numeric
                         / NULLIF(SUM(fd.points_possible), 0) AS pct
                FROM fact_dedup fd
                JOIN qid_qno qq ON qq.question_id = fd.question_id
                GROUP BY qq.question_no, fd.user_uid
            )
            SELECT question_no AS question_id, AVG(pct) AS grade_average
            FROM per_user_q
            GROUP BY question_no
            """
        )
        result = await self.session.execute(sql, {"subject_id": subject_id})
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # School-level summary for one assessment (cube_school_summary)
    # ────────────────────────────────────────────────────────────────────
    async def get_school_summary_for_item(self, subject_id: str) -> Optional[Dict[str, Any]]:
        """MERGED school summary: the (school_id, subject_id) GROUPING-SETS
        rollup row (item_id IS NULL) pools points + distinct standards/questions
        across all sections. Total Students mirrors legacy SUMX(SUMMARIZE(
        Item_ID, MAX(Total_Students))) so it agrees with the KPI strip."""
        sql = text(
            """
            SELECT
                :subject_id                  AS subject_id,
                rollup.total_questions,
                rollup.total_standards,
                (
                    SELECT COALESCE(SUM(ts), 0)
                    FROM (
                        SELECT item_id, MAX(total_students) AS ts
                        FROM cube_school_summary
                        WHERE subject_id = :subject_id AND item_id IS NOT NULL
                        GROUP BY item_id
                    ) per_item
                )                            AS total_students,
                rollup.total_possible_point,
                rollup.total_score,
                rollup.grade_average,
                rollup.percentage_incorrect_answers
            FROM cube_school_summary rollup
            WHERE rollup.subject_id = :subject_id AND rollup.item_id IS NULL
            LIMIT 1
            """
        )
        result = await self.session.execute(sql, {"subject_id": subject_id})
        row = result.first()
        return _row_to_dict(row) if row else None

    async def get_grade_summary_for_item(self, subject_id: str) -> Optional[Dict[str, Any]]:
        """MERGED grade summary: the (school_id, subject_id) rollup row of
        cube_grade_summary (item_id IS NULL) — grade min/max/avg across every
        section's students."""
        sql = text(
            """
            SELECT
                :subject_id AS subject_id,
                grade_average,
                percentage_incorrect_answers,
                grade_min,
                grade_max
            FROM cube_grade_summary
            WHERE subject_id = :subject_id AND item_id IS NULL
            LIMIT 1
            """
        )
        result = await self.session.execute(sql, {"subject_id": subject_id})
        row = result.first()
        return _row_to_dict(row) if row else None

    # ────────────────────────────────────────────────────────────────────
    # Question-level summaries (cube_question_summary +
    # cube_question_summary_overall)
    # ────────────────────────────────────────────────────────────────────
    async def get_questions_overall_for_item(self, subject_id: str) -> List[Dict[str, Any]]:
        """One row per question for a MERGED assessment (all section copies pooled).

        Keyed on ``subject_id``. ``cube_question_summary`` (per-item) reads widen
        to the section set (``item_id IN (SELECT … FROM dim_item WHERE
        subject_id)``) and group by ``question_id`` so a question's metadata +
        numerics pool across sections. ``cube_question_summary_overall`` (cqso)
        is already section-agnostic (keyed by ``(school_id, ukey)``; one ukey per
        (assessment, question) regardless of section) and is scoped here by
        ``subject_id``.

        MERGE / R3 reconciliation: under a subject-keyed report the cqso pooled
        distractor % and named-student list across every section IS the legacy
        merged content (not a leak), so it is now PREFERRED over the per-section
        ``cube_question_summary`` list. For a single-section assessment cqso
        pools exactly that one section, so the list is identical to the
        pre-merge per-item read (parity preserved).
        """
        sql = text(
            """
            WITH items AS (
                SELECT item_id FROM dim_item WHERE subject_id = :subject_id
            ),
            -- Per-question_no metadata + text from the per-section cube. The
            -- merged grain is question_no (section-agnostic; equals the legacy
            -- DISTINCTCOUNT(Question_No) and the old single-section question_id
            -- grain). Pick one representative row per question_no.
            qs_meta AS (
                SELECT DISTINCT ON (question_no)
                    question_no, question, question_type, position_number,
                    correct_answer, standard, standards AS cube_standards
                FROM cube_question_summary
                WHERE item_id IN (SELECT item_id FROM items)
                ORDER BY question_no,
                         NULLIF(regexp_replace(COALESCE(position_number, ''), '[^0-9]', '', 'g'), '')::int NULLS LAST,
                         position_number
            ),
            -- Merged per-question_no numerics: pool every section's points
            -- (SUM), grade = SUM(score)/SUM(possible). Overridden downstream by
            -- the canonical per-question grade; kept for total points + fallback.
            qs_num AS (
                SELECT question_no,
                       SUM(total_possible_point) AS total_possible_point,
                       SUM(total_score)          AS total_score,
                       SUM(total_score)::numeric / NULLIF(SUM(total_possible_point), 0) AS grade_average,
                       1 - SUM(total_score)::numeric / NULLIF(SUM(total_possible_point), 0) AS percentage_incorrect
                FROM cube_question_summary
                WHERE item_id IN (SELECT item_id FROM items)
                GROUP BY question_no
            ),
            -- Pooled distractor % + named-student list per question_no from the
            -- section-agnostic base cqso (already pooled across sections). This
            -- IS the legacy merged content; a question_no with several cqso ukey
            -- rows (multi-answer) is concatenated. Reverses the R3 per-section
            -- read; a single-section assessment yields that one section's list.
            cqso_agg AS (
                SELECT question_no,
                       STRING_AGG(NULLIF(incorrect_choice_details, ''), E'\n') AS incorrect_choice_details,
                       STRING_AGG(NULLIF(incorrect_details_name, ''), E'\n')   AS incorrect_details_name,
                       MAX(description)                                        AS description
                FROM cube_question_summary_overall
                WHERE subject_id = :subject_id
                GROUP BY question_no
            ),
            -- question_no -> every per-section question_id, for dim_question_data
            -- (keyed on the per-section question_id) aggregation.
            uk_qids AS (
                SELECT DISTINCT question_no, question_id
                FROM cube_question_summary
                WHERE item_id IN (SELECT item_id FROM items)
            ),
            qd_standards AS (
                SELECT uq.question_no,
                       STRING_AGG(DISTINCT dqd.standard, E'\n' ORDER BY dqd.standard) AS standards
                FROM uk_qids uq
                JOIN dim_question_data dqd ON dqd.question_id = uq.question_id
                WHERE dqd.standard IS NOT NULL AND dqd.standard <> ''
                GROUP BY uq.question_no
            ),
            qd_cpalms AS (
                SELECT uq.question_no,
                       STRING_AGG(DISTINCT ds.cpalms_standard, E'\n'
                                  ORDER BY ds.cpalms_standard) AS cpalms_standard
                FROM uk_qids uq
                JOIN dim_question_data dqd ON dqd.question_id = uq.question_id
                JOIN dim_standard ds ON ds.schoology_standard = dqd.standard
                WHERE dqd.standard IS NOT NULL AND dqd.standard <> ''
                  AND dqd.standard NOT LIKE 'AI.%'
                  AND ds.cpalms_standard IS NOT NULL AND ds.cpalms_standard <> ''
                GROUP BY uq.question_no
            ),
            qd_first_standard AS (
                SELECT uq.question_no,
                       MIN(dqd.standard) FILTER (
                           WHERE dqd.standard IS NOT NULL
                             AND dqd.standard <> ''
                             AND LOWER(dqd.standard) <> 'other'
                       ) AS first_standard
                FROM uk_qids uq
                JOIN dim_question_data dqd ON dqd.question_id = uq.question_id
                GROUP BY uq.question_no
            ),
            qd_description AS (
                SELECT qfs.question_no, MAX(ds.description) AS description
                FROM qd_first_standard qfs
                LEFT JOIN dim_standard ds
                  ON ds.schoology_standard = qfs.first_standard
                GROUP BY qfs.question_no
            )
            SELECT
                qm.question_no                                                  AS question_id,
                qm.question_no                                                  AS question_no,
                qm.position_number                                             AS position_number,
                qm.question                                                     AS question,
                qm.question_type                                                AS question_type,
                qm.correct_answer                                               AS correct_answer,
                qn.total_possible_point                                         AS total_possible_point,
                qn.total_score                                                  AS total_score,
                qn.grade_average                                                AS grade_average,
                qn.percentage_incorrect                                         AS percentage_incorrect,
                COALESCE(ca.incorrect_choice_details, '')                       AS incorrect_choice_details,
                COALESCE(ca.incorrect_details_name, '')                         AS incorrect_details_name,
                COALESCE(NULLIF(qdst.standards, ''), NULLIF(qm.cube_standards, ''), '') AS standards,
                COALESCE(qdc.cpalms_standard, '')                              AS cpalms_standard,
                qm.standard                                                     AS strand_raw,
                COALESCE(qdd.description, ca.description, '')                   AS description
            FROM qs_meta qm
            LEFT JOIN qs_num         qn   ON qn.question_no   = qm.question_no
            LEFT JOIN cqso_agg       ca   ON ca.question_no   = qm.question_no
            LEFT JOIN qd_standards   qdst ON qdst.question_no = qm.question_no
            LEFT JOIN qd_cpalms      qdc  ON qdc.question_no  = qm.question_no
            LEFT JOIN qd_description qdd  ON qdd.question_no  = qm.question_no
            ORDER BY NULLIF(regexp_replace(qm.question_no, '[^0-9]', '', 'g'), '')::int NULLS LAST,
                     qm.question_no
            """
        )
        result = await self.session.execute(sql, {"subject_id": subject_id})
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # Incorrect-choice detail (cube_questionincorrectchoice_summary)
    # ────────────────────────────────────────────────────────────────────
    async def get_incorrect_choices_for_item(self, subject_id: str) -> List[Dict[str, Any]]:
        """MERGED per-(question, answer-choice) rollup for an assessment.

        Keyed on ``question_no`` — the section-agnostic merged question identity
        (the per-section ``question_id`` differs across section copies). The
        choice rows are pooled across every section that answered the question
        and returned under ``question_id = question_no`` so the merged QRA
        question identity is consistent everywhere.
        """
        sql = text(
            """
            WITH qid_qno AS (
                SELECT DISTINCT question_id, question_no
                FROM cube_question_summary
                WHERE item_id IN (
                          SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                      )
            ),
            choices AS (
                -- Pool the per-section detail rows by (question_no, answer).
                -- Exclude the GROUPING SETS rollup rows (NULL answer_submission).
                SELECT
                    qq.question_no,
                    qic.answer_submission,
                    SUM(qic.total_student)        AS students_count,
                    SUM(qic.total_score)          AS total_score,
                    SUM(qic.total_possible_point) AS total_possible_point
                FROM cube_questionincorrectchoice_summary qic
                JOIN qid_qno qq ON qq.question_id = qic.question_id
                WHERE qic.answer_submission IS NOT NULL
                  AND qic.answer_submission <> ''
                GROUP BY qq.question_no, qic.answer_submission
            ),
            attempts AS (
                SELECT question_no, SUM(students_count) AS total_attempts
                FROM choices GROUP BY question_no
            )
            SELECT
                c.question_no                                    AS question_id,
                c.answer_submission,
                c.students_count                                 AS students_count,
                c.students_count                                 AS attempt_count_for_choice,
                COALESCE(a.total_attempts, 0)                    AS total_attempts_for_question,
                CASE WHEN COALESCE(a.total_attempts,0) > 0
                     THEN c.students_count::numeric / a.total_attempts::numeric
                     ELSE 0 END                                  AS share_of_attempts,
                c.total_score,
                c.total_possible_point,
                CASE WHEN c.total_possible_point > 0
                     THEN c.total_score::numeric / NULLIF(c.total_possible_point, 0)
                     ELSE 0 END                                  AS grade_average,
                CASE WHEN c.total_possible_point > 0
                     THEN 1 - c.total_score::numeric / NULLIF(c.total_possible_point, 0)
                     ELSE 0 END                                  AS percentage_incorrect_answers,
                CASE WHEN c.total_possible_point > 0
                     AND c.total_score >= c.total_possible_point
                     THEN TRUE ELSE FALSE END                    AS is_correct
            FROM choices c
            LEFT JOIN attempts a ON a.question_no = c.question_no
            ORDER BY c.question_no, c.students_count DESC NULLS LAST
            """
        )
        result = await self.session.execute(sql, {"subject_id": subject_id})
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # Standards (cube_standard_summary joined with dim_standard)
    # ────────────────────────────────────────────────────────────────────
    async def get_standards_for_item(self, subject_id: str) -> List[Dict[str, Any]]:
        """MERGED per-(strand, identifier) rollup for an assessment.

        ``cube_standard_summary`` is per-(item, strand, identifier) and carries
        no subject_id, so re-aggregate over the assessment's section set: SUM
        the points (grade_average = SUM(score)/SUM(possible)), and take the
        per-question/standard counts via MAX (identical content across
        sections, so MAX avoids double-counting)."""
        sql = text(
            """
            WITH agg AS (
                SELECT
                    cs.strand_id,
                    cs.identifier,
                    MAX(cs.total_questions)        AS total_questions,
                    MAX(cs.total_standards)        AS total_standards,
                    SUM(cs.total_possible_point)   AS total_possible_point,
                    SUM(cs.total_score)            AS total_score,
                    SUM(cs.total_score)::numeric
                      / NULLIF(SUM(cs.total_possible_point), 0)  AS grade_average,
                    1 - SUM(cs.total_score)::numeric
                      / NULLIF(SUM(cs.total_possible_point), 0)  AS percentage_incorrect_answers
                FROM cube_standard_summary cs
                WHERE cs.item_id IN (
                          SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                      )
                GROUP BY cs.strand_id, cs.identifier
            )
            SELECT
                :subject_id                     AS item_id,
                a.strand_id,
                a.identifier,
                a.total_questions,
                a.total_standards,
                a.total_possible_point,
                a.total_score,
                a.grade_average,
                a.percentage_incorrect_answers,
                ds_strand.strand                AS strand,
                ds_std.schoology_standard       AS schoology_standard,
                ds_std.description              AS description
            FROM agg a
            LEFT JOIN dim_strand ds_strand
              ON ds_strand.strand_id = a.strand_id
             AND ds_strand.identifier = a.identifier
            LEFT JOIN LATERAL (
                SELECT description, schoology_standard
                FROM dim_standard
                WHERE identifier = a.identifier
                LIMIT 1
            ) ds_std ON TRUE
            ORDER BY ds_strand.strand NULLS LAST, a.identifier
            """
        )
        result = await self.session.execute(sql, {"subject_id": subject_id})
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # Per-assessment strand / standard rollups (Standards Deep Dive interactive page
    # AND the QRA Strands/Standards summary tables).
    # ────────────────────────────────────────────────────────────────────
    async def get_strand_rollup_for_item(
        self, subject_id: str
    ) -> List[Dict[str, Any]]:
        """One row per Strand for a given MERGED assessment.

        ``num_standards`` is counted at the **schoology_standard grain** —
        the Schoology canonical long form rendered by
        ``get_standard_rollup_for_item``. Each unique Schoology code per
        strand contributes one entry. ``num_questions`` =
        ``COUNT(DISTINCT question_no)`` over the matched identifiers in
        ``cube_question_summary``.

        ``grade_average`` reproduces legacy DAX
        ``Grade_Average_Strand_Measure = AVERAGE('cube_question_summary_overall'[Grade_Average])``
        filtered to the strand (``04_dax_measures.csv:142-146``). It is
        therefore sourced from ``cube_question_summary_overall`` — one row
        per ``(question_no, position_number, correct_answer, standards)`` —
        **not** from ``cube_question_summary`` (per-identifier, per-position),
        whose ``AVG(grade_average)`` diverged from PBIX (audit
        ``06_cubes_and_reports.md`` §D4). The cqso bridge maps
        ``cqso.standards`` (the Schoology canonical code) to the strand via
        ``dim_standard.schoology_standard``. Alias strands carrying no cqso
        rows resolve to NULL (rendered BLANK) — matching legacy where the
        DAX measure returns BLANK for an unassessed standard.

        Restricts identifiers via an exact-match join on the item's
        ``dim_question_data.standard`` set so unaligned assessments yield
        zero strand rows.
        """
        sql = text(
            """
            WITH items AS (
                SELECT item_id FROM dim_item WHERE subject_id = :subject_id
            ),
            item_codes AS (
                SELECT DISTINCT standard AS code
                FROM dim_question_data
                WHERE item_id IN (SELECT item_id FROM items)
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
            strand_questions AS (
                SELECT
                    ds.strand                              AS strand,
                    COUNT(DISTINCT cqs.question_no)        AS num_questions
                FROM cube_question_summary cqs
                JOIN dim_standard ds
                  ON ds.identifier = cqs.identifier
                JOIN labeled l
                  ON l.identifier = cqs.identifier
                WHERE cqs.item_id IN (SELECT item_id FROM items)
                  AND ds.strand IS NOT NULL
                  AND ds.strand <> ''
                GROUP BY ds.strand
            ),
            strand_grade AS (
                -- MERGED strand grade: AVG(grade_average) over the section-agnostic
                -- base cube_question_summary_overall (one row per ukey, already
                -- pooled across every section of the assessment) scoped by
                -- subject_id. This reverses the R3 per-item twin read: under a
                -- subject-keyed report the pooled cqso IS the desired merged
                -- content, and for a single-section assessment it equals the twin.
                SELECT
                    ds.strand               AS strand,
                    AVG(cqso.grade_average) AS grade_average
                FROM cube_question_summary_overall cqso
                JOIN dim_standard ds
                  ON ds.schoology_standard = cqso.standards
                WHERE cqso.subject_id = :subject_id
                  AND ds.strand IS NOT NULL AND ds.strand <> ''
                GROUP BY ds.strand
            )
            SELECT
                sq.strand                       AS strand,
                ss.num_standards                AS num_standards,
                sq.num_questions                AS num_questions,
                -- NULL (not 0) when the strand's standards carry no cqso
                -- rows: legacy renders an unassessed strand BLANK, not
                -- 0.0% (MASTER_PLAN §6, Decision 3).
                sg.grade_average                AS grade_average
            FROM strand_questions sq
            JOIN strand_standards ss ON ss.strand = sq.strand
            LEFT JOIN strand_grade sg ON sg.strand = sq.strand
            ORDER BY sq.strand
            """
        )
        result = await self.session.execute(sql, {"subject_id": subject_id})
        return [_row_to_dict(r) for r in result.all()]

    async def get_strand_rows_page(
        self,
        session_filter: Optional[str] = None,
        category: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        instructor: Optional[str] = None,
        q: Optional[str] = None,
        sort_sql: str = "assessment_date",
        dir_sql: str = "DESC",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        """One page of the dashboard "Performance by Strand" grid at the legacy
        per-(assessment × strand) grain, plus the full filter-scoped total.

        Generalizes :meth:`get_strand_rollup_for_item` across every assessment in
        the filter scope — identical column semantics so the dashboard cannot
        disagree with the SDD/QRA strand tables or legacy PowerBI:

        * ``total_standards`` = COUNT(DISTINCT schoology_standard) per strand,
          from ``dim_standard`` matched to the item's aligned ``dim_question_data``
          codes.
        * ``total_questions`` = COUNT(DISTINCT question_no) per strand, from
          ``cube_question_summary``.
        * ``grade_average`` = AVG(grade_average) over
          ``cube_question_summary_overall_by_item`` per strand — the section-aware
          per-item twin (legacy DAX ``Grade_Average_Strand_Measure``). NULL (BLANK)
          when the strand carries no cqso rows, exactly like legacy.

        Server-paginated (``limit``/``offset``) + sorted. ``sort_sql``/``dir_sql``
        MUST be pre-validated literals from the service whitelist (interpolated,
        not bound). RLS scopes every base table to the caller's school.
        """
        order_by = f"{sort_sql} {dir_sql} NULLS LAST, item_id ASC, strand ASC"
        sql = text(
            f"""
            -- MERGED "Performance by Strand" grid: one row per
            -- (assessment, strand) keyed on subject_id, pooling all section
            -- copies (no per-section duplicate rows on the dashboard).
            WITH scoped_items AS (
                SELECT di.item_id, di.subject_id, ds.grade, di.item_name, di.assessment_date
                FROM dim_item di
                LEFT JOIN dim_subject ds
                  ON ds.school_id = di.school_id AND ds.subject_id = di.subject_id
                WHERE (CAST(:session_filter AS TEXT) IS NULL OR ds.session = CAST(:session_filter AS TEXT))
                  AND (CAST(:category AS TEXT)  IS NULL OR ds.assessment_type = CAST(:category AS TEXT))
                  AND (CAST(:subject AS TEXT)   IS NULL OR ds.subject = CAST(:subject AS TEXT))
                  AND (CAST(:grade AS TEXT)     IS NULL OR ds.grade = CAST(:grade AS TEXT))
                  AND {_DI_INSTRUCTOR_FILTER_SQL}
                  AND (CAST(:q AS TEXT)         IS NULL OR di.item_name ILIKE '%' || CAST(:q AS TEXT) || '%')
            ),
            subjects AS (
                SELECT subject_id,
                       MIN(grade)           AS grade,
                       MIN(item_name)       AS item_name,
                       MIN(assessment_date) AS assessment_date
                FROM scoped_items
                GROUP BY subject_id
            ),
            item_codes AS (
                SELECT DISTINCT si.subject_id, dqd.standard AS code
                FROM dim_question_data dqd
                JOIN scoped_items si ON si.item_id = dqd.item_id
                WHERE dqd.standard IS NOT NULL AND dqd.standard NOT IN ('', 'null')
            ),
            labeled AS (
                SELECT DISTINCT ic.subject_id, ds.identifier, ds.schoology_standard, ds.strand
                FROM dim_standard ds
                JOIN item_codes ic ON ds.schoology_standard = ic.code
                WHERE ds.strand IS NOT NULL AND ds.strand <> ''
                  AND ds.schoology_standard IS NOT NULL AND ds.schoology_standard <> ''
            ),
            strand_standards AS (
                SELECT subject_id, strand, COUNT(DISTINCT schoology_standard) AS num_standards
                FROM labeled
                GROUP BY subject_id, strand
            ),
            strand_questions AS (
                SELECT si.subject_id AS subject_id, ds.strand AS strand,
                       COUNT(DISTINCT cqs.question_no) AS num_questions
                FROM cube_question_summary cqs
                JOIN scoped_items si ON si.item_id = cqs.item_id
                JOIN labeled l ON l.identifier = cqs.identifier AND l.subject_id = si.subject_id
                JOIN dim_standard ds ON ds.identifier = cqs.identifier
                WHERE ds.strand IS NOT NULL AND ds.strand <> ''
                GROUP BY si.subject_id, ds.strand
            ),
            strand_grade AS (
                -- Merged strand grade from the section-agnostic base cqso
                -- (one row per ukey, already pooled), scoped to the subjects
                -- in view.
                SELECT cqso.subject_id AS subject_id, ds.strand AS strand,
                       AVG(cqso.grade_average) AS grade_average
                FROM cube_question_summary_overall cqso
                JOIN subjects su ON su.subject_id = cqso.subject_id
                JOIN dim_standard ds ON ds.schoology_standard = cqso.standards
                WHERE ds.strand IS NOT NULL AND ds.strand <> ''
                GROUP BY cqso.subject_id, ds.strand
            ),
            rows AS (
                SELECT
                    su.grade           AS grade,
                    sq.strand          AS strand,
                    ss.num_standards   AS total_standards,
                    sq.num_questions   AS total_questions,
                    sg.grade_average   AS grade_average,
                    su.assessment_date AS assessment_date,
                    su.item_name       AS assessment,
                    sq.subject_id      AS item_id,
                    COUNT(*) OVER()    AS total
                FROM strand_questions sq
                JOIN subjects su ON su.subject_id = sq.subject_id
                JOIN strand_standards ss
                  ON ss.subject_id = sq.subject_id AND ss.strand = sq.strand
                LEFT JOIN strand_grade sg
                  ON sg.subject_id = sq.subject_id AND sg.strand = sq.strand
            )
            SELECT * FROM rows
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
            """
        )
        result = await self.session.execute(
            sql,
            {
                "session_filter": session_filter,
                "category": category,
                "subject": subject,
                "grade": grade,
                "instructor": instructor,
                "q": q,
                "limit": limit,
                "offset": offset,
            },
        )
        rows = [_row_to_dict(r) for r in result.all()]
        total = int(rows[0]["total"]) if rows else 0
        for r in rows:
            r.pop("total", None)
        return rows, total

    async def get_standard_rollup_for_item(
        self, subject_id: str
    ) -> List[Dict[str, Any]]:
        """One row per Schoology canonical standard for a given MERGED assessment.

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
        identifier (from ``cube_question_summary``).

        ``grade_average`` reproduces legacy DAX
        ``Grade_Average_Standard_Measure = AVERAGE('cube_question_summary_overall'[Grade_Average])``
        filtered by ``cqso[Standards]`` (``04_dax_measures.csv:148-176``).
        It is sourced from ``cube_question_summary_overall`` (one row per
        ``(question_no, position_number, correct_answer, standards)``) —
        **not** from ``cube_question_summary`` whose per-identifier
        ``AVG(grade_average)`` leaked grades across alias identifiers and
        diverged from PBIX (audit ``06_cubes_and_reports.md`` §D3).

        Two cqso bridges, in preference order:
          1. ``cqso_by_code`` — exact match on the Schoology code that
             appears in the raw data (``cqso.standards = schoology_standard``).
             This keeps standards that share a ``dim_standard.identifier`` but
             differ in their cqso rows distinct (e.g. ``A-REI.2.4.a`` vs
             ``.b``, both identifier ``15b9…``, target 48.1 vs 68.6).
          2. ``cqso_by_id`` — identifier-level average, used as the fallback
             so a Schoology **alias** code (e.g. ``MA.912.AR.3.1``, which
             never appears literally in cqso but shares an identifier with
             ``AI.MA.912.AR.3.1``) still inherits its canonical target.
        Alias codes whose identifier carries no cqso rows resolve to
        NULL — legacy renders these unassessed Schoology aliases as a
        BLANK cell (not 0.0%); see MASTER_PLAN §6 Decision 3.
        """
        sql = text(
            """
            WITH items AS (
                SELECT item_id FROM dim_item WHERE subject_id = :subject_id
            ),
            item_codes AS (
                SELECT DISTINCT standard AS code
                FROM dim_question_data
                WHERE item_id IN (SELECT item_id FROM items)
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
                    COUNT(DISTINCT cqs.question_no) AS num_questions
                FROM cube_question_summary cqs
                WHERE cqs.item_id IN (SELECT item_id FROM items)
                GROUP BY cqs.identifier
            ),
            cqso_by_code AS (
                -- MERGED grade by Schoology code from the section-agnostic base
                -- cqso (pooled across sections), scoped by subject_id. Reverses
                -- the R3 per-item twin read; equals the twin for a single section.
                SELECT
                    cqso.standards          AS schoology_standard,
                    AVG(cqso.grade_average) AS grade_average
                FROM cube_question_summary_overall cqso
                WHERE cqso.subject_id = :subject_id
                GROUP BY cqso.standards
            ),
            cqso_by_id AS (
                SELECT
                    ds.identifier           AS identifier,
                    AVG(cqso.grade_average) AS grade_average
                FROM cube_question_summary_overall cqso
                JOIN dim_standard ds
                  ON ds.schoology_standard = cqso.standards
                WHERE cqso.subject_id = :subject_id
                GROUP BY ds.identifier
            )
            SELECT
                l.schoology_standard                                         AS schoology_standard,
                l.strand                                                     AS strand,
                MAX(COALESCE(p.num_questions, 0))                            AS num_questions,
                -- NULL (not 0) when no cqso rows match this code/identifier:
                -- legacy DAX returns BLANK for an unassessed Schoology alias
                -- standard, which renders as an empty cell (MASTER_PLAN §6,
                -- Decision 3). The serializer preserves None → blank pct.
                MAX(COALESCE(bc.grade_average, bi.grade_average))            AS grade_average
            FROM labeled l
            LEFT JOIN per_identifier p ON p.identifier = l.identifier
            LEFT JOIN cqso_by_code bc ON bc.schoology_standard = l.schoology_standard
            LEFT JOIN cqso_by_id   bi ON bi.identifier = l.identifier
            GROUP BY l.schoology_standard, l.strand
            ORDER BY l.strand, l.schoology_standard
            """
        )
        result = await self.session.execute(sql, {"subject_id": subject_id})
        return [_row_to_dict(r) for r in result.all()]

    async def get_standard_bands_for_item(
        self, subject_id: str
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
            WITH items AS (
                SELECT item_id FROM dim_item WHERE subject_id = :subject_id
            ),
            item_codes AS (
                SELECT DISTINCT standard AS code
                FROM dim_question_data
                WHERE item_id IN (SELECT item_id FROM items)
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
            -- Merged per-identifier grade across the section set: pool every
            -- section's points per question (SUM/SUM), then AVG over questions —
            -- the points-weighted per-identifier average, pooled across sections.
            per_identifier AS (
                SELECT
                    identifier,
                    COUNT(DISTINCT question_no) AS num_questions,
                    AVG(qga)                    AS grade_average
                FROM (
                    SELECT identifier, question_no,
                           SUM(total_score)::numeric
                             / NULLIF(SUM(total_possible_point), 0) AS qga
                    FROM cube_question_summary
                    WHERE item_id IN (SELECT item_id FROM items)
                    GROUP BY identifier, question_no
                ) per_q
                GROUP BY identifier
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
        result = await self.session.execute(sql, {"subject_id": subject_id})
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

    async def get_subject_overview(
        self,
        session_filter: Optional[str] = None,
        grade: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Per-subject ``AVG(cqso.grade_average)`` for the dashboard subject cards.

        Same canonical grade-average source as the KPI strip
        (``cube_question_summary_overall``, legacy DAX
        ``AVERAGE(cqso[Grade_Average])``) — just grouped by subject. Scoped by
        session/grade/category but NOT by subject (every subject is returned so
        the cards stay visible) and NOT by section/instructor: the per-question
        OVERALL cube has no section grain, so the subject cards stay school-wide,
        exactly like the KPI strip and legacy PowerBI.
        """
        sql = text(
            f"""
            SELECT dsubj.subject                  AS subject,
                   AVG(cqso.grade_average)::float AS grade_average
            FROM cube_question_summary_overall cqso
            JOIN dim_subject dsubj
              ON dsubj.school_id = cqso.school_id
             AND dsubj.subject_id = cqso.subject_id
            WHERE {_CQSO_YTD_FILTER_SQL}
              AND dsubj.subject IS NOT NULL AND dsubj.subject <> ''
            GROUP BY dsubj.subject
            ORDER BY dsubj.subject
            """
        )
        result = await self.session.execute(
            sql,
            _school_filter_params(session_filter, None, grade, category, None),
        )
        return [_row_to_dict(r) for r in result.all()]

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
        """Total Students for the Standard/Strand Summary, legacy semantics.

        Replicates the PBIX DAX measure (``04_dax_measures.csv:103``)::

            Total Student =
            SUMX(
                SUMMARIZE(
                    'cube_school_summary',
                    'cube_school_summary'[Item_ID],
                    "UniqueTotalQuestions", MAX('cube_school_summary'[Total_Students])
                ),
                [UniqueTotalQuestions]
            )

        i.e. SUM over distinct ``Item_ID`` of the per-item ``MAX(Total_
        Students)`` — a student who sits N assessments contributes N times.
        This is **not** a DISTINCT headcount (the prior implementation,
        which under-counted: Athenian school-wide = 332 distinct vs the
        legacy 1049). MASTER_PLAN §6 Decision 7 / §7 STDSUM-1.

        ``cube_school_summary`` is the Spark ``rollup`` cube
        (40_schoology_py_spec.md §`Cube_School_Summary`), so the
        subject/year/grade rollup rows carry a NULL ``Item_ID``; those
        collapse into a single SUMMARIZE group exactly as legacy's DAX
        groups them. Filters dereference via ``dim_subject`` (cube only
        carries ``subject_id``), mirroring ``_CQSO_YTD_FILTER_SQL``;
        ``section`` is below this grain and intentionally ignored.
        """
        sql = text(
            """
            SELECT COALESCE(SUM(per_item_students), 0)::bigint AS total_students
            FROM (
                SELECT COALESCE(css.item_id, '')   AS item_key,
                       MAX(css.total_students)     AS per_item_students
                FROM cube_school_summary css
                LEFT JOIN dim_subject dsubj
                  ON dsubj.school_id = css.school_id
                 AND dsubj.subject_id = css.subject_id
                WHERE (CAST(:session_filter AS TEXT) IS NULL OR dsubj.session = CAST(:session_filter AS TEXT))
                  AND (CAST(:subject AS TEXT) IS NULL OR dsubj.subject = CAST(:subject AS TEXT))
                  AND (CAST(:grade AS TEXT) IS NULL OR dsubj.grade = CAST(:grade AS TEXT))
                  AND (CAST(:category AS TEXT) IS NULL OR dsubj.assessment_type = CAST(:category AS TEXT))
                GROUP BY COALESCE(css.item_id, '')
            ) per_item
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
        # Same RLS-opaque-estimate guard as get_school_standard_rollup: force a
        # hash join for the qso_avg join so cube_question_summary_overall isn't
        # re-aggregated per strand row under a Nested Loop. Planner-only; output
        # identical.
        await self.session.execute(text("SET LOCAL enable_nestloop = off"))
        result = await self.session.execute(
            sql,
            _school_filter_params(session_filter, subject, grade, category, section),
        )
        rows = [_row_to_dict(r) for r in result.all()]
        await self.session.execute(text("RESET enable_nestloop"))
        return rows

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
                    dst.cpalms_standard,
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
                    SELECT schoology_standard, cpalms_standard, cluster,
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
                COALESCE(NULLIF(sq.cpalms_standard, ''),
                         sq.schoology_standard, '')                AS cpalms_standard,
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
            GROUP BY 1, 2, 3, 4, 5, 6, 7
            ORDER BY 3 NULLS LAST, 1
            """
        )
        # Force a hash/merge join for the qso_avg join. Under RLS the
        # `school_id = current_setting('app.current_school_id')` predicate is
        # opaque to the planner, so it under-estimates the scoped set at ~1 row
        # and picks a Nested Loop that RE-AGGREGATES cube_question_summary_overall
        # once per std_q row (48M join-filter rows → ~30s on a real school). A
        # hash join computes qso_avg once. Transaction-scoped + reset so sibling
        # queries are unaffected; output is identical (planner-only change).
        await self.session.execute(text("SET LOCAL enable_nestloop = off"))
        result = await self.session.execute(
            sql,
            {
                **_school_filter_params(
                    session_filter, subject, grade, category, section
                ),
                "strand": strand,
            },
        )
        rows = [_row_to_dict(r) for r in result.all()]
        await self.session.execute(text("RESET enable_nestloop"))
        return rows

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
        self, subject_id: str
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
            WHERE item_id IN (
                      SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                  )
            """
        )
        row = (await self.session.execute(sql, {"subject_id": subject_id})).first()
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
        self, subject_id: str, limit: int = 5
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
            WHERE item_id IN (
                      SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                  )
              AND standard IS NOT NULL
              AND standard <> ''
              AND identifier IS NULL
            ORDER BY standard
            LIMIT :limit
            """
        )
        result = await self.session.execute(
            sql, {"subject_id": subject_id, "limit": int(limit)}
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
        # Collapse to one row per (item, question) first (bool_or over the
        # question's rows), THEN count per item. This is identical to the prior
        # two COUNT(DISTINCT question_id) measures (each question maps to exactly
        # one item; verified symmetric-diff = 0 on prod) but replaces a sort-based
        # GroupAggregate behind two COUNT(DISTINCT) with two stacked
        # HashAggregates — no Sort node. ~2.4x faster, results unchanged.
        sql = text(
            """
            WITH per_q AS (
                SELECT
                    dqd.item_id,
                    dqd.question_id,
                    bool_or(dqd.identifier IS NOT NULL) AS is_aligned,
                    MAX(dqd.subject) AS subject,
                    MAX(dqd.grade)   AS grade
                FROM dim_question_data dqd
                GROUP BY dqd.item_id, dqd.question_id
            ),
            per_item AS (
                SELECT
                    q.item_id,
                    MAX(q.subject) AS subject,
                    MAX(q.grade)   AS grade,
                    COUNT(*) AS qs_total,
                    COUNT(*) FILTER (WHERE q.is_aligned) AS qs_aligned
                FROM per_q q
                GROUP BY q.item_id
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
    async def get_assessment_meta(self, subject_id: str) -> Optional[Dict[str, Any]]:
        """Compose the MERGED AssessmentMeta for one assessment (subject_id).

        The same-named assessment given to N sections is one report: the header
        lists the UNION of all section instructors + section names (legacy DAX
        ``CONCATENATEX(DISTINCT(dim_Item[Section_Instructors]))``), keyed on the
        section-agnostic subject_id. Representative item-level fields (name,
        type, school) come from the earliest section copy; assessment_date is
        the earliest across sections. first_access / latest_attempt span the
        whole section set.
        """
        sql = text(
            """
            WITH items AS (
                SELECT item_id, school_id, item_name, item_type, subject_id,
                       section_name, section_instructors, assessment_date
                FROM dim_item
                WHERE subject_id = :subject_id
            ),
            rep AS (
                SELECT * FROM items
                ORDER BY assessment_date ASC NULLS LAST, item_id
                LIMIT 1
            ),
            -- Per-section instructor + name resolution (dim_section preferred,
            -- dim_item fallback), unnested so the union is de-duplicated cleanly.
            sec_src AS (
                SELECT
                    COALESCE(NULLIF(ds.section_instructors, ''),
                             NULLIF(it.section_instructors, '')) AS instructors,
                    COALESCE(NULLIF(ds.section_name, ''),
                             NULLIF(it.section_name, ''))        AS section_name,
                    ds.section_code,
                    ds.section_nid
                FROM items it
                LEFT JOIN dim_section ds
                  ON ds.school_id = it.school_id AND ds.item_id = it.item_id
            ),
            sec AS (
                SELECT
                    (SELECT string_agg(DISTINCT btrim(name), ', ' ORDER BY btrim(name))
                     FROM sec_src s,
                          unnest(string_to_array(s.instructors, ',')) AS name
                     WHERE btrim(name) <> '')                         AS section_instructors,
                    (SELECT string_agg(DISTINCT btrim(nm), ', ' ORDER BY btrim(nm))
                     FROM sec_src s,
                          unnest(string_to_array(s.section_name, ',')) AS nm
                     WHERE btrim(nm) <> '')                           AS section_name,
                    (SELECT string_agg(DISTINCT section_code, ', ' ORDER BY section_code)
                     FROM sec_src WHERE NULLIF(section_code, '') IS NOT NULL) AS section_code,
                    (SELECT string_agg(DISTINCT section_nid, ', ' ORDER BY section_nid)
                     FROM sec_src WHERE NULLIF(section_nid, '') IS NOT NULL)  AS section_nid
            ),
            item_course AS (
                SELECT DISTINCT course_nid
                FROM fact_student_submission
                WHERE item_id IN (SELECT item_id FROM items)
                LIMIT 1
            )
            SELECT
                :subject_id                            AS item_id,
                COALESCE(rep.item_name, '')            AS item_name,
                COALESCE(rep.item_type, '')            AS item_type,
                rep.subject_id,
                COALESCE(sec.section_nid, '')          AS section_nid,
                COALESCE(sec.section_code, '')         AS section_code,
                COALESCE(sec.section_name, rep.section_name, '') AS section_name,
                COALESCE(sec.section_instructors, rep.section_instructors, '') AS section_instructors,
                COALESCE(dc.course_nid, '')            AS course_nid,
                COALESCE(dc.course_name, '')           AS course_name,
                COALESCE(dc.course_code, '')           AS course_code,
                COALESCE(dsubj.subject, '')            AS subject,
                COALESCE(dsubj.grade, '')              AS grade,
                COALESCE(dsubj.session, '')            AS session,
                COALESCE(dsubj.assessment_type, '')    AS assessment_type,
                rep.assessment_date,
                rep.school_id,
                COALESCE(s.name, '')                   AS school_name,
                s.logo_url                             AS school_logo_url
            FROM rep
            LEFT JOIN sec ON TRUE
            LEFT JOIN item_course ic ON TRUE
            LEFT JOIN dim_course dc
              ON dc.school_id = rep.school_id AND dc.course_nid = ic.course_nid
            LEFT JOIN dim_subject dsubj
              ON dsubj.school_id = rep.school_id AND dsubj.subject_id = rep.subject_id
            LEFT JOIN public.schools s
              ON s.school_id = rep.school_id
            LIMIT 1
            """
        )
        result = await self.session.execute(sql, {"subject_id": subject_id})
        row = result.first()
        if not row:
            return None
        meta = _row_to_dict(row)

        # First/latest access from the fact table, across the section set.
        access_sql = text(
            """
            SELECT
                MIN(first_access)   AS first_access,
                MAX(latest_attempt) AS latest_attempt
            FROM fact_student_submission
            WHERE item_id IN (
                      SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                  )
            """
        )
        access_row = (await self.session.execute(access_sql, {"subject_id": subject_id})).first()
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

    # ────────────────────────────────────────────────────────────────────
    # YTD Longitudinal paginated matrix (PBIX ord 8 / 9 / 10 rdlVisual).
    #
    # The three legacy "Longitudinal Report - Year To Date" paginated reports
    # (1/2/3) are the SAME matrix parameterised by (Session, Grade, Subject,
    # Assessment_type, School_ID) — one row per (Classroom Instructor →
    # Student) and one column-pair per STANDARD assessed YTD, where the cell is
    # the POINTS earned over points possible (e.g. ``4/7``) summed across every
    # assessment of that scope, and ``%`` = SUM(received)/SUM(possible).
    #
    # Grain note (alias fan-out): ``fact_student_submission``'s 9-part PK fans
    # a single (user, question, position) attempt into one row per Schoology
    # standard alias (e.g. ``AI.MA.912.AR.1.7`` + ``MA.912.AR.1.7``). Summing
    # the fact directly would double-count those points. We therefore:
    #   1. resolve ONE canonical Schoology standard per (item, question) via
    #      the alphabetical-first non-"Other" label in ``dim_question_data``
    #      (mirrors the committed ``qd_first_standard`` rollup pattern), then
    #   2. dedupe the fact to one row per (user, item, question, position)
    #      before summing, so each attempt contributes its points exactly once
    #      to exactly one standard column.
    # The column label is ``dim_standard.cpalms_standard`` (falling back to the
    # canonical Schoology code), matching the bare-code headers in the legacy
    # PDFs (e.g. ``MA.1.NSO.2.3``). No school_id predicate is needed — RLS
    # scopes every tenant table via ``app.current_school_id``.
    # ────────────────────────────────────────────────────────────────────
    async def get_ytd_longitudinal_cells(
        self,
        session_filter: Optional[str],
        subject: Optional[str],
        grade: Optional[str],
        category: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Long-format (teacher, student, standard) points for the YTD matrix."""
        sql = text(
            """
            WITH qd_first AS (
                -- One canonical Schoology standard per (item, question):
                -- alphabetical-first non-"Other" label (collapses aliases).
                SELECT qd.item_id, qd.question_id,
                       MIN(qd.standard) FILTER (
                           WHERE qd.standard IS NOT NULL
                             AND qd.standard <> ''
                             AND LOWER(qd.standard) <> 'other'
                       ) AS canon_std
                FROM dim_question_data qd
                WHERE (CAST(:session_filter AS TEXT) IS NULL OR qd.session = CAST(:session_filter AS TEXT))
                  AND (CAST(:subject AS TEXT) IS NULL OR qd.subject = CAST(:subject AS TEXT))
                  AND (CAST(:grade AS TEXT) IS NULL OR qd.grade = CAST(:grade AS TEXT))
                  AND (CAST(:category AS TEXT) IS NULL OR qd.assessment_type = CAST(:category AS TEXT))
                GROUP BY qd.item_id, qd.question_id
            ),
            fact_dedup AS (
                -- Undo the standard-alias fan-out: one attempt row per
                -- (user, item, question, position).
                SELECT DISTINCT ON (
                           fss.user_uid, fss.item_id, fss.question_id, fss.position_number
                       )
                       fss.user_uid, fss.user_name, fss.section_nid, fss.school_id,
                       fss.item_id, fss.question_id,
                       fss.points_received, fss.points_possible
                FROM fact_student_submission fss
                WHERE (CAST(:session_filter AS TEXT) IS NULL OR fss.session = CAST(:session_filter AS TEXT))
                  AND (CAST(:subject AS TEXT) IS NULL OR fss.subject = CAST(:subject AS TEXT))
                  AND (CAST(:grade AS TEXT) IS NULL OR fss.grade = CAST(:grade AS TEXT))
                  AND (CAST(:category AS TEXT) IS NULL OR fss.assessment_type = CAST(:category AS TEXT))
                  AND fss.points_possible IS NOT NULL
                  AND fss.points_possible > 0
                ORDER BY fss.user_uid, fss.item_id, fss.question_id,
                         fss.position_number, fss.standard NULLS LAST
            ),
            joined AS (
                SELECT
                    fd.user_uid,
                    fd.user_name,
                    COALESCE(
                        NULLIF(dsec.section_instructors, ''),
                        NULLIF(di_t.section_instructors, ''),
                        'Unassigned'
                    )                                       AS section_instructors,
                    fd.item_id,
                    qf.canon_std                            AS schoology_standard,
                    COALESCE(ds.cpalms_standard, qf.canon_std, 'Other')
                                                            AS standard_label,
                    fd.points_received,
                    fd.points_possible
                FROM fact_dedup fd
                LEFT JOIN qd_first qf
                  ON qf.item_id = fd.item_id AND qf.question_id = fd.question_id
                LEFT JOIN dim_standard ds
                  ON ds.schoology_standard = qf.canon_std
                -- Resolve the instructor the SAME way get_assessment_meta and the
                -- QSR matrix do: join dim_section by item_id (NOT section_nid),
                -- falling back to dim_item. A section_nid is reused across
                -- assessments/dates and dim_section keeps only ONE row per
                -- section_nid, so a section_nid join surfaced a DIFFERENT item's
                -- (possibly different teacher's) instructor list in the YTD
                -- longitudinal rows. item_id + dim_item fallback keeps every
                -- assessment attributed to its own teacher.
                LEFT JOIN dim_section dsec
                  ON dsec.item_id    = fd.item_id
                 AND dsec.school_id  = fd.school_id
                LEFT JOIN dim_item di_t
                  ON di_t.item_id    = fd.item_id
                 AND di_t.school_id  = fd.school_id
            )
            SELECT
                section_instructors,
                user_uid,
                user_name,
                standard_label,
                MIN(schoology_standard)              AS schoology_standard,
                SUM(points_received)::float          AS points_received,
                SUM(points_possible)::float          AS points_possible
            -- No COUNT(DISTINCT item_id) (was unused) and no ORDER BY (the
            -- service re-sorts teachers/students by Score%): both forced a
            -- 549k-row external-merge sort. Without them the GROUP BY is a
            -- HashAggregate. With the covering ytd_dedup index (INCLUDE
            -- user_name/section_nid/points) the dedup is an index-only scan.
            -- ~8s -> ~2s on a full-year school; output unchanged.
            FROM joined
            GROUP BY section_instructors, user_uid, user_name, standard_label
            """
        )
        result = await self.session.execute(
            sql,
            {
                "session_filter": session_filter,
                "subject": subject,
                "grade": grade,
                "category": category,
            },
        )
        return [_row_to_dict(r) for r in result.all()]

    async def get_ytd_longitudinal_tests_taken(
        self,
        session_filter: Optional[str],
        subject: Optional[str],
        grade: Optional[str],
        category: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Per-student count of distinct assessments attempted YTD (Tests Taken).

        Reads the precomputed ``cube_user_summary`` (user×item×question grain,
        carrying session/subject/grade/assessment_type) rather than re-scanning
        the 1.65M-row ``fact_student_submission``: COUNT(DISTINCT item_id) per
        user over the same distinct-assessment set is identical (verified
        symmetric-diff = 0 / sum 28103 = 28103 on prod) but reads ~3x fewer
        pages. The cube is kept fresh by the transform pipeline; the YTD report
        path is session-scoped and cube-backed.
        """
        sql = text(
            """
            SELECT user_uid,
                   COUNT(DISTINCT item_id) AS tests_taken
            FROM cube_user_summary cus
            WHERE (CAST(:session_filter AS TEXT) IS NULL OR cus.session = CAST(:session_filter AS TEXT))
              AND (CAST(:subject AS TEXT) IS NULL OR cus.subject = CAST(:subject AS TEXT))
              AND (CAST(:grade AS TEXT) IS NULL OR cus.grade = CAST(:grade AS TEXT))
              AND (CAST(:category AS TEXT) IS NULL OR cus.assessment_type = CAST(:category AS TEXT))
            GROUP BY user_uid
            """
        )
        result = await self.session.execute(
            sql,
            {
                "session_filter": session_filter,
                "subject": subject,
                "grade": grade,
                "category": category,
            },
        )
        return [_row_to_dict(r) for r in result.all()]

    async def get_ytd_longitudinal_standard_units(
        self,
        session_filter: Optional[str],
        subject: Optional[str],
        grade: Optional[str],
        category: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Per-standard list of assessment (unit) names — V3 secondary header."""
        sql = text(
            """
            WITH qd_first AS (
                SELECT qd.item_id, qd.question_id,
                       MIN(qd.standard) FILTER (
                           WHERE qd.standard IS NOT NULL
                             AND qd.standard <> ''
                             AND LOWER(qd.standard) <> 'other'
                       ) AS canon_std
                FROM dim_question_data qd
                WHERE (CAST(:session_filter AS TEXT) IS NULL OR qd.session = CAST(:session_filter AS TEXT))
                  AND (CAST(:subject AS TEXT) IS NULL OR qd.subject = CAST(:subject AS TEXT))
                  AND (CAST(:grade AS TEXT) IS NULL OR qd.grade = CAST(:grade AS TEXT))
                  AND (CAST(:category AS TEXT) IS NULL OR qd.assessment_type = CAST(:category AS TEXT))
                GROUP BY qd.item_id, qd.question_id
            ),
            items AS (
                SELECT DISTINCT fss.item_id, fss.item_name
                FROM fact_student_submission fss
                WHERE (CAST(:session_filter AS TEXT) IS NULL OR fss.session = CAST(:session_filter AS TEXT))
                  AND (CAST(:subject AS TEXT) IS NULL OR fss.subject = CAST(:subject AS TEXT))
                  AND (CAST(:grade AS TEXT) IS NULL OR fss.grade = CAST(:grade AS TEXT))
                  AND (CAST(:category AS TEXT) IS NULL OR fss.assessment_type = CAST(:category AS TEXT))
            )
            SELECT
                COALESCE(ds.cpalms_standard, qf.canon_std, 'Other') AS standard_label,
                STRING_AGG(DISTINCT it.item_name, ' / ' ORDER BY it.item_name)
                                                                    AS unit_names
            FROM qd_first qf
            JOIN items it ON it.item_id = qf.item_id
            LEFT JOIN dim_standard ds ON ds.schoology_standard = qf.canon_std
            WHERE qf.canon_std IS NOT NULL
            GROUP BY COALESCE(ds.cpalms_standard, qf.canon_std, 'Other')
            """
        )
        result = await self.session.execute(
            sql,
            {
                "session_filter": session_filter,
                "subject": subject,
                "grade": grade,
                "category": category,
            },
        )
        return [_row_to_dict(r) for r in result.all()]

    # ────────────────────────────────────────────────────────────────────
    # Paginated reports (PBIX ord 6/7/16, 11, 12, 13)
    # ────────────────────────────────────────────────────────────────────
    async def get_question_summary_matrix_rows(
        self, subject_id: str
    ) -> List[Dict[str, Any]]:
        """One row per (student, question) for the MERGED QSR matrix.

        Widens to the assessment's section set so every section's students pool
        into one report; the per-section instructor is resolved off each
        student's OWN section copy (``pa.item_id``), so the matrix groups by
        instructor across all sections (legacy QSR "by teacher" bands within one
        report). Columns are keyed on question_no (section-invariant), so a
        student appears once per question regardless of how many section copies
        the assessment has.
        """
        sql = text(
            """
            WITH items AS (
                SELECT item_id FROM dim_item WHERE subject_id = :subject_id
            ),
            per_question AS (
                -- One row per (section copy) question. The dim_standard alias
                -- table can map a single schoology_standard to many rows
                -- (Schoology course-prefix aliases — see
                -- docs/audit/legacy-schoology-cpalms-mapping.md); collapse to
                -- one cpalms_standard here so the (user, question) attempt rows
                -- below do NOT fan out and inflate the cell counts (PAG-6).
                SELECT DISTINCT ON (qs.question_id)
                    qs.school_id,
                    qs.question_id,
                    qs.question_no,
                    qs.position_number,
                    qs.correct_answer,
                    qs.standards,
                    qs.standard,
                    ds.cpalms_standard
                FROM cube_question_summary qs
                -- dim_standard is global (no school_id) — RLS not applicable.
                LEFT JOIN dim_standard ds
                  ON ds.schoology_standard = qs.standard
                WHERE qs.item_id IN (SELECT item_id FROM items)
                ORDER BY qs.question_id,
                         NULLIF(regexp_replace(COALESCE(qs.question_no, ''), '[^0-9]', '', 'g'), '')::int NULLS LAST,
                         ds.cpalms_standard NULLS LAST
            ),
            -- Per-(user, question) latest attempt, so re-takes don't double-count.
            -- fss.submission is UUID v7 (time-ordered) per CLAUDE.md. question_id
            -- is per-section, so DISTINCT ON (user, question_id) keeps each
            -- student's own section attempt.
            per_attempt AS (
                SELECT DISTINCT ON (fss.user_uid, fss.question_id)
                    fss.school_id,
                    fss.item_id,
                    fss.user_uid,
                    fss.user_name,
                    fss.section_nid,
                    fss.question_id,
                    fss.points_received,
                    fss.points_possible
                FROM fact_student_submission fss
                WHERE fss.item_id IN (SELECT item_id FROM items)
                ORDER BY fss.user_uid, fss.question_id,
                         fss.submission DESC NULLS LAST,
                         fss.latest_attempt DESC NULLS LAST
            )
            SELECT
                pa.user_uid,
                pa.user_name,
                -- Per-section instructor (dim_section on the student's OWN
                -- section copy) is most specific; fall back to the
                -- assessment-level list (dim_item). "Unassigned" only when
                -- neither resolves.
                COALESCE(
                    NULLIF(dsec.section_instructors, ''),
                    NULLIF(di.section_instructors, ''),
                    'Unassigned'
                )                                            AS section_instructors,
                -- The merged matrix column key is question_no (section-agnostic);
                -- the per-section question_id would split each question into one
                -- column per section. A student answers each question_no once, so
                -- cells collapse correctly.
                pq.question_no                               AS question_id,
                pa.points_received,
                pa.points_possible,
                pq.question_no,
                NULLIF(regexp_replace(COALESCE(pq.question_no, ''), '[^0-9]', '', 'g'), '')::int
                                                            AS sorting_question_no,
                pq.position_number,
                pq.correct_answer,
                pq.standards,
                pq.standard                                  AS schoology_standard,
                pq.cpalms_standard
            FROM per_attempt pa
            JOIN per_question pq ON pq.question_id = pa.question_id
            -- Resolve the instructor off the student's OWN section copy so each
            -- student bands under the right teacher across the merged sections.
            LEFT JOIN dim_section dsec
              ON dsec.item_id = pa.item_id
             AND dsec.school_id = pa.school_id
            LEFT JOIN dim_item di
              ON di.item_id = pa.item_id
             AND di.school_id = pa.school_id
            ORDER BY section_instructors, pa.user_name,
                     NULLIF(regexp_replace(COALESCE(pq.question_no, ''), '[^0-9]', '', 'g'), '')::int NULLS LAST,
                     pq.question_no
            """
        )
        result = await self.session.execute(sql, {"subject_id": subject_id})
        return [_row_to_dict(r) for r in result.all()]

    async def get_cube_grand_total_for_item(
        self, subject_id: str
    ) -> Optional[Dict[str, Any]]:
        """Cube-derived MERGED grand total for fact-less (parquet-loaded) schools.

        When ``get_question_summary_matrix_rows`` returns no rows (no
        ``fact_student_submission`` data), the QSR matrix has no per-student
        body. Sum the per-question cube across the assessment's section set so
        the footer still shows the real merged aggregate (== the cube-derived
        KPI strip) instead of 0/0/0%.
        """
        sql = text(
            """
            SELECT
                SUM(total_possible_point) AS total_possible_point,
                SUM(total_score)          AS total_score
            FROM cube_question_summary
            WHERE item_id IN (
                      SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                  )
            """
        )
        result = await self.session.execute(sql, {"subject_id": subject_id})
        row = result.first()
        return _row_to_dict(row) if row else None

    async def get_qra_by_teacher_rows(
        self, subject_id: str
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
                WHERE item_id IN (
                          SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                      )
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
                WHERE item_id IN (
                          SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                      )
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
        result = await self.session.execute(sql, {"subject_id": subject_id})
        return [_row_to_dict(r) for r in result.all()]

    async def get_qra_by_standard_teacher_rows(
        self, subject_id: str
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
                WHERE item_id IN (
                          SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                      )
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
                WHERE item_id IN (
                          SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                      )
                  AND standard IS NOT NULL AND standard <> ''
                GROUP BY school_id, item_id, question_id
            )
            SELECT
                -- Legacy paginated (SSRS) renders AND sorts the FULL
                -- Schoology code (e.g. "SC.3.N.1.6", "MA.1.NSO.1.1"),
                -- not the stripped cPalms sub-code. Verified across the
                -- historical *By Standard And Teacher.pdf* set (PAG-7).
                b.standard                                          AS cpalms_standard,
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
                    PARTITION BY b.standard, b.section_instructors
                )                                                     AS teacher_standard_avg,
                AVG(b.grade_average) OVER (
                    PARTITION BY b.standard
                )                                                     AS standard_avg
            FROM base b
            -- dim_standard is global (no school_id) — RLS not applicable.
            LEFT JOIN dim_standard ds
              ON ds.schoology_standard = b.standard
            LEFT JOIN qd_standards qds
              ON qds.item_id = b.item_id
             AND qds.question_id = b.question_id
             AND qds.school_id = b.school_id
            -- Group ordering: lexical ascending by the full Schoology code,
            -- matching the legacy SSRS render order (PAG-7).
            ORDER BY b.standard, b.section_instructors,
                     b.grade_average ASC NULLS LAST,
                     b.sorting_question_no NULLS LAST, b.question_no
            """
        )
        result = await self.session.execute(sql, {"subject_id": subject_id})
        return [_row_to_dict(r) for r in result.all()]


    async def get_question_overall(
        self, subject_id: str, question_no: str
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
            WITH items AS (
                SELECT item_id FROM dim_item WHERE subject_id = :subject_id
            ),
            -- question_no is the section-agnostic merged question identity.
            qs_meta AS (
                SELECT DISTINCT ON (question_no)
                       question_no, position_number, question_type, standard
                FROM cube_question_summary
                WHERE item_id IN (SELECT item_id FROM items) AND question_no = :question_no
                ORDER BY question_no,
                         NULLIF(regexp_replace(COALESCE(position_number, ''), '[^0-9]', '', 'g'), '')::int NULLS LAST,
                         position_number
            ),
            uk_qids AS (
                SELECT DISTINCT question_id
                FROM cube_question_summary
                WHERE item_id IN (SELECT item_id FROM items) AND question_no = :question_no
            ),
            qd_standards AS (
                SELECT STRING_AGG(DISTINCT standard, E'\n' ORDER BY standard) AS standards
                FROM dim_question_data
                WHERE question_id IN (SELECT question_id FROM uk_qids)
                  AND standard IS NOT NULL AND standard <> ''
            ),
            qd_first_standard AS (
                SELECT MIN(standard) FILTER (
                           WHERE standard IS NOT NULL
                             AND standard <> ''
                             AND LOWER(standard) <> 'other'
                       ) AS first_standard
                FROM dim_question_data
                WHERE question_id IN (SELECT question_id FROM uk_qids)
            ),
            qd_description AS (
                SELECT MAX(ds.description) AS description
                FROM qd_first_standard qfs
                LEFT JOIN dim_standard ds
                  ON ds.schoology_standard = qfs.first_standard
            ),
            -- base cqso pooled to question_no (already merged across sections;
            -- a multi-answer question_no concatenates its ukey rows).
            cqso AS (
                SELECT question_no,
                       MAX(question)                  AS question,
                       STRING_AGG(DISTINCT correct_answer, ', ') AS correct_answer,
                       SUM(total_possible_point)      AS total_possible_point,
                       SUM(total_score)               AS total_score,
                       SUM(total_score)::numeric / NULLIF(SUM(total_possible_point), 0) AS grade_average,
                       MAX(description)               AS description
                FROM cube_question_summary_overall
                WHERE subject_id = :subject_id AND question_no = :question_no
                GROUP BY question_no
            )
            SELECT
                c.question_no                                   AS question_id,
                c.question_no                                   AS question_no,
                COALESCE(qm.position_number, '')                AS position_number,
                c.question                                      AS question,
                COALESCE(qm.question_type, '')                  AS question_type,
                c.correct_answer                                AS correct_answer,
                c.total_possible_point                          AS total_possible_point,
                c.total_score                                   AS total_score,
                c.grade_average                                 AS grade_average,
                COALESCE(qds.standards, '')                     AS standards,
                COALESCE(qm.standard, '')                       AS strand_raw,
                COALESCE(qdd.description, c.description, '')     AS description
            FROM cqso c
            LEFT JOIN qs_meta qm ON TRUE
            LEFT JOIN qd_standards qds ON TRUE
            LEFT JOIN qd_description qdd ON TRUE
            LIMIT 1
            """
        )
        result = await self.session.execute(
            sql, {"subject_id": subject_id, "question_no": question_no}
        )
        row = result.first()
        return _row_to_dict(row) if row else None


    async def get_distractor_breakdown(
        self, subject_id: str, question_no: str
    ) -> List[Dict[str, Any]]:
        """MERGED per-answer-choice rollup for one question (by ``question_no``).

        Resolves the per-section ``question_id`` set for this ``question_no``
        (across the assessment's section copies) and pools every section's
        ``cube_questionincorrectchoice_summary`` detail rows.

        Empty/null answer_submission rows are dropped (matches PBIX M filter).
        ``answer_submission`` arrives prefixed with a randomised option letter
        ("a. ", "b. ", …) — Schoology shuffles option positions per student, so
        the same logical answer can appear under 4 different letters. The cube
        preserves the raw string for legacy parity (notebook lines 1772-1798),
        so we strip the prefix and re-aggregate here at the read layer.
        """
        sql = text(
            r"""
            WITH qids AS (
                SELECT DISTINCT question_id
                FROM cube_question_summary
                WHERE item_id IN (
                          SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                      )
                  AND question_no = :question_no
            ),
            choices AS (
                SELECT
                    regexp_replace(qic.answer_submission, '^\s*[a-zA-Z]\.\s+', '')
                                                          AS answer_submission,
                    SUM(qic.total_student)                AS students_count,
                    SUM(qic.total_score)                  AS total_score,
                    SUM(qic.total_possible_point)         AS total_possible_point
                FROM cube_questionincorrectchoice_summary qic
                JOIN qids ON qids.question_id = qic.question_id
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
            sql, {"subject_id": subject_id, "question_no": question_no}
        )
        return [_row_to_dict(r) for r in result.all()]


    async def get_per_student_attempts(
        self, subject_id: str, question_no: str
    ) -> List[Dict[str, Any]]:
        """Every student × this question row for the MERGED IAD per-student table.

        ``question_no`` is the section-agnostic merged question identity; the
        fact table is keyed on the per-section ``question_id``, so resolve the
        section question_ids for this question_no (via ``cube_question_summary``
        over the assessment's section set) and pool every section's attempts.

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
            WITH uk_qids AS (
                SELECT DISTINCT question_id
                FROM cube_question_summary
                WHERE item_id IN (
                          SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                      )
                  AND question_no = :question_no
            )
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
                WHERE fss.item_id IN (
                          SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                      )
                  AND fss.question_id IN (SELECT question_id FROM uk_qids)
                  AND fss.user_uid IS NOT NULL
                ORDER BY fss.user_uid, fss.submission
            ) deduped
            ORDER BY user_name
            """
        )
        result = await self.session.execute(
            sql, {"subject_id": subject_id, "question_no": question_no}
        )
        return [_row_to_dict(r) for r in result.all()]

