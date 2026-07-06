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
# session / subject / grade / assessment_type / section. The slicer values
# come from dim_subject (which carries the full subject_course_overrides /
# subject_overrides labels, e.g. "HS Physics"), but cube_question_summary's
# denormalised subject/grade columns are sourced from dim_question_data,
# which can only apply subject_overrides (no course_name) — so its subject
# stays the un-overridden base ("Science"). Filtering qs.subject directly
# therefore returned 0 rows for any course-overridden subject. We instead
# scope subject/grade/session/assessment_type through dim_subject (alias
# ``dsub``, joined on subject_id) so the filter agrees with the slicer;
# section still scopes on qs. Both get_school_strand_rollup and
# get_school_standard_rollup JOIN dim_subject dsub in their scoped_qs CTE.
_QS_SCHOOL_FILTER_SQL = """\
(CAST(:session_filter AS TEXT) IS NULL OR dsub.session = CAST(:session_filter AS TEXT))
                  AND (CAST(:subject AS TEXT) IS NULL OR dsub.subject = CAST(:subject AS TEXT))
                  AND (CAST(:grade AS TEXT) IS NULL OR dsub.grade = CAST(:grade AS TEXT))
                  AND (CAST(:category AS TEXT) IS NULL OR dsub.assessment_type = CAST(:category AS TEXT))
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

# MULTI-instructor narrowing for the MERGED per-assessment ``items`` CTE
# (``SELECT item_id FROM dim_item WHERE subject_id = :instr_subject_id``).
# ``:instructor`` is a single comma-separated string (e.g. "Jane Doe,John
# Smith"); an item matches when ANY comma-split element of its
# ``dim_item.section_instructors`` equals (btrim) ANY comma-split element of
# the requested list. Both sides use the SAME btrim/comma-split as
# ``dim_repository.list_instructors`` so a full name matches exactly with no
# substring over-match. NULL/empty ``:instructor`` short-circuits to TRUE, so
# the enclosing query stays byte-identical to the pre-filter read. References
# ``dim_item`` unqualified so it drops straight into the merged-report
# ``items`` CTE (no ``di`` alias).
_DI_ITEM_INSTRUCTOR_MATCH_SQL = """(CAST(:instructor AS TEXT) IS NULL OR EXISTS (
                  SELECT 1
                  FROM unnest(string_to_array(dim_item.section_instructors, ',')) AS _ins(name)
                  JOIN unnest(string_to_array(CAST(:instructor AS TEXT), ',')) AS _sel(want)
                    ON btrim(_ins.name) = btrim(_sel.want)
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
        self, subject_id: str, instructor: Optional[str] = None
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

        ``instructor`` (OPTIONAL, single comma-separated string) narrows the
        ``items`` CTE to the sections taught by ANY of the listed instructors;
        every downstream metric (Total Students, points, per-question grades)
        recomputes over the narrowed section set. NULL/empty = no filter,
        byte-identical to today.
        """
        sql = text(
            f"""
            WITH items AS (
                SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                  AND {_DI_ITEM_INSTRUCTOR_MATCH_SQL}
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
            -- MERGED school totals, recomputed over the (instructor-)narrowed
            -- ``items`` section set so an instructor filter pools only the
            -- matching sections. With NULL/empty :instructor ``items`` spans
            -- every section, and SUM over the per-section (item_id IS NOT NULL)
            -- rows equals the (school_id, subject_id) GROUPING-SETS rollup row
            -- (item_id IS NULL) — so the unfiltered read stays byte-identical.
            -- total_students mirrors legacy SUMX(SUMMARIZE(Item_ID,
            -- MAX(Total_Students))): sum the per-section student counts (MAX
            -- de-dups the multi-subject duplicate rows a single item can carry
            -- — e.g. Brightview 7566518630). A single-section assessment
            -- collapses to the lone per-item value.
            school AS (
                SELECT
                    COALESCE(SUM(ts), 0)            AS total_students,
                    SUM(possible)                   AS total_possible_point,
                    SUM(score)                      AS total_score
                FROM (
                    SELECT item_id,
                           MAX(total_students)      AS ts,
                           SUM(total_possible_point) AS possible,
                           SUM(total_score)          AS score
                    FROM cube_school_summary
                    WHERE subject_id = :subject_id
                      AND item_id IN (SELECT item_id FROM items)
                    GROUP BY item_id
                ) per_item
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
                    -- Points-weighted merged grade over the narrowed section
                    -- set. SUM/SUM across the per-section (item_id IS NOT NULL)
                    -- rows of ``items`` equals the (subject_id, item_id IS NULL)
                    -- rollup row's total_score/total_possible_point when no
                    -- instructor filter is applied — byte-identical unfiltered.
                    (
                        SELECT SUM(total_score)::numeric
                                 / NULLIF(SUM(total_possible_point), 0)
                        FROM cube_school_summary
                        WHERE subject_id = :subject_id
                          AND item_id IN (SELECT item_id FROM items)
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
        result = await self.session.execute(
            sql, {"subject_id": subject_id, "instructor": instructor}
        )
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
        self, subject_id: str, instructor: Optional[str] = None
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

        ``instructor`` (OPTIONAL) narrows the ``items`` CTE to the matching
        sections; NULL/empty = no filter (byte-identical to today).
        """
        sql = text(
            f"""
            WITH items AS (
                SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                  AND {_DI_ITEM_INSTRUCTOR_MATCH_SQL}
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
        result = await self.session.execute(
            sql, {"subject_id": subject_id, "instructor": instructor}
        )
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
    async def get_questions_overall_for_item(
        self, subject_id: str, instructor: Optional[str] = None
    ) -> List[Dict[str, Any]]:
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

        ``instructor`` (OPTIONAL) narrows the ``items`` CTE — and therefore the
        per-question_no numerics / metadata / grades sourced from the
        per-section ``cube_question_summary`` — to the matching sections.
        NULL/empty = no filter (byte-identical). The pooled distractor /
        named-student list (``cqso_agg``) is sourced from the section-agnostic
        ``cube_question_summary_overall`` (keyed on subject_id) which carries no
        per-section split, so it stays the merged content — the same boundary
        the dashboard By-Strand grid keeps for its cqso-sourced grade.
        """
        sql = text(
            f"""
            WITH items AS (
                SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                  AND {_DI_ITEM_INSTRUCTOR_MATCH_SQL}
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
        result = await self.session.execute(
            sql, {"subject_id": subject_id, "instructor": instructor}
        )
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
        self, subject_id: str, instructor: Optional[str] = None
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

        ``instructor`` (OPTIONAL) narrows the ``items`` CTE (and so the
        num_standards / num_questions counts that key off it) to the matching
        sections; NULL/empty = no filter (byte-identical). The merged strand
        grade (``strand_grade``, sourced from the section-agnostic cqso by
        subject_id) stays the pooled merged value — the same boundary the
        dashboard By-Strand grid keeps.
        """
        sql = text(
            f"""
            WITH items AS (
                SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                  AND {_DI_ITEM_INSTRUCTOR_MATCH_SQL}
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
        result = await self.session.execute(
            sql, {"subject_id": subject_id, "instructor": instructor}
        )
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
        self, subject_id: str, instructor: Optional[str] = None
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

        ``instructor`` (OPTIONAL) narrows the ``items`` CTE (and the per-code
        num_questions that keys off it) to the matching sections; NULL/empty =
        no filter (byte-identical). The merged per-code/per-identifier grade
        (sourced from the section-agnostic cqso by subject_id) stays the pooled
        merged value — same boundary as the dashboard By-Strand grid.
        """
        sql = text(
            f"""
            WITH items AS (
                SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                  AND {_DI_ITEM_INSTRUCTOR_MATCH_SQL}
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
            per_code AS (
                -- num_questions at the Schoology-CODE grain (NOT identifier).
                -- A benchmark and its sub-standards (e.g. ELA.1.F.1.3.c and
                -- ELA.1.F.1.3.f) share ONE dim_standard.identifier, so counting
                -- DISTINCT question_no per identifier double-attributes every
                -- sibling's questions to each code (GAI-8: .c and .f both showed
                -- 9 = 6+3, inflating the "# of Questions" column past the real
                -- assessment total). dim_question_data.standard carries the exact
                -- per-code tag; Schoology aliases that share an identifier ARE
                -- tagged on the same questions, so they still resolve to equal
                -- counts (no alias regression — verified on AI.MA.912.* items).
                SELECT
                    standard AS schoology_standard,
                    COUNT(DISTINCT question_no) AS num_questions
                FROM dim_question_data
                WHERE item_id IN (SELECT item_id FROM items)
                  AND standard IS NOT NULL
                  AND standard NOT IN ('', 'null')
                GROUP BY standard
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
            LEFT JOIN per_code p ON p.schoology_standard = l.schoology_standard
            LEFT JOIN cqso_by_code bc ON bc.schoology_standard = l.schoology_standard
            LEFT JOIN cqso_by_id   bi ON bi.identifier = l.identifier
            GROUP BY l.schoology_standard, l.strand
            ORDER BY l.strand, l.schoology_standard
            """
        )
        result = await self.session.execute(
            sql, {"subject_id": subject_id, "instructor": instructor}
        )
        return [_row_to_dict(r) for r in result.all()]

    async def get_standard_bands_for_item(
        self, subject_id: str, instructor: Optional[str] = None
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

        ``instructor`` (OPTIONAL) narrows the ``items`` CTE; both the band
        membership AND the points-weighted band grade (sourced from the
        per-section ``cube_question_summary`` scoped by ``items``) recompute
        over the matching sections. NULL/empty = no filter (byte-identical).
        """
        sql = text(
            f"""
            WITH items AS (
                SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                  AND {_DI_ITEM_INSTRUCTOR_MATCH_SQL}
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
        result = await self.session.execute(
            sql, {"subject_id": subject_id, "instructor": instructor}
        )
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
        """Total Students for the Standard/Strand Summary — DISTINCT headcount.

        Stakeholder validation (Jun 24 dashboard review / Linear GAI-20):
        the dashboard "Total Students" tile read as unreasonably high — one
        grade showed thousands because the legacy PBIX measure summed
        per-assessment headcounts (``SUMX(SUMMARIZE(Item_ID, MAX(Total_
        Students)))``, ``04_dax_measures.csv:103``), so a student who sat N
        assessments counted N times (e.g. Grade 1 = 11,075 attempt-sum vs 263
        distinct students). The product owner flagged this in review and asked
        for a believable count, so this metric is now a TRUE DISTINCT student
        headcount — a deliberate, documented deviation from the legacy
        SUMX mirror (MASTER_PLAN §6 Decision 7).

        Distinct students come from ``fact_student_submission`` scoped by the
        same ``dim_subject`` filters (session/subject/grade/category). Cube-only
        (parquet-loaded) schools have no fact rows, so for them we fall back to
        the **de-leaked** legacy SUMX from ``cube_school_summary`` (the prior
        query also erroneously folded the NULL-``Item_ID`` subject/grade rollup
        rows into the sum via ``COALESCE(item_id,'')``; this fallback filters
        ``item_id IS NOT NULL`` so it matches the true legacy SUMX). ``section``
        is below this grain and intentionally ignored.
        """
        sql = text(
            """
            WITH distinct_students AS (
                SELECT COUNT(DISTINCT f.user_uid) AS n
                FROM fact_student_submission f
                JOIN dim_subject dsubj
                  ON dsubj.school_id = f.school_id
                 AND dsubj.subject_id = f.subject_id
                WHERE (CAST(:session_filter AS TEXT) IS NULL OR dsubj.session = CAST(:session_filter AS TEXT))
                  AND (CAST(:subject AS TEXT) IS NULL OR dsubj.subject = CAST(:subject AS TEXT))
                  AND (CAST(:grade AS TEXT) IS NULL OR dsubj.grade = CAST(:grade AS TEXT))
                  AND (CAST(:category AS TEXT) IS NULL OR dsubj.assessment_type = CAST(:category AS TEXT))
            ),
            cube_sumx AS (
                SELECT COALESCE(SUM(per_item_students), 0) AS n
                FROM (
                    SELECT css.item_id,
                           MAX(css.total_students) AS per_item_students
                    FROM cube_school_summary css
                    LEFT JOIN dim_subject dsubj
                      ON dsubj.school_id = css.school_id
                     AND dsubj.subject_id = css.subject_id
                    WHERE css.item_id IS NOT NULL
                      AND (CAST(:session_filter AS TEXT) IS NULL OR dsubj.session = CAST(:session_filter AS TEXT))
                      AND (CAST(:subject AS TEXT) IS NULL OR dsubj.subject = CAST(:subject AS TEXT))
                      AND (CAST(:grade AS TEXT) IS NULL OR dsubj.grade = CAST(:grade AS TEXT))
                      AND (CAST(:category AS TEXT) IS NULL OR dsubj.assessment_type = CAST(:category AS TEXT))
                    GROUP BY css.item_id
                ) per_item
            )
            -- Prefer the distinct headcount; fall back to the cube SUMX only
            -- for fact-less schools. NULLIF lets Postgres skip the cube_sumx
            -- scan whenever the distinct count is non-zero (the common case).
            SELECT COALESCE(
                       NULLIF((SELECT n FROM distinct_students), 0),
                       (SELECT n FROM cube_sumx)
                   )::bigint AS total_students
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
        across all assessments matching the filter context. Subject / grade /
        session / assessment_type are scoped through dim_subject (the slicer's
        label source) via the subject_id join in ``_QS_SCHOOL_FILTER_SQL``;
        section still scopes on cube_question_summary.
        """
        sql = text(
            f"""
            WITH strand_agg AS (
                -- One row per Strand from the overall cube (legacy's DAX table),
                -- joined to dim_standard by the standard CODE. Legacy measures:
                --   grade_average = AVERAGE(cqso[Grade_Average])       (flat)
                --   num_standards = DISTINCTCOUNT(cqso[Standards])     (by code)
                --   num_questions = DISTINCTCOUNT(cqso[Question_No])
                -- Scoped via dim_subject (session/subject/grade/assessment_type);
                -- no section grain on this page.
                SELECT ds.strand                        AS strand,
                       COUNT(DISTINCT cqso.standards)    AS num_standards,
                       COUNT(DISTINCT cqso.question_no)  AS num_questions,
                       AVG(cqso.grade_average)           AS grade_average
                FROM cube_question_summary_overall cqso
                JOIN dim_subject dsubj
                  ON dsubj.school_id = cqso.school_id
                 AND dsubj.subject_id = cqso.subject_id
                JOIN dim_standard ds
                  ON ds.schoology_standard = cqso.standards
                WHERE {_CQSO_YTD_FILTER_SQL}
                  AND ds.strand IS NOT NULL AND ds.strand <> ''
                  AND cqso.standards IS NOT NULL AND cqso.standards <> ''
                GROUP BY ds.strand
            ),
            strand_subjects AS (
                SELECT ds.strand AS strand,
                       ARRAY_AGG(DISTINCT dsubj.subject ORDER BY dsubj.subject) AS subjects
                FROM cube_question_summary_overall cqso
                JOIN dim_subject dsubj
                  ON dsubj.school_id = cqso.school_id
                 AND dsubj.subject_id = cqso.subject_id
                JOIN dim_standard ds
                  ON ds.schoology_standard = cqso.standards
                WHERE {_CQSO_YTD_FILTER_SQL}
                  AND ds.strand IS NOT NULL AND ds.strand <> ''
                  AND dsubj.subject IS NOT NULL AND dsubj.subject <> ''
                GROUP BY ds.strand
            )
            SELECT
                sa.strand                                AS strand,
                sa.num_standards                         AS num_standards,
                sa.num_questions                         AS num_questions,
                0                                        AS num_assessments,
                sa.grade_average                         AS grade_average,
                COALESCE(ss.subjects, ARRAY[]::text[])   AS subjects
            FROM strand_agg sa
            LEFT JOIN strand_subjects ss ON ss.strand = sa.strand
            ORDER BY sa.strand
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
            WITH scoped_cqso AS (
                -- Every overall-cube row in scope (legacy scopes the Standard
                -- Summary through dim_subject: session/subject/grade/assessment_type;
                -- there is no section grain on this page). This is the DAX
                -- table the page's measures read.
                SELECT cqso.standards        AS schoology_standard,
                       cqso.question_no      AS question_no,
                       cqso.grade_average    AS grade_average,
                       dsubj.grade           AS grade
                FROM cube_question_summary_overall cqso
                JOIN dim_subject dsubj
                  ON dsubj.school_id = cqso.school_id
                 AND dsubj.subject_id = cqso.subject_id
                WHERE {_CQSO_YTD_FILTER_SQL}
                  AND cqso.standards IS NOT NULL AND cqso.standards <> ''
            ),
            agg AS (
                -- One row per standard CODE: legacy `Grade_Average_Standard_Measure`
                -- = AVERAGE(cqso[Grade_Average]) (flat, BLANK when empty) and
                -- `Total Question` = DISTINCTCOUNT(cqso[Question_No]).
                SELECT schoology_standard,
                       COUNT(DISTINCT question_no) AS num_questions,
                       AVG(grade_average)          AS grade_average,
                       COALESCE(
                           array_agg(DISTINCT NULLIF(grade, ''))
                             FILTER (WHERE NULLIF(grade, '') IS NOT NULL),
                           ARRAY[]::text[]
                       )                           AS grades
                FROM scoped_cqso
                GROUP BY schoology_standard
            ),
            std_meta AS (
                -- One dim_standard row per code (dedupe aliases deterministically)
                -- for the card chrome: strand / cluster / cognitive complexity /
                -- description / curriculum subject / adopted date.
                SELECT DISTINCT ON (schoology_standard)
                    schoology_standard, cpalms_standard, strand, cluster,
                    cognitive_complexity_rating, subject,
                    custom_cleaned_description, description, last_change_date_time
                FROM dim_standard
                WHERE schoology_standard IS NOT NULL AND schoology_standard <> ''
                ORDER BY schoology_standard, identifier
            )
            SELECT
                a.schoology_standard                              AS schoology_standard,
                COALESCE(NULLIF(m.cpalms_standard, ''),
                         a.schoology_standard)                    AS cpalms_standard,
                COALESCE(m.strand, '')                            AS strand,
                COALESCE(m.cluster, '')                           AS cluster,
                COALESCE(m.cognitive_complexity_rating, '')       AS cognitive_complexity,
                COALESCE(NULLIF(m.custom_cleaned_description, ''),
                         m.description, '')                       AS description,
                COALESCE(m.subject, '')                           AS subject,
                a.grades                                          AS grades,
                a.num_questions                                   AS num_questions,
                0                                                 AS num_assessments,
                a.grade_average                                   AS grade_average,
                m.last_change_date_time                           AS last_change_date_time
            FROM agg a
            LEFT JOIN std_meta m ON m.schoology_standard = a.schoology_standard
            WHERE (CAST(:strand AS TEXT) IS NULL OR m.strand = CAST(:strand AS TEXT))
            ORDER BY m.strand NULLS LAST, a.schoology_standard
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
        self, subject_id: str, instructor: Optional[str] = None
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

        ``instructor`` (OPTIONAL) narrows the item set to the matching
        sections; NULL/empty = no filter (byte-identical).
        """
        sql = text(
            f"""
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
                        AND {_DI_ITEM_INSTRUCTOR_MATCH_SQL}
                  )
            """
        )
        row = (
            await self.session.execute(
                sql, {"subject_id": subject_id, "instructor": instructor}
            )
        ).first()
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
        self, subject_id: str, limit: int = 5, instructor: Optional[str] = None
    ) -> List[str]:
        """Return distinct raw standard labels that failed to map to a CPALMS code.

        Used by ``_build_alignment_data_quality_for_item`` when
        ``cause == "labels_not_mapped"`` so the empty-state card can list
        the offending labels (e.g. ``"Social Studies"`` on a Grade K Math
        assessment). Sorted alphabetically; capped at ``limit`` so a
        pathological item with hundreds of malformed labels doesn't bloat
        the payload.

        ``instructor`` (OPTIONAL) narrows the item set to the matching
        sections; NULL/empty = no filter (byte-identical).
        """
        sql = text(
            f"""
            SELECT DISTINCT standard
            FROM dim_question_data
            WHERE item_id IN (
                      SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                        AND {_DI_ITEM_INSTRUCTOR_MATCH_SQL}
                  )
              AND standard IS NOT NULL
              AND standard <> ''
              AND identifier IS NULL
            ORDER BY standard
            LIMIT :limit
            """
        )
        result = await self.session.execute(
            sql,
            {"subject_id": subject_id, "limit": int(limit), "instructor": instructor},
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
    async def get_assessment_meta(
        self, subject_id: str, instructor: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Compose the MERGED AssessmentMeta for one assessment (subject_id).

        The same-named assessment given to N sections is one report: the header
        lists the UNION of all section instructors + section names (legacy DAX
        ``CONCATENATEX(DISTINCT(dim_Item[Section_Instructors]))``), keyed on the
        section-agnostic subject_id. Representative item-level fields (name,
        type, school) come from the earliest section copy; assessment_date is
        the earliest across sections. first_access / latest_attempt span the
        whole section set.

        ``instructor`` (OPTIONAL) narrows the ``items`` CTE to the matching
        sections, so the merged header (section names + section instructors
        UNION) reflects only the selected instructors; NULL/empty = no filter
        (byte-identical to the full-merge header).
        """
        sql = text(
            f"""
            WITH items AS (
                SELECT item_id, school_id, item_name, item_type, subject_id,
                       section_name, section_instructors, assessment_date
                FROM dim_item
                WHERE subject_id = :subject_id
                  AND {_DI_ITEM_INSTRUCTOR_MATCH_SQL}
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
        result = await self.session.execute(
            sql, {"subject_id": subject_id, "instructor": instructor}
        )
        row = result.first()
        if not row:
            return None
        meta = _row_to_dict(row)

        # First/latest access from the fact table, across the (instructor-)
        # narrowed section set. NULL/empty :instructor = full section set.
        access_sql = text(
            f"""
            SELECT
                MIN(first_access)   AS first_access,
                MAX(latest_attempt) AS latest_attempt
            FROM fact_student_submission
            WHERE item_id IN (
                      SELECT item_id FROM dim_item WHERE subject_id = :subject_id
                        AND {_DI_ITEM_INSTRUCTOR_MATCH_SQL}
                  )
            """
        )
        access_row = (
            await self.session.execute(
                access_sql, {"subject_id": subject_id, "instructor": instructor}
            )
        ).first()
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
    # YTD Longitudinal matrix (PBIX ord 8 / 9 / 10) — cube_user_summary pivot.
    #
    # Legacy is a pure SUMMARIZECOLUMNS projection of ``cube_users_summary``
    # (our ``cube_user_summary``) with all aggregation done in the SSRS tablix
    # cells — NOT a re-derivation from the raw fact table. We mirror that:
    # ``cube_user_summary`` already carries every precomputed year-to-date
    # column the RDL reads (``user_possible_point``, ``user_overall_possible_point``,
    # ``*_by_overall_year``) and is one clean row per (user, item, question,
    # standard) with NO standard-alias fan-out, so a single scoped GROUP BY is
    # both the parity source and the fast path (kills the 1.6M-row fact scan +
    # DISTINCT-ON dedup + Python fan-in). RLS scopes the tenant via the
    # ``app.current_school_id`` GUC — no explicit school predicate.
    #
    # Column identity/header = the RAW ``cus.standards`` value (e.g.
    # ``ELA.7.C.3.1``), exactly as legacy groups by ``Fields!Standards.Value``
    # (NOT the shorter ``dim_standard.cpalms_standard``). Blank standards fold
    # into an "Other" column so per-standard sums still reconcile with the
    # year grand-total band.
    # ────────────────────────────────────────────────────────────────────
    async def get_ytd_cells_from_cus(
        self,
        session_filter: Optional[str],
        subject: Optional[str],
        grade: Optional[str],
        category: Optional[str],
        section: Optional[str],
    ) -> List[Dict[str, Any]]:
        """One-query YTD matrix source: per (instructor, student, standard) cell.

        Returns, per (section_instructors, user_uid, standard_label):
        ``points_received`` = SUM(total_score), ``points_possible`` =
        SUM(total_possible_point); plus the per-student constants
        ``user_possible_point`` (the per-standard "%" denominator — a
        contribution-to-year ratio, per the RDL) and
        ``user_overall_possible_point`` (the "Possible Points" column);
        ``tests_taken`` = COUNT(DISTINCT item_name) for the student;
        ``unit_names`` = the assessments that touched the standard (variant 3
        sub-header); and the scope-constant ``grand_score`` /
        ``grand_possible`` (``*_by_overall_year``) for the year grand-total band.
        """
        sql = text(
            f"""
            WITH scoped AS (
                SELECT
                    COALESCE(NULLIF(cus.section_instructors, ''), 'Unassigned')
                                                        AS section_instructors,
                    cus.user_uid,
                    cus.user_name,
                    cus.student_name_hash,
                    COALESCE(NULLIF(cus.standards, ''), 'Other')
                                                        AS standard_label,
                    cus.item_name,
                    cus.total_score,
                    cus.total_possible_point,
                    cus.user_possible_point,
                    cus.user_overall_possible_point,
                    cus.total_score_by_overall_year,
                    cus.total_possible_point_by_overall_year
                FROM cube_user_summary cus
                WHERE {_CUS_YTD_FILTER_SQL}
            ),
            grand AS (
                SELECT
                    MAX(total_score_by_overall_year)::float          AS grand_score,
                    MAX(total_possible_point_by_overall_year)::float AS grand_possible
                FROM scoped
            ),
            tests AS (
                SELECT user_uid, COUNT(DISTINCT item_name) AS tests_taken
                FROM scoped
                GROUP BY user_uid
            ),
            units AS (
                SELECT standard_label,
                       STRING_AGG(DISTINCT item_name, ' / ' ORDER BY item_name)
                                                        AS unit_names
                FROM scoped
                GROUP BY standard_label
            ),
            cells AS (
                SELECT
                    section_instructors,
                    user_uid,
                    MIN(user_name)                          AS user_name,
                    standard_label,
                    SUM(total_score)::float                 AS points_received,
                    SUM(total_possible_point)::float        AS points_possible,
                    MAX(user_possible_point)::float         AS user_possible_point,
                    MAX(user_overall_possible_point)::float AS user_overall_possible_point
                FROM scoped
                GROUP BY section_instructors, user_uid, standard_label
            )
            SELECT
                c.section_instructors,
                c.user_uid,
                c.user_name,
                c.standard_label,
                c.points_received,
                c.points_possible,
                c.user_possible_point,
                c.user_overall_possible_point,
                t.tests_taken,
                u.unit_names,
                g.grand_score,
                g.grand_possible
            FROM cells c
            JOIN tests t ON t.user_uid = c.user_uid
            LEFT JOIN units u ON u.standard_label = c.standard_label
            CROSS JOIN grand g
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

