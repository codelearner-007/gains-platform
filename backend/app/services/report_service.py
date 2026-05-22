"""Composes the report payloads from the cube_* / dim_* tables.

Each ``build_*`` method on :class:`ReportService` corresponds to one
endpoint in :mod:`app.api.v1.reports`:

* ``build_question_response_analysis``  → /reports/question-response-analysis
* ``build_standards_deep_dive``         → /reports/standards-deep-dive
* ``build_incorrect_answer_details``    → /reports/incorrect-answer-details
* ``build_year_to_date_performance``    → /reports/year-to-date-performance
* ``build_standard_summary``            → /reports/standard-summary
* ``build_strand_summary``              → /reports/strand-summary

The shapes returned here MUST match the TypeScript interfaces in
``frontend/src/lib/reports/types.ts``. Field names are intentionally
snake_case to mirror the API contract consumed by the Next.js pages.
"""

from __future__ import annotations

import html as _html
import logging
import re
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError
from app.repositories.cube_repository import CubeRepository
from app.repositories.dim_repository import DimRepository
from app.utils.coercion import safe_str, to_float, to_int
from app.schemas.reports import (
    AlignmentDataQuality,
    AlignmentDataQualityReport,
    AlignmentItemRow,
    AssessmentMeta,
    IadDistractorRow,
    IadKpis,
    IadQuestionContext,
    IadStudentAttempt,
    IncorrectAnswerDetailsPayload,
    IncorrectChoice,
    KPIs,
    QuestionOverall,
    QuestionResponseAnalysisPayload,
    RawQuestionOption,
    SddBandStandardRow,
    SddKpis,
    SddStandardRow,
    SddStrandRow,
    StandardSummaryFilters,
    StandardSummaryKpis,
    StandardSummaryPayload,
    StandardSummaryRollupRow,
    StandardSummaryStrandCount,
    StandardsDeepDivePayload,
    StrandSummaryBandRow,
    StrandSummaryFilters,
    StrandSummaryKpis,
    StrandSummaryPayload,
    StrandSummaryRollupRow,
    StrandSummaryStandardRow,
    Student,
    YearToDatePerformancePayload,
    YTDFilters,
    YTDGradeDistribution,
    YTDHeatmapCell,
    YTDKpis,
    YTDPeriodInfo,
    YTDSchoolInfo,
    YTDStudentScatter,
    YTDStudentSummary,
    YTDTimelinePoint,
)


_ALIGNMENT_REMEDIATION = (
    "Open this assessment in Schoology, edit each question, and use "
    '"Align Learning Objective" to attach the relevant standards. '
    "Re-ingest after the next Export Stats download."
)


def _classify_alignment(
    questions_total: int, questions_with_alignment: int
) -> str:
    """Map question-level coverage onto the alignment_status enum."""
    if questions_total == 0:
        return "missing"
    if questions_with_alignment == 0:
        return "missing"
    if questions_with_alignment == questions_total:
        return "full"
    return "partial"


def _classify_alignment_cause(
    questions_total: int,
    questions_with_alignment: int,
    nonempty_standards_count: int,
    distinct_unmatched_label_count: int,
) -> Optional[str]:
    """Refine the alignment status into a specific cause for UI messaging.

    Distinguishes the two flavours of "missing" empty state surfaced in the
    2026-05-19 RCA (``.hermes/report-parity/missing-alignment-2026-05-19``):

    * ``no_standards_in_source`` (Category A): the Schoology "Export Stats"
      CSV had zero ``Standards{N}`` columns, so every
      ``dim_question_data.standard`` is NULL. The fix is for the teacher
      to use "Align Learning Objective" in Schoology.
    * ``labels_not_mapped`` (Category B): the CSV contains labels but the
      exact-match join against ``dim_standard.schoology_standard`` failed —
      typically because the label is something like ``"Social Studies"``
      rather than a real CPALMS code. The fix is to either correct the
      label in Schoology or extend the standards dictionary.

    Returns one of:
      * ``"no_questions"``               — item has no question rows
      * ``"full_alignment"``             — every question aligned
      * ``"partial_teacher_alignment"``  — some aligned, some not
      * ``"no_standards_in_source"``     — Category A
      * ``"labels_not_mapped"``          — Category B
      * ``None``                         — counts inconsistent; caller
        should treat this as "cannot determine" and fall back to the
        generic empty state rather than fabricating a cause.
    """
    if questions_total == 0:
        return "no_questions"
    if questions_with_alignment == questions_total:
        return "full_alignment"
    if questions_with_alignment > 0:
        return "partial_teacher_alignment"
    # questions_with_alignment == 0 from here — split A vs B.
    if nonempty_standards_count == 0:
        return "no_standards_in_source"
    if distinct_unmatched_label_count > 0:
        return "labels_not_mapped"
    # Pathological: counts say "no aligned questions, no empty labels,
    # no unmatched labels" simultaneously. Don't fabricate a cause.
    return None

logger = logging.getLogger(__name__)

# Match HTML tags while *preserving* Schoology's `<https://…>` image-URL
# placeholders. The negative lookahead skips `<` followed by a URL scheme so
# the frontend's formatQuestionHtml can still convert it into an <img>.
_HTML_TAG_RE = re.compile(r"<(?!https?://)[^>]+>")


def _strip_html(s: Optional[str]) -> str:
    if not s:
        return ""
    return _HTML_TAG_RE.sub("", s).strip()


def _format_pct(v: float) -> str:
    return f"{v * 100:.1f}%"


# PBIX-mandated band thresholds (Performance Color* DAX measures): a strand
# or standard is "at target" at >=80%, "approaching" at 70–80%, and "needs
# attention" below 70%.
_BAND_HIGH_THRESHOLD = 0.8
_BAND_MID_THRESHOLD = 0.7


def _decode_html(s: str) -> str:
    """Decode HTML entities (e.g. ``&amp;`` → ``&``).

    Some dim_strand labels in the source data are pre-HTML-encoded (the
    PBIX tooling round-tripped them through HTML at some point). We render
    them as plain text in the React UI so we need to decode before
    serialising.
    """
    if not s:
        return ""
    return _html.unescape(s)


def _coerce_str_list(value: Any) -> list[str]:
    """Normalise a SQL string_agg / array_agg result into a clean str list.

    Postgres ``array_agg`` lands as a Python ``list``; legacy ``string_agg``
    lands as a comma-joined str. Both shapes appear across the codebase; this
    helper accepts either, drops empties, and preserves order.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v]
    return [s.strip() for s in str(value).split(",") if s.strip()]


class ReportService:
    """High-level reporting service that composes cube outputs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.cube = CubeRepository(session)
        self.dim = DimRepository(session)

    # ────────────────────────────────────────────────────────────────────
    # Shared helpers (used by QRA + SDD)
    # ────────────────────────────────────────────────────────────────────
    def _build_assessment_meta(
        self,
        meta_row: dict[str, Any],
        first_access: Any,
        latest_attempt: Any,
    ) -> AssessmentMeta:
        return AssessmentMeta(
            item_id=safe_str(meta_row.get("item_id")),
            item_name=safe_str(meta_row.get("item_name")),
            course_name=safe_str(meta_row.get("course_name")),
            course_code=safe_str(meta_row.get("course_code")),
            section_nid=safe_str(meta_row.get("section_nid")),
            section_name=safe_str(meta_row.get("section_name")),
            section_code=safe_str(meta_row.get("section_code")),
            section_instructors=safe_str(meta_row.get("section_instructors")),
            school_id=safe_str(meta_row.get("school_id")),
            school_name=safe_str(meta_row.get("school_name")),
            school_logo_url=meta_row.get("school_logo_url") or None,
            subject=safe_str(meta_row.get("subject")),
            grade=safe_str(meta_row.get("grade")),
            session=safe_str(meta_row.get("session")),
            assessment_type=safe_str(meta_row.get("assessment_type")),
            first_access=first_access.isoformat() if first_access else "",
            latest_attempt=latest_attempt.isoformat() if latest_attempt else "",
        )

    @staticmethod
    def _split_instructors(raw: str) -> list[str]:
        """Section_Instructors is a comma-separated list (PBIX semantics).

        Returns a deduped list preserving first-seen order. Whitespace
        stripped. Empty strings dropped.
        """
        if not raw:
            return []
        seen: dict[str, None] = {}
        for token in raw.split(","):
            t = token.strip()
            if t and t not in seen:
                seen[t] = None
        return list(seen)

    async def _compute_canonical_kpis_for_item(
        self, item_id: str
    ) -> dict[str, Any]:
        """Single source of truth for per-assessment KPI strip values.

        Returns a dict consumed by BOTH
        :meth:`build_question_response_analysis` and
        :meth:`build_standards_deep_dive` to guarantee they cannot
        diverge for the same item. See
        :meth:`CubeRepository.get_canonical_kpis_for_item` for the SQL
        and the FRESH-RCA at
        ``.hermes/report-parity/FRESH-RCA-2026-05-18-stable-formulas.md``
        §4 for the formula-to-DAX correspondence.

        Values returned:

        ``total_students`` — distinct student count from
        ``cube_school_summary``.

        ``total_questions`` — distinct question_id count from the
        per-(question, user) collapsed fact (matches legacy
        ``DISTINCTCOUNT(cqso.Question_No)``).

        ``total_standards`` — ``COUNT(DISTINCT standard)`` over
        ``dim_question_data`` for the item — counts the raw long-form
        ``standards_val`` strings (matches legacy
        ``DISTINCTCOUNT(cqso.Standards)`` which is a string column,
        NOT identifier UUID).

        ``grade_average`` / ``grade_min`` / ``grade_max`` — per-question
        grade averages computed by collapsing the standard-alias fan-out
        in the fact (DISTINCT ON ``(user_uid, question_id,
        position_number)``), averaging per-user pcts per question, then
        AVG/MIN/MAX across questions. Mirrors the legacy DAX
        ``AVERAGE / MAXX / MINX VALUES(Question_No)`` semantics.

        ``total_possible_point`` / ``total_score`` — pass-through from
        ``cube_school_summary``.
        """
        row = await self.cube.get_canonical_kpis_for_item(item_id) or {}
        return {
            "total_students": to_int(row.get("total_students")),
            "total_questions": to_int(row.get("total_questions")),
            "total_standards": to_int(row.get("total_standards")),
            "grade_average": to_float(row.get("grade_average")),
            "grade_min": to_float(row.get("grade_min")),
            "grade_max": to_float(row.get("grade_max")),
            "total_possible_point": to_float(row.get("total_possible_point")),
            "total_score": to_float(row.get("total_score")),
        }

    async def _build_alignment_data_quality_for_item(
        self, item_id: str
    ) -> AlignmentDataQuality:
        """Build the per-assessment AlignmentDataQuality block.

        Extracted from ``build_standards_deep_dive`` so the QRA composer
        can reuse it (so the QRA page can gate on
        ``alignment_status === "missing"`` the same way SDD does).

        Sets ``cause`` to disambiguate the two flavours of empty state
        (no Standards columns in CSV vs. labels that didn't map). When
        ``cause == "labels_not_mapped"`` we also surface up to five of the
        offending labels via ``unmatched_labels`` so the UI can render
        them inline (e.g. ``"Social Studies"`` on a Grade K Math item).
        """
        quality = await self.cube.get_alignment_quality_for_item(item_id)
        q_total = quality["questions_total"]
        q_aligned = quality["questions_with_alignment"]
        nonempty_count = quality["nonempty_standards_count"]
        unmatched_count = quality["distinct_unmatched_label_count"]

        cause = _classify_alignment_cause(
            q_total, q_aligned, nonempty_count, unmatched_count
        )
        unmatched_labels: Optional[list[str]] = None
        if cause == "labels_not_mapped":
            labels = await self.cube.get_unmatched_alignment_labels_for_item(
                item_id, limit=5
            )
            unmatched_labels = labels or None

        return AlignmentDataQuality(
            alignment_status=_classify_alignment(q_total, q_aligned),
            questions_total=q_total,
            questions_with_alignment=q_aligned,
            items_total=1,
            items_with_alignment=1 if q_aligned > 0 else 0,
            remediation_hint=_ALIGNMENT_REMEDIATION,
            cause=cause,
            unmatched_labels=unmatched_labels,
        )

    async def _build_strand_standard_rollups(
        self, item_id: str
    ) -> tuple[list[SddStrandRow], list[SddStandardRow]]:
        """Shared aggregation used by both SDD and QRA endpoints."""
        strand_rows = await self.cube.get_strand_rollup_for_item(item_id)
        standard_rows = await self.cube.get_standard_rollup_for_item(item_id)

        strands_rollup = [
            SddStrandRow(
                strand=_decode_html(safe_str(r.get("strand"))),
                num_standards=to_int(r.get("num_standards")),
                num_questions=to_int(r.get("num_questions")),
                grade_average=round(to_float(r.get("grade_average")), 6),
                grade_average_pct=_format_pct(to_float(r.get("grade_average"))),
            )
            for r in strand_rows
        ]
        standards_rollup = [
            SddStandardRow(
                schoology_standard=safe_str(r.get("schoology_standard")),
                strand=_decode_html(safe_str(r.get("strand"))),
                num_questions=to_int(r.get("num_questions")),
                grade_average=round(to_float(r.get("grade_average")), 6),
                grade_average_pct=_format_pct(to_float(r.get("grade_average"))),
            )
            for r in standard_rows
        ]
        return strands_rollup, standards_rollup

    @staticmethod
    def _synthesize_other_rollups(
        strands_rollup: list[SddStrandRow],
        standards_rollup: list[SddStandardRow],
        canon: dict,
    ) -> tuple[list[SddStrandRow], list[SddStandardRow], bool]:
        """Schoology / legacy-PBIX parity for unaligned assessments.

        Legacy DAX queries ``cube_question_summary`` which has its own
        ``NULL → 'Other'`` coercion (see ``Schoology_py.ipynb`` L1691-1700),
        so the PBIX renders a single ``Other`` strand and ``Other`` standard
        row at the assessment's overall grade_average when no question was
        tagged. Our warehouse rollup queries require a successful
        ``dim_question_data.standard → dim_standard`` join and therefore
        return empty for the same case. Re-inject the synthetic row here so
        QRA + SDD match Schoology screenshot-for-screenshot.

        Only fires when BOTH rollups are empty AND the item has questions.
        Partial-alignment items keep their real rollup (showing only the
        aligned subset) — that matches today's behavior and avoids
        double-counting unaligned questions twice.
        """
        if strands_rollup or standards_rollup:
            return strands_rollup, standards_rollup, False
        total_q = to_int(canon.get("total_questions"))
        if total_q <= 0:
            return strands_rollup, standards_rollup, False
        grade = to_float(canon.get("grade_average"))
        synthetic_strand = SddStrandRow(
            strand="Other",
            num_standards=1,
            num_questions=total_q,
            grade_average=round(grade, 6),
            grade_average_pct=_format_pct(grade),
        )
        synthetic_standard = SddStandardRow(
            schoology_standard="Other",
            strand="Other",
            num_questions=total_q,
            grade_average=round(grade, 6),
            grade_average_pct=_format_pct(grade),
        )
        return [synthetic_strand], [synthetic_standard], True

    # ────────────────────────────────────────────────────────────────────
    # Question-Response-Analysis (composed payload)
    # ────────────────────────────────────────────────────────────────────
    async def build_question_response_analysis(
        self, item_id: str
    ) -> QuestionResponseAnalysisPayload:
        meta_row = await self.cube.get_assessment_meta(item_id)
        if not meta_row:
            raise ResourceNotFoundError("Assessment", item_id)

        question_rows = await self.cube.get_questions_overall_for_item(item_id)
        incorrect_rows = await self.cube.get_incorrect_choices_for_item(item_id)
        student_rows = await self.cube.get_students_for_item(item_id)
        raw_options = await self.cube.get_raw_question_options_for_item(item_id)

        # ─── AssessmentMeta ────────────────────────────────────────────────
        first_access = meta_row.get("first_access")
        latest_attempt = meta_row.get("latest_attempt")

        assessment = self._build_assessment_meta(
            meta_row, first_access, latest_attempt
        )

        # ─── KPIs (canonical, legacy-DAX-equivalent) ──────────────────────
        # Both QRA and SDD compute KPIs through this helper so the strip
        # values can never disagree for the same item.
        canon = await self._compute_canonical_kpis_for_item(item_id)

        # ─── Strands & Standards rollups (per assessment) ─────────────────
        # Compute BEFORE building the KPI strip so the "Other" synthesis
        # (Schoology / legacy PBIX parity for unaligned assessments) can
        # bump ``canon["total_standards"]`` to 1 before the KPI is frozen.
        strands_rollup, standards_rollup = await self._build_strand_standard_rollups(
            item_id
        )
        strands_rollup, standards_rollup, synthesized_other = (
            self._synthesize_other_rollups(strands_rollup, standards_rollup, canon)
        )
        if synthesized_other:
            canon["total_standards"] = 1

        # Override per-question grade_average in the QRA question table
        # with the canonical per-user-collapsed value so the Lowest /
        # Highest KPIs and the per-question table report the same number
        # for the same question (fixes multi-select questions like Q12
        # where cube row-grain SUM/SUM gives 23.97% but per-student
        # collapsed gives 27.78%, matching the canonical KPI).
        canon_per_q = await self.cube.get_canonical_per_question_grades(item_id)
        canon_q_by_id = {
            safe_str(r.get("question_id")): to_float(r.get("grade_average"))
            for r in canon_per_q
        }
        for q in question_rows:
            qid = safe_str(q.get("question_id"))
            if qid in canon_q_by_id:
                ga = canon_q_by_id[qid]
                q["grade_average"] = ga
                q["percentage_incorrect"] = max(0.0, min(1.0, 1.0 - ga))

        # Tag question rows with the synthetic "Other" standard label so
        # the per-question "Standards" column matches Schoology when the
        # source CSV shipped no Standards{N} columns.
        if synthesized_other:
            for q in question_rows:
                q["standards"] = "Other"

        instructors = self._split_instructors(
            safe_str(meta_row.get("section_instructors"))
        )

        kpis = KPIs(
            instructors=instructors,
            grade_average=round(canon["grade_average"], 6),
            grade_average_pct=_format_pct(canon["grade_average"]),
            total_questions=canon["total_questions"],
            total_standards=canon["total_standards"],
            total_students=canon["total_students"],
            grade_min=round(canon["grade_min"], 6),
            grade_max=round(canon["grade_max"], 6),
            grade_min_pct=_format_pct(canon["grade_min"]),
            grade_max_pct=_format_pct(canon["grade_max"]),
            total_possible_point=round(canon["total_possible_point"], 4),
            total_score=round(canon["total_score"], 4),
        )

        # ─── Students ──────────────────────────────────────────────────────
        students = [
            Student(
                user_uid=safe_str(s.get("user_uid")),
                username=safe_str(s.get("username")),
                first_name=safe_str(s.get("first_name")),
                last_name=safe_str(s.get("last_name")),
                user_role_id=safe_str(s.get("user_role_id")),
            )
            for s in student_rows
        ]

        # ─── Questions ─────────────────────────────────────────────────────
        questions_overall = [
            QuestionOverall(
                question_id=safe_str(q.get("question_id")),
                question_no=safe_str(q.get("question_no")),
                position_number=safe_str(q.get("position_number")) or "n/a",
                question=_strip_html(safe_str(q.get("question"))),
                question_type=safe_str(q.get("question_type")),
                correct_answer=safe_str(q.get("correct_answer")),
                total_possible_point=round(to_float(q.get("total_possible_point")), 4),
                total_score=round(to_float(q.get("total_score")), 4),
                grade_average=round(to_float(q.get("grade_average")), 6),
                percentage_incorrect=round(to_float(q.get("percentage_incorrect")), 6),
                incorrect_choice_details=safe_str(q.get("incorrect_choice_details")),
                incorrect_details_name=safe_str(q.get("incorrect_details_name")),
                standards=safe_str(q.get("standards")),
                strand=safe_str(q.get("strand_raw")),
                # Strip raw HTML tags from description — Schoology /standards
                # API returns benchmark text with embedded markup
                # (`<ol>`, `<b>`, `<sup>`, etc.). Legacy PBIX strips this at
                # Power Query load (07_power_query.m:161-173); we mirror it
                # at the serializer so the QRA Description cell renders as
                # plain text.
                description=_strip_html(safe_str(q.get("description"))),
            )
            for q in question_rows
        ]

        # ─── Incorrect choices ────────────────────────────────────────────
        # Build student-name lookup keyed by user_uid for the "students" array.
        # cube_questionincorrectchoice_summary doesn't store names so we
        # leave the array empty (frontend will display from students_count).
        incorrect_choices = [
            IncorrectChoice(
                question_id=safe_str(c.get("question_id")),
                answer_submission=safe_str(c.get("answer_submission")),
                is_correct=bool(c.get("is_correct")),
                students_count=to_int(c.get("students_count")),
                attempt_count_for_choice=to_int(c.get("attempt_count_for_choice")),
                total_attempts_for_question=to_int(
                    c.get("total_attempts_for_question")
                ),
                share_of_attempts=round(to_float(c.get("share_of_attempts")), 4),
                total_score=round(to_float(c.get("total_score")), 4),
                total_possible_point=round(to_float(c.get("total_possible_point")), 4),
                grade_average=round(to_float(c.get("grade_average")), 4),
                students=[],
            )
            for c in incorrect_rows
        ]

        # ─── Raw question options ─────────────────────────────────────────
        raw_question_options = [
            RawQuestionOption(
                item_id=safe_str(r.get("item_id")),
                item_name=safe_str(r.get("item_name")),
                question_id=safe_str(r.get("question_id")),
                associated_question_id=safe_str(r.get("associated_question_id")),
                total_points=to_float(r.get("total_points")),
                question_type=safe_str(r.get("question_type")),
                question=_strip_html(safe_str(r.get("question"))),
                position_number=safe_str(r.get("position_number")),
                sub_question=safe_str(r.get("sub_question")),
                answer_option=safe_str(r.get("answer_option")),
                answer_breakdown_count=to_float(r.get("answer_breakdown_count")),
                answer_breakdown_pct=to_float(r.get("answer_breakdown_pct")),
                correct_answer=safe_str(r.get("correct_answer")),
                correctly_answered=to_float(r.get("correctly_answered")),
                most_points_earned=to_float(r.get("most_points_earned")),
                least_points_earned=to_float(r.get("least_points_earned")),
                average_points_earned=to_float(r.get("average_points_earned")),
            )
            for r in raw_options
        ]

        # Surface the standards-alignment block so the QRA page can render
        # the AlignmentEmptyState card when the assessment has no aligned
        # questions (mirrors SDD behaviour). Rollups already computed above
        # alongside the KPI synthesis.
        data_quality = await self._build_alignment_data_quality_for_item(item_id)

        return QuestionResponseAnalysisPayload(
            assessment=assessment,
            kpis=kpis,
            students=students,
            questions_overall=questions_overall,
            incorrect_choices=incorrect_choices,
            raw_question_options=raw_question_options,
            strands_rollup=strands_rollup,
            standards_rollup=standards_rollup,
            data_quality=data_quality,
        )

    # ────────────────────────────────────────────────────────────────────
    # Standards Deep Dive interactive (per-assessment, mirrors PBIX page #16)
    # ────────────────────────────────────────────────────────────────────
    async def build_standards_deep_dive(
        self, item_id: str
    ) -> StandardsDeepDivePayload:
        meta_row = await self.cube.get_assessment_meta(item_id)
        if not meta_row:
            raise ResourceNotFoundError("Assessment", item_id)

        first_access = meta_row.get("first_access")
        latest_attempt = meta_row.get("latest_attempt")
        assessment = self._build_assessment_meta(
            meta_row, first_access, latest_attempt
        )

        # ─── KPI strip values (canonical, shared with QRA) ────────────────
        # Both QRA and SDD compute KPIs through the same canonical helper
        # so they cannot disagree for the same item. See
        # ``_compute_canonical_kpis_for_item`` for the formula contract
        # (matches legacy PBIX DAX semantics for # Standards, Grade Avg,
        # Highest/Lowest at per-question grain).
        canon = await self._compute_canonical_kpis_for_item(item_id)

        # ─── Strand + standard rollups (shared with QRA) ──────────────────
        # Compute BEFORE building the KPI strip so the "Other" synthesis
        # (Schoology / legacy PBIX parity for unaligned assessments) can
        # bump ``canon["total_standards"]`` to 1 before the KPI is frozen.
        strands_rollup, standards_rollup = await self._build_strand_standard_rollups(
            item_id
        )
        strands_rollup, standards_rollup, synthesized_other = (
            self._synthesize_other_rollups(strands_rollup, standards_rollup, canon)
        )
        if synthesized_other:
            canon["total_standards"] = 1

        instructors = self._split_instructors(
            safe_str(meta_row.get("section_instructors"))
        )

        kpis = SddKpis(
            instructors=instructors,
            total_students=canon["total_students"],
            total_questions=canon["total_questions"],
            total_standards=canon["total_standards"],
            grade_average=round(canon["grade_average"], 6),
            grade_average_pct=_format_pct(canon["grade_average"]),
        )

        # ─── Performance bands (3 × 100% stacked bar charts) ──────────────
        # Per spec §4.4 (50_sdd_spec.md:143-184) each band panel renders
        # one bar per ``dim_standard.cPalms_Standard`` filtered to the
        # band; bucketing uses the same 70/80 thresholds the perf-color
        # DAX uses.
        band_rows = await self.cube.get_standard_bands_for_item(item_id)
        band_high: list[SddBandStandardRow] = []
        band_mid: list[SddBandStandardRow] = []
        band_low: list[SddBandStandardRow] = []
        for r in band_rows:
            schoology = safe_str(r.get("schoology_standard"))
            if not schoology:
                continue
            grade = to_float(r.get("grade_average"))
            row = SddBandStandardRow(
                schoology_standard=schoology,
                strand=_decode_html(safe_str(r.get("strand"))),
                num_questions=to_int(r.get("num_questions")),
                grade_average=round(grade, 6),
            )
            if grade >= _BAND_HIGH_THRESHOLD:
                band_high.append(row)
            elif grade >= _BAND_MID_THRESHOLD:
                band_mid.append(row)
            else:
                band_low.append(row)

        # When the rollup is synthesized "Other", the band-rows query also
        # returns empty (it filters on dim_standard joins). Inject one
        # synthetic band row at the overall grade_average so the SDD page
        # places "Other" in the right performance band — matches Schoology.
        if synthesized_other:
            grade = to_float(canon.get("grade_average"))
            other_band_row = SddBandStandardRow(
                schoology_standard="Other",
                strand="Other",
                num_questions=to_int(canon.get("total_questions")),
                grade_average=round(grade, 6),
            )
            if grade >= _BAND_HIGH_THRESHOLD:
                band_high.append(other_band_row)
            elif grade >= _BAND_MID_THRESHOLD:
                band_mid.append(other_band_row)
            else:
                band_low.append(other_band_row)

        data_quality = await self._build_alignment_data_quality_for_item(item_id)

        return StandardsDeepDivePayload(
            assessment=assessment,
            kpis=kpis,
            strands_rollup=strands_rollup,
            standards_rollup=standards_rollup,
            band_high=band_high,
            band_mid=band_mid,
            band_low=band_low,
            data_quality=data_quality,
        )

    # ────────────────────────────────────────────────────────────────────
    # Incorrect Answer Details (drill-through from QRA, per-question)
    # ────────────────────────────────────────────────────────────────────
    async def build_incorrect_answer_details(
        self, item_id: str, question_id: str
    ) -> IncorrectAnswerDetailsPayload:
        meta_row = await self.cube.get_assessment_meta(item_id)
        if not meta_row:
            raise ResourceNotFoundError("Assessment", item_id)

        question_row = await self.cube.get_question_overall(item_id, question_id)
        if not question_row:
            raise ResourceNotFoundError("Question", question_id)

        first_access = meta_row.get("first_access")
        latest_attempt = meta_row.get("latest_attempt")
        assessment = self._build_assessment_meta(
            meta_row, first_access, latest_attempt
        )

        # ─── Question context ──────────────────────────────────────────────
        grade_average = to_float(question_row.get("grade_average"))
        question_ctx = IadQuestionContext(
            question_id=safe_str(question_row.get("question_id")),
            question_no=safe_str(question_row.get("question_no")),
            position_number=safe_str(question_row.get("position_number")) or "n/a",
            question=_strip_html(safe_str(question_row.get("question"))),
            question_type=safe_str(question_row.get("question_type")),
            correct_answer=safe_str(question_row.get("correct_answer")),
            standards=safe_str(question_row.get("standards")),
            strand=safe_str(question_row.get("strand_raw")),
            description=safe_str(question_row.get("description")),
            grade_average=round(grade_average, 6),
            grade_average_pct=_format_pct(grade_average),
            total_possible_point=round(
                to_float(question_row.get("total_possible_point")), 4
            ),
            total_score=round(to_float(question_row.get("total_score")), 4),
        )

        # ─── Distractor breakdown ──────────────────────────────────────────
        distractor_rows = await self.cube.get_distractor_breakdown(
            item_id, question_id
        )
        distractors: list[IadDistractorRow] = [
            IadDistractorRow(
                answer_submission=safe_str(d.get("answer_submission")),
                students_count=to_int(d.get("students_count")),
                share_of_attempts=round(to_float(d.get("share_of_attempts")), 6),
                share_pct=_format_pct(to_float(d.get("share_of_attempts"))),
                is_correct=bool(d.get("is_correct")),
            )
            for d in distractor_rows
        ]

        # ─── Per-student attempts ──────────────────────────────────────────
        student_rows = await self.cube.get_per_student_attempts(item_id, question_id)
        student_attempts: list[IadStudentAttempt] = []
        for row in student_rows:
            la = row.get("latest_attempt")
            student_attempts.append(
                IadStudentAttempt(
                    user_uid=safe_str(row.get("user_uid")),
                    user_name=safe_str(row.get("user_name")),
                    answer_submission=safe_str(row.get("answer_submission")),
                    correct_answer=safe_str(row.get("correct_answer")),
                    is_correct=bool(row.get("is_correct")),
                    points_received=round(to_float(row.get("points_received")), 4),
                    points_possible=round(to_float(row.get("points_possible")), 4),
                    score_pct=round(to_float(row.get("score_pct")), 6),
                    latest_attempt=la.isoformat() if la else "",
                )
            )

        # ─── KPI strip (computed from the rolled-up data) ─────────────────
        total_attempts = sum(d.students_count for d in distractors)
        correct_count = sum(d.students_count for d in distractors if d.is_correct)
        incorrect_count = total_attempts - correct_count
        correct_pct = (
            correct_count / total_attempts if total_attempts > 0 else 0.0
        )
        incorrect_pct = 1.0 - correct_pct if total_attempts > 0 else 0.0

        wrong_choices = [d for d in distractors if not d.is_correct]
        wrong_choices_sorted = sorted(
            wrong_choices, key=lambda d: d.students_count, reverse=True
        )
        if wrong_choices_sorted:
            top = wrong_choices_sorted[0]
            top_share = (
                top.students_count / total_attempts if total_attempts > 0 else 0.0
            )
            top_wrong_answer = top.answer_submission
            top_wrong_count = top.students_count
            top_wrong_pct = _format_pct(top_share)
        else:
            top_wrong_answer = ""
            top_wrong_count = 0
            top_wrong_pct = _format_pct(0.0)

        kpis = IadKpis(
            total_attempts=total_attempts,
            correct_count=correct_count,
            incorrect_count=incorrect_count,
            correct_pct=_format_pct(correct_pct),
            incorrect_pct=_format_pct(incorrect_pct),
            distinct_answers=len(distractors),
            top_wrong_answer=top_wrong_answer,
            top_wrong_count=top_wrong_count,
            top_wrong_pct=top_wrong_pct,
        )

        return IncorrectAnswerDetailsPayload(
            assessment=assessment,
            question=question_ctx,
            kpis=kpis,
            distractors=distractors,
            student_attempts=student_attempts,
        )

    # ────────────────────────────────────────────────────────────────────
    # Year To Date - Longitudinal Report (cross-assessment, school-wide)
    # ────────────────────────────────────────────────────────────────────
    async def build_year_to_date_performance(
        self,
        filters: Optional["YTDFilters"] = None,
    ) -> YearToDatePerformancePayload:
        f = filters or YTDFilters()
        meta = await self.cube.get_ytd_school_meta(
            session_filter=f.session,
            subject=f.subject,
            grade=f.grade,
            category=f.category,
            section=f.section,
        ) or {}
        kpi_row = await self.cube.get_ytd_overall_kpis(
            session_filter=f.session,
            subject=f.subject,
            grade=f.grade,
            category=f.category,
            section=f.section,
        ) or {}
        timeline_rows = await self.cube.get_ytd_timeline(
            session_filter=f.session,
            subject=f.subject,
            grade=f.grade,
            category=f.category,
            section=f.section,
        )
        grade_dist_rows = await self.cube.get_ytd_grade_distribution(
            session_filter=f.session,
            subject=f.subject,
            grade=f.grade,
            category=f.category,
            section=f.section,
        )
        prog_rows = await self.cube.get_ytd_student_progression(
            session_filter=f.session,
            subject=f.subject,
            grade=f.grade,
            category=f.category,
            section=f.section,
        )
        heatmap_rows = await self.cube.get_ytd_strand_heatmap(
            session_filter=f.session,
            subject=f.subject,
            grade=f.grade,
            category=f.category,
            section=f.section,
        )

        date_from = meta.get("date_from")
        date_to = meta.get("date_to")
        school = YTDSchoolInfo(
            name=safe_str(meta.get("name")),
            logo_url=meta.get("logo_url") or None,
            current_session=safe_str(meta.get("current_session")),
            course_unit=safe_str(meta.get("course_unit")),
            assessment_types=_coerce_str_list(meta.get("assessment_types")),
        )
        period = YTDPeriodInfo(
            date_from=date_from.isoformat() if date_from else "",
            date_to=date_to.isoformat() if date_to else "",
        )

        timeline_by_date: dict[str, dict[str, Any]] = {}
        for row in timeline_rows:
            d = row.get("date")
            d_str = d.isoformat() if d else ""
            entry = timeline_by_date.setdefault(
                d_str,
                {
                    "date": d_str,
                    "overall_avg": to_float(row.get("overall_avg")),
                    "assessments_count": to_int(row.get("assessments_count")),
                    "per_subject": {},
                },
            )
            subject = safe_str(row.get("subject"))
            if subject:
                entry["per_subject"][subject] = round(
                    to_float(row.get("subject_avg")), 6
                )
        timeline = [
            YTDTimelinePoint(
                date=v["date"],
                overall_avg=round(v["overall_avg"], 6),
                per_subject=v["per_subject"],
                assessments_count=v["assessments_count"],
            )
            for v in sorted(timeline_by_date.values(), key=lambda r: r["date"])
        ]

        grade_distribution = [
            YTDGradeDistribution(
                date=row["date"].isoformat() if row.get("date") else "",
                band_high=to_int(row.get("band_high")),
                band_mid=to_int(row.get("band_mid")),
                band_low=to_int(row.get("band_low")),
            )
            for row in grade_dist_rows
        ]

        student_progression: list[YTDStudentScatter] = []
        improving = 0
        declining = 0
        for row in prog_rows:
            first = to_float(row.get("first_avg"))
            latest = to_float(row.get("latest_avg"))
            taken = to_int(row.get("assessments_taken"))
            delta = latest - first
            if taken < 2:
                continue
            if delta >= 0.05:
                improving += 1
            elif delta <= -0.05:
                declining += 1
            student_progression.append(
                YTDStudentScatter(
                    user_uid=safe_str(row.get("user_uid")),
                    user_name=safe_str(row.get("user_name")),
                    first_avg=round(first, 6),
                    latest_avg=round(latest, 6),
                    delta=round(delta, 6),
                    assessments_taken=taken,
                )
            )

        sorted_by_delta = sorted(
            student_progression, key=lambda s: s.delta, reverse=True
        )
        most_improved = [
            YTDStudentSummary(
                user_uid=s.user_uid, user_name=s.user_name, delta=s.delta
            )
            for s in sorted_by_delta[:3]
            if s.delta > 0
        ]
        biggest_drops = [
            YTDStudentSummary(
                user_uid=s.user_uid, user_name=s.user_name, delta=s.delta
            )
            for s in sorted(student_progression, key=lambda s: s.delta)[:3]
            if s.delta < 0
        ]

        overall_avg = to_float(kpi_row.get("overall_avg"))
        kpis = YTDKpis(
            total_questions=to_int(kpi_row.get("total_questions")),
            total_students=to_int(kpi_row.get("total_students")),
            total_points_earned=round(
                to_float(kpi_row.get("total_points_earned")), 2
            ),
            total_points_possible=round(
                to_float(kpi_row.get("total_points_possible")), 2
            ),
            overall_avg_pct=_format_pct(overall_avg),
            total_assessments=to_int(kpi_row.get("total_assessments")),
            students_improving=improving,
            students_declining=declining,
            most_improved=most_improved,
            biggest_drops=biggest_drops,
        )

        strand_heatmap = [
            YTDHeatmapCell(
                strand=safe_str(row.get("strand")),
                date=row["date"].isoformat() if row.get("date") else "",
                grade_average=round(to_float(row.get("grade_average")), 6),
            )
            for row in heatmap_rows
        ]

        return YearToDatePerformancePayload(
            school=school,
            period=period,
            kpis=kpis,
            timeline=timeline,
            grade_distribution=grade_distribution,
            student_progression=student_progression,
            strand_heatmap=strand_heatmap,
        )

    # ────────────────────────────────────────────────────────────────────
    # Standard Summary (school-wide, per-cPalms_Standard grain)
    # ────────────────────────────────────────────────────────────────────
    async def build_standard_summary(
        self, filters: StandardSummaryFilters
    ) -> StandardSummaryPayload:
        meta = await self.cube.get_school_wide_meta() or {}
        rows = await self.cube.get_school_standard_rollup(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
            section=filters.section,
        )
        total_students = await self.cube.get_school_total_students(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
            section=filters.section,
        )

        standards: list[StandardSummaryRollupRow] = []
        strand_counts_acc: dict[str, dict[str, Any]] = {}
        at_target = 0
        for row in rows:
            schoology = safe_str(row.get("schoology_standard"))
            if not schoology:
                continue
            grade_avg = to_float(row.get("grade_average"))
            num_q = to_int(row.get("num_questions"))
            num_a = to_int(row.get("num_assessments"))
            strand = _decode_html(safe_str(row.get("strand")))
            description = _strip_html(safe_str(row.get("description")))
            last_change = row.get("last_change_date_time")
            grades_list = _coerce_str_list(row.get("grades"))
            standards.append(
                StandardSummaryRollupRow(
                    schoology_standard=schoology,
                    strand=strand,
                    cluster=safe_str(row.get("cluster")),
                    cognitive_complexity=safe_str(row.get("cognitive_complexity")),
                    description=description,
                    subject=safe_str(row.get("subject")),
                    grades=grades_list,
                    num_questions=num_q,
                    num_assessments=num_a,
                    grade_average=round(grade_avg, 6),
                    grade_average_pct=_format_pct(grade_avg),
                    last_change_date_time=(
                        last_change.isoformat() if last_change else None
                    ),
                )
            )
            if grade_avg >= _BAND_HIGH_THRESHOLD:
                at_target += 1
            bucket = strand_counts_acc.setdefault(
                strand,
                {
                    "strand": strand,
                    "num_standards": 0,
                    "num_questions": 0,
                    "grade_sum": 0.0,
                    "rows": 0,
                },
            )
            bucket["num_standards"] += 1
            bucket["num_questions"] += num_q
            bucket["grade_sum"] += grade_avg
            bucket["rows"] += 1

        total_standards = len(standards)
        at_target_pct = at_target / total_standards if total_standards else 0.0

        strand_counts = sorted(
            (
                StandardSummaryStrandCount(
                    strand=b["strand"],
                    num_standards=int(b["num_standards"]),
                    num_questions=int(b["num_questions"]),
                    grade_average=round(b["grade_sum"] / b["rows"], 6)
                    if b["rows"]
                    else 0.0,
                )
                for b in strand_counts_acc.values()
                if b["strand"]
            ),
            key=lambda r: r.num_standards,
            reverse=True,
        )

        # Sequential — AsyncSession is not safe for concurrent statements
        # on the same connection.
        total_questions_cqso = await self.cube.get_school_total_questions(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
            section=filters.section,
        )
        grade_average = await self.cube.get_school_overall_grade_average(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
            section=filters.section,
        )

        kpis = StandardSummaryKpis(
            total_standards=total_standards,
            total_questions=total_questions_cqso,
            total_students=total_students,
            at_target_pct=round(at_target_pct, 6),
            at_target_pct_str=_format_pct(at_target_pct),
            grade_average=round(grade_average, 6),
            grade_average_pct=_format_pct(grade_average),
        )

        school = YTDSchoolInfo(
            name=safe_str(meta.get("name")),
            logo_url=meta.get("logo_url") or None,
            current_session=safe_str(meta.get("current_session")),
        )

        quality = await self.cube.get_school_alignment_quality(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
            section=filters.section,
        )
        data_quality = AlignmentDataQuality(
            alignment_status=_classify_alignment(
                quality["questions_total"], quality["questions_with_alignment"]
            ),
            questions_total=quality["questions_total"],
            questions_with_alignment=quality["questions_with_alignment"],
            items_total=quality["items_total"],
            items_with_alignment=quality["items_with_alignment"],
            remediation_hint=_ALIGNMENT_REMEDIATION,
        )

        return StandardSummaryPayload(
            school=school,
            filters_applied=filters,
            kpis=kpis,
            standards=standards,
            strand_counts=strand_counts,
            data_quality=data_quality,
        )

    # ────────────────────────────────────────────────────────────────────
    # Strand Summary (school-wide, per-Strand grain)
    # ────────────────────────────────────────────────────────────────────
    async def build_strand_summary(
        self, filters: StrandSummaryFilters
    ) -> StrandSummaryPayload:
        meta = await self.cube.get_school_wide_meta() or {}
        strand_rows = await self.cube.get_school_strand_rollup(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
            section=filters.section,
        )
        std_rows = await self.cube.get_school_standard_rollup(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
            section=filters.section,
            strand=filters.strand,
        )
        total_students = await self.cube.get_school_total_students(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
            section=filters.section,
        )

        strands_rollup: list[StrandSummaryRollupRow] = []
        band_high: list[StrandSummaryBandRow] = []
        band_mid: list[StrandSummaryBandRow] = []
        band_low: list[StrandSummaryBandRow] = []
        worst_strand = ""
        worst_grade = 1.5  # any value beats this on the first iteration
        for row in strand_rows:
            strand_name = _decode_html(safe_str(row.get("strand")))
            grade_avg = to_float(row.get("grade_average"))
            num_questions = to_int(row.get("num_questions"))
            num_standards = to_int(row.get("num_standards"))
            subjects_raw = row.get("subjects")
            subjects = [
                _decode_html(safe_str(s))
                for s in (subjects_raw if isinstance(subjects_raw, list) else [])
                if s
            ]
            strands_rollup.append(
                StrandSummaryRollupRow(
                    strand=strand_name,
                    num_standards=num_standards,
                    num_questions=num_questions,
                    num_assessments=to_int(row.get("num_assessments")),
                    grade_average=round(grade_avg, 6),
                    grade_average_pct=_format_pct(grade_avg),
                    incorrect_pct=round(max(0.0, 1.0 - grade_avg), 6),
                    subjects=subjects,
                )
            )
            band_row = StrandSummaryBandRow(
                strand=strand_name,
                num_standards=num_standards,
                num_questions=num_questions,
                grade_average=round(grade_avg, 6),
            )
            if grade_avg >= _BAND_HIGH_THRESHOLD:
                band_high.append(band_row)
            elif grade_avg >= _BAND_MID_THRESHOLD:
                band_mid.append(band_row)
            else:
                band_low.append(band_row)
            if num_questions > 0 and grade_avg < worst_grade:
                worst_grade = grade_avg
                worst_strand = strand_name

        standards_rollup: list[StrandSummaryStandardRow] = [
            StrandSummaryStandardRow(
                strand=_decode_html(safe_str(r.get("strand"))),
                schoology_standard=safe_str(r.get("schoology_standard")),
                cluster=safe_str(r.get("cluster")),
                num_questions=to_int(r.get("num_questions")),
                num_assessments=to_int(r.get("num_assessments")),
                grade_average=round(to_float(r.get("grade_average")), 6),
                grade_average_pct=_format_pct(to_float(r.get("grade_average"))),
            )
            for r in std_rows
            if safe_str(r.get("schoology_standard"))
        ]

        total_strands = len(strands_rollup)
        total_standards = sum(s.num_standards for s in strands_rollup)
        # Mirrors PBIX `Total Question = DISTINCTCOUNT(cqso[Question_No])` so
        # the KPI agrees across YTD / Standard / Strand Summary.
        total_questions = await self.cube.get_school_total_questions(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
            section=filters.section,
        )
        total_assessments = await self.cube.get_school_total_assessments(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
            section=filters.section,
        )
        # Mirrors PBIX `Grade_Average_Standard_Measure = AVERAGE(cqso[Grade_Average])`
        # rather than mean-of-per-strand-means (which would weight strands equally).
        grade_average = await self.cube.get_school_overall_grade_average(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
            section=filters.section,
        )

        kpis = StrandSummaryKpis(
            total_strands=total_strands,
            total_standards=total_standards,
            total_questions=total_questions,
            total_assessments=total_assessments,
            total_students=total_students,
            grade_average=round(grade_average, 6),
            grade_average_pct=_format_pct(grade_average),
            worst_strand=worst_strand,
            worst_strand_pct=_format_pct(worst_grade) if worst_strand else "—",
        )

        data_refreshed_at = (
            await self.cube.get_school_data_refreshed_at()
        ) or ""

        school = YTDSchoolInfo(
            name=safe_str(meta.get("name")),
            logo_url=meta.get("logo_url") or None,
            current_session=safe_str(meta.get("current_session")),
        )

        quality = await self.cube.get_school_alignment_quality(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
            section=filters.section,
        )
        data_quality = AlignmentDataQuality(
            alignment_status=_classify_alignment(
                quality["questions_total"], quality["questions_with_alignment"]
            ),
            questions_total=quality["questions_total"],
            questions_with_alignment=quality["questions_with_alignment"],
            items_total=quality["items_total"],
            items_with_alignment=quality["items_with_alignment"],
            remediation_hint=_ALIGNMENT_REMEDIATION,
        )

        return StrandSummaryPayload(
            school=school,
            filters_applied=filters,
            kpis=kpis,
            strands_rollup=strands_rollup,
            standards_rollup=standards_rollup,
            band_high=band_high,
            band_mid=band_mid,
            band_low=band_low,
            data_quality=data_quality,
            data_refreshed_at=data_refreshed_at,
        )

    # ────────────────────────────────────────────────────────────────────
    # Data Quality — Standards alignment coverage (admin)
    # ────────────────────────────────────────────────────────────────────
    async def build_alignment_data_quality(self) -> AlignmentDataQualityReport:
        """Tenant-scoped report listing alignment coverage per assessment."""
        meta = await self.cube.get_school_wide_meta() or {}
        rows = await self.cube.list_alignment_quality_by_item()

        items: list[AlignmentItemRow] = []
        items_total = 0
        items_full = 0
        items_partial = 0
        items_missing = 0
        for r in rows:
            qs_total = to_int(r.get("questions_total"))
            qs_aligned = to_int(r.get("questions_with_alignment"))
            status = _classify_alignment(qs_total, qs_aligned)
            pct = (qs_aligned / qs_total) if qs_total else 0.0
            items.append(
                AlignmentItemRow(
                    item_id=safe_str(r.get("item_id")),
                    item_name=safe_str(r.get("item_name")),
                    item_type=safe_str(r.get("item_type")) or None,
                    subject=safe_str(r.get("subject")) or None,
                    grade=safe_str(r.get("grade")) or None,
                    questions_total=qs_total,
                    questions_with_alignment=qs_aligned,
                    pct_aligned=round(pct, 6),
                    alignment_status=status,
                )
            )
            items_total += 1
            if status == "full":
                items_full += 1
            elif status == "partial":
                items_partial += 1
            else:
                items_missing += 1

        return AlignmentDataQualityReport(
            school_id=safe_str(meta.get("school_id")),
            school_name=safe_str(meta.get("name")),
            items_total=items_total,
            items_with_alignment=items_full + items_partial,
            items_missing_alignment=items_missing,
            items_partial_alignment=items_partial,
            items=items,
        )
