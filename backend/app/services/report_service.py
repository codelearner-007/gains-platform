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
    KPIs,
    PaginatedKpis,
    PaginatedQuestionRow,
    QraByStandardTeacherPayload,
    QraByTeacherPayload,
    QraPaginatedPayload,
    QraStandardGroup,
    QraStandardTeacherGroup,
    QraTeacherGroup,
    QsmQuestionColumn,
    QuestionOverall,
    QspGrandTotal,
    QspStandardBand,
    QspStudentRow,
    QspTeacherGroup,
    QuestionResponseAnalysisPayload,
    QuestionSummaryPointsPayload,
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
    YearToDatePerformancePayload,
    YtdCell,
    YTDFilters,
    YtdGrandTotal,
    YTDSchoolInfo,
    YtdStandardColumn,
    YtdStandardTotal,
    YtdStudentRow,
    YtdTeacherGroup,
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


def _round_opt(v: Any) -> Optional[float]:
    """Round to 6 dp, preserving ``None`` (an unassessed/BLANK grade).

    Unlike ``to_float`` this does NOT coerce ``None`` → 0.0, so a missing
    grade stays blank end-to-end (MASTER_PLAN §6, Decision 3).
    """
    if v is None:
        return None
    return round(to_float(v), 6)


def _format_pct_opt(v: Any) -> str:
    """Percent string for an optional grade; empty string when ``None``."""
    if v is None:
        return ""
    return _format_pct(to_float(v))


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
            assessment_date=(
                meta_row.get("assessment_date").isoformat()
                if meta_row.get("assessment_date")
                else None
            ),
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
                grade_average=_round_opt(r.get("grade_average")),
                grade_average_pct=_format_pct_opt(r.get("grade_average")),
            )
            for r in strand_rows
        ]
        standards_rollup = [
            SddStandardRow(
                schoology_standard=safe_str(r.get("schoology_standard")),
                strand=_decode_html(safe_str(r.get("strand"))),
                num_questions=to_int(r.get("num_questions")),
                grade_average=_round_opt(r.get("grade_average")),
                grade_average_pct=_format_pct_opt(r.get("grade_average")),
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
                standard_raw=safe_str(q.get("strand_raw")),
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

        # Surface the standards-alignment block so the QRA page can render
        # the AlignmentEmptyState card when the assessment has no aligned
        # questions (mirrors SDD behaviour). Rollups already computed above
        # alongside the KPI synthesis.
        data_quality = await self._build_alignment_data_quality_for_item(item_id)

        return QuestionResponseAnalysisPayload(
            assessment=assessment,
            kpis=kpis,
            questions_overall=questions_overall,
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

        # ─── KPI strip ─────────────────────────────────────────────────────
        # Prefer the PER-STUDENT grain (one row per student, is_correct =
        # points_received >= points_possible at the student level) over the
        # per-collapsed-answer distractor rows. The distractor breakdown
        # splits multi-blank / partial-credit questions across positions, so
        # summing its rows both inflates total_attempts (27 students × N
        # blanks) and never marks any collapsed choice is_correct (no single
        # choice reaches full credit) — yielding a spurious "0 correct / 0%".
        # The per-student grain agrees with the per-student table on the same
        # page (e.g. 19/27 correct = 70.4%).
        #
        # Cube-only (parquet-loaded) schools have NO per-student rows, so we
        # fall back to the distractor-based derivation, which the audit
        # verified renders correctly from the cube for single-answer
        # questions (e.g. Brightview 7566518630/2074630261 = 19/22 = 86.4%).
        if student_attempts:
            distinct_students = {s.user_uid for s in student_attempts}
            total_attempts = len(distinct_students)
            correct_students = {
                s.user_uid for s in student_attempts if s.is_correct
            }
            correct_count = len(correct_students)
        else:
            total_attempts = sum(d.students_count for d in distractors)
            correct_count = sum(
                d.students_count for d in distractors if d.is_correct
            )
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

        # `Total Incorrect Choices` =
        #   CALCULATE(DISTINCTCOUNT('fact_student_submission'[Answer_Submission]))
        # — legacy DAX at 04_dax_measures.csv:405. The DISTINCTCOUNT spans
        # ALL distinct answer submissions for the question, INCLUDING the
        # correct answer (the measure has no [Score]=0 filter), so it equals
        # the count of distinct distractor rows, not just the wrong ones.
        total_incorrect_choices = len(distractors)

        kpis = IadKpis(
            total_attempts=total_attempts,
            correct_count=correct_count,
            incorrect_count=incorrect_count,
            correct_pct=_format_pct(correct_pct),
            incorrect_pct=_format_pct(incorrect_pct),
            distinct_answers=len(distractors),
            total_incorrect_choices=total_incorrect_choices,
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
        """Legacy YTD Longitudinal paginated matrix (PBIX ord 8/9/10).

        Rows are grouped Classroom Instructor → Student; columns are the
        standards assessed YTD for the (session, grade, subject,
        assessment_type) scope. Every cell + subtotal + grand total is
        POINTS-based: Score = SUM(points_received)/SUM(points_possible) at
        that grain (matching the legacy SSRS PDFs, e.g. grand 36/45 = 80%).
        """
        f = filters or YTDFilters()
        meta = await self.cube.get_ytd_school_meta(
            session_filter=f.session,
            subject=f.subject,
            grade=f.grade,
            category=f.category,
            section=f.section,
        ) or {}
        cell_rows = await self.cube.get_ytd_longitudinal_cells(
            f.session, f.subject, f.grade, f.category
        )
        tests_rows = await self.cube.get_ytd_longitudinal_tests_taken(
            f.session, f.subject, f.grade, f.category
        )
        unit_rows = await self.cube.get_ytd_longitudinal_standard_units(
            f.session, f.subject, f.grade, f.category
        )

        school = YTDSchoolInfo(
            name=safe_str(meta.get("name")),
            logo_url=meta.get("logo_url") or None,
            current_session=safe_str(meta.get("current_session")),
            course_unit=safe_str(meta.get("course_unit")),
            assessment_types=_coerce_str_list(meta.get("assessment_types")),
        )

        tests_taken_by_user: dict[str, int] = {
            safe_str(r.get("user_uid")): to_int(r.get("tests_taken"))
            for r in tests_rows
        }
        unit_names_by_std: dict[str, str] = {
            safe_str(r.get("standard_label")): safe_str(r.get("unit_names"))
            for r in unit_rows
        }

        # ── Standard columns ─────────────────────────────────────────────────
        # Legacy SSRS orders the standard columns ASCENDING by the standard's
        # overall Score% (lowest-scoring standard first) — the grand-total
        # "Score %" row in the legacy PDF reads left→right 48%, 61%, 65%, …,
        # 96%. Ties break alphabetically by label for determinism.
        std_meta: dict[str, str] = {}  # label → schoology code
        std_totals: dict[str, list[float]] = {}  # label → [recv, poss]
        for r in cell_rows:
            label = safe_str(r.get("standard_label"))
            if not label:
                continue
            if label not in std_meta:
                std_meta[label] = safe_str(r.get("schoology_standard")) or label
            agg = std_totals.setdefault(label, [0.0, 0.0])
            agg[0] += to_float(r.get("points_received"))
            agg[1] += to_float(r.get("points_possible"))

        def _std_score(label: str) -> float:
            recv, poss = std_totals.get(label, [0.0, 0.0])
            return round(recv / poss, 6) if poss > 0 else 0.0

        ordered_labels = sorted(std_meta, key=lambda lab: (_std_score(lab), lab))
        standards = [
            YtdStandardColumn(
                standard_label=label,
                schoology_standard=std_meta[label],
                unit_names=unit_names_by_std.get(label, ""),
            )
            for label in ordered_labels
        ]

        # ── Teacher → student → (standard) accumulation ─────────────────────
        # teacher → user_uid → {name, cells: {label: [recv, poss]}}
        teachers: dict[str, dict[str, dict[str, Any]]] = {}
        for r in cell_rows:
            teacher = safe_str(r.get("section_instructors")) or "Unassigned"
            uid = safe_str(r.get("user_uid"))
            label = safe_str(r.get("standard_label"))
            recv = to_float(r.get("points_received"))
            poss = to_float(r.get("points_possible"))
            student = teachers.setdefault(teacher, {}).setdefault(
                uid,
                {"user_name": safe_str(r.get("user_name")), "cells": {}},
            )
            cur = student["cells"].setdefault(label, [0.0, 0.0])
            cur[0] += recv
            cur[1] += poss

        def _pct(recv: float, poss: float) -> float:
            return round(recv / poss, 6) if poss > 0 else 0.0

        teacher_groups: list[YtdTeacherGroup] = []
        grand_recv = 0.0
        grand_poss = 0.0
        grand_std: dict[str, list[float]] = {}

        # Legacy SSRS orders the Classroom Instructor groups ASCENDING by the
        # teacher's overall Score% (lowest-scoring teacher first) — the legacy
        # PDF runs 80.9% → 81.8% → 84.7%. Ties break alphabetically by name.
        def _teacher_score(name: str) -> float:
            recv = sum(v[0] for s in teachers[name].values() for v in s["cells"].values())
            poss = sum(v[1] for s in teachers[name].values() for v in s["cells"].values())
            return round(recv / poss, 6) if poss > 0 else 0.0

        for teacher in sorted(teachers, key=lambda t: (_teacher_score(t), t)):
            students_list: list[YtdStudentRow] = []
            t_recv = 0.0
            t_poss = 0.0
            t_std: dict[str, list[float]] = {}
            for uid, s in teachers[teacher].items():
                s_recv = sum(v[0] for v in s["cells"].values())
                s_poss = sum(v[1] for v in s["cells"].values())
                cells = {
                    label: YtdCell(
                        points_received=round(v[0], 4),
                        points_possible=round(v[1], 4),
                        score_pct=_pct(v[0], v[1]),
                    )
                    for label, v in s["cells"].items()
                }
                students_list.append(
                    YtdStudentRow(
                        user_uid=uid,
                        user_name=s["user_name"],
                        score_pct=_pct(s_recv, s_poss),
                        tests_taken=tests_taken_by_user.get(uid, 0),
                        points_received=round(s_recv, 4),
                        points_possible=round(s_poss, 4),
                        cells=cells,
                    )
                )
                t_recv += s_recv
                t_poss += s_poss
                for label, v in s["cells"].items():
                    agg = t_std.setdefault(label, [0.0, 0.0])
                    agg[0] += v[0]
                    agg[1] += v[1]
                    g = grand_std.setdefault(label, [0.0, 0.0])
                    g[0] += v[0]
                    g[1] += v[1]
            # Legacy sorts students ascending by overall Score %.
            students_list.sort(key=lambda x: x.score_pct)
            teacher_groups.append(
                YtdTeacherGroup(
                    section_instructor=teacher,
                    teacher_score_pct=_pct(t_recv, t_poss),
                    students=students_list,
                    standard_subtotals={
                        label: YtdStandardTotal(
                            points_received=round(v[0], 4),
                            points_possible=round(v[1], 4),
                            score_pct=_pct(v[0], v[1]),
                        )
                        for label, v in t_std.items()
                    },
                )
            )
            grand_recv += t_recv
            grand_poss += t_poss

        grand_total = YtdGrandTotal(
            points_received=round(grand_recv, 4),
            points_possible=round(grand_poss, 4),
            score_pct=_pct(grand_recv, grand_poss),
            standard_totals={
                label: YtdStandardTotal(
                    points_received=round(v[0], 4),
                    points_possible=round(v[1], 4),
                    score_pct=_pct(v[0], v[1]),
                )
                for label, v in grand_std.items()
            },
        )

        return YearToDatePerformancePayload(
            school=school,
            subject=safe_str(f.subject),
            grade=safe_str(f.grade),
            session=safe_str(f.session) or safe_str(meta.get("current_session")),
            assessment_type=safe_str(f.category),
            standards=standards,
            teacher_groups=teacher_groups,
            grand_total=grand_total,
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
                    cpalms_standard=safe_str(row.get("cpalms_standard"))
                    or schoology,
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
        self, filters: StrandSummaryFilters, strands_only: bool = False
    ) -> StrandSummaryPayload:
        """Build the Strand Summary payload.

        ``strands_only`` is the dashboard's lean path: it consumes ONLY
        ``strands_rollup``, so we skip the per-standard rollup (a full, expensive
        ``get_school_standard_rollup`` that the dashboard already pays for via
        Standard Summary) plus the school-wide KPI / alignment / refresh queries
        the dashboard never reads — 9 round-trips collapse to 2. The Strand
        Summary report page calls without the flag (full payload, unchanged).
        """
        meta = await self.cube.get_school_wide_meta() or {}
        strand_rows = await self.cube.get_school_strand_rollup(
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

        total_strands = len(strands_rollup)
        total_standards = sum(s.num_standards for s in strands_rollup)

        school = YTDSchoolInfo(
            name=safe_str(meta.get("name")),
            logo_url=meta.get("logo_url") or None,
            current_session=safe_str(meta.get("current_session")),
        )

        # Dashboard lean path: only strands_rollup is consumed, so skip the
        # per-standard rollup + the school-wide KPI / alignment / refresh queries.
        if strands_only:
            return StrandSummaryPayload(
                school=school,
                filters_applied=filters,
                kpis=StrandSummaryKpis(
                    total_strands=total_strands,
                    total_standards=total_standards,
                    total_questions=0,
                    total_assessments=0,
                    total_students=0,
                    grade_average=0.0,
                    grade_average_pct=_format_pct(0.0),
                    worst_strand=worst_strand,
                    worst_strand_pct=_format_pct(worst_grade) if worst_strand else "—",
                ),
                strands_rollup=strands_rollup,
                standards_rollup=[],
                band_high=band_high,
                band_mid=band_mid,
                band_low=band_low,
                data_quality=None,
                data_refreshed_at="",
            )

        std_rows = await self.cube.get_school_standard_rollup(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
            section=filters.section,
            strand=filters.strand,
        )
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

        total_students = await self.cube.get_school_total_students(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
            section=filters.section,
        )
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

    # ────────────────────────────────────────────────────────────────────
    # Paginated reports (PBIX ord 6/7/16, 11, 12, 13)
    # ────────────────────────────────────────────────────────────────────
    async def _build_paginated_kpis(self, item_id: str) -> PaginatedKpis:
        canon = await self._compute_canonical_kpis_for_item(item_id)
        return PaginatedKpis(
            total_questions=canon["total_questions"],
            total_students=canon["total_students"],
            score=round(canon["total_score"], 4),
            total_possible_point=round(canon["total_possible_point"], 4),
            grade_average=round(canon["grade_average"], 6),
            grade_average_pct=_format_pct(canon["grade_average"]),
        )

    async def build_question_summary_matrix_points(
        self, item_id: str
    ) -> QuestionSummaryPointsPayload:
        """Partial-credit QSR matrix — single source of truth for the web/JSON
        matrix AND the xlsx export (legacy SSRS parity).

        Reproduces the legacy .xlsx / PDF exactly: each cell is
        ``points_received`` (possibly fractional), "Possible Points" is
        SUM(points_possible), "# Correct Answers" is SUM(points_received), and
        every Score% (overall, per-band, per-question, per-teacher, grand) is
        SUM(received)/SUM(possible). Verified cell-for-cell against the legacy
        Chapter 9 Test 8359960427 xlsx (grand 318/486 = 65.4%, which equals the
        grade-average KPI). Both the web endpoint and the xlsx export consume
        this payload so they cannot diverge.
        """
        meta_row = await self.cube.get_assessment_meta(item_id)
        if not meta_row:
            raise ResourceNotFoundError("Assessment", item_id)
        assessment = self._build_assessment_meta(
            meta_row, meta_row.get("first_access"), meta_row.get("latest_attempt")
        )
        kpis = await self._build_paginated_kpis(item_id)

        rows = await self.cube.get_question_summary_matrix_rows(item_id)

        # ── Cube-only (parquet-loaded) schools have ZERO fact rows, so the
        # per-student matrix body is empty. Without a fallback the grand
        # total renders 0/0/0% next to a correct cube KPI strip — a
        # self-contradictory page. Derive the grand total from the cube
        # (SUM per-question possible/score, == the KPI strip) and flag the
        # per-student detail as unavailable so the frontend can show an
        # explicit empty-state instead of zeros.
        if not rows:
            cube_total = await self.cube.get_cube_grand_total_for_item(item_id)
            grand_poss = to_float((cube_total or {}).get("total_possible_point"))
            grand_recv = to_float((cube_total or {}).get("total_score"))
            grand_total = QspGrandTotal(
                possible_points=round(grand_poss, 4),
                correct_count=round(grand_recv, 4),
                score_pct=round(grand_recv / grand_poss, 6)
                if grand_poss > 0
                else 0.0,
                per_question_possible={},
                per_question_correct={},
                per_question_pct={},
                band_possible={},
                band_correct={},
                band_pct={},
            )
            return QuestionSummaryPointsPayload(
                assessment=assessment,
                kpis=kpis,
                questions=[],
                bands=[],
                teacher_groups=[],
                grand_total=grand_total,
                per_student_available=False,
            )

        # ── Question columns (deduplicated, sorted by cpalms then question_no)
        questions_by_id: dict[str, QsmQuestionColumn] = {}
        for r in rows:
            qid = safe_str(r.get("question_id"))
            if qid and qid not in questions_by_id:
                questions_by_id[qid] = QsmQuestionColumn(
                    question_id=qid,
                    question_no=safe_str(r.get("question_no")),
                    sorting_question_no=to_int(r.get("sorting_question_no")),
                    standard=safe_str(r.get("schoology_standard")),
                    cpalms_standard=safe_str(r.get("cpalms_standard"))
                    or safe_str(r.get("schoology_standard")),
                    position_number=safe_str(r.get("position_number")),
                    correct_answer=safe_str(r.get("correct_answer")),
                )
        questions = sorted(
            questions_by_id.values(),
            key=lambda q: (q.cpalms_standard or "~", q.sorting_question_no or 0),
        )

        # Contiguous CPALMS bands over the sorted question list. Every band —
        # even a single-question one — owns a trailing Score% sub-column in the
        # legacy layout, so map qid → band code for the per-band roll-up.
        bands: list[QspStandardBand] = []
        qid_band: dict[str, str] = {}
        for q in questions:
            code = q.cpalms_standard or q.standard or "Other"
            qid_band[q.question_id] = code
            if bands and bands[-1].cpalms_standard == code:
                bands[-1].question_ids.append(q.question_id)
            else:
                bands.append(
                    QspStandardBand(cpalms_standard=code, question_ids=[q.question_id])
                )

        # ── Per-(teacher, student) accumulation of fractional points ──────────
        teacher_students: dict[str, dict[str, dict[str, Any]]] = {}
        per_q_poss: dict[str, float] = {}
        per_q_recv: dict[str, float] = {}
        band_poss: dict[str, float] = {}
        band_recv: dict[str, float] = {}
        # teacher → qid → [recv, poss], for the web "- Teacher" subtotal block.
        teacher_q: dict[str, dict[str, list[float]]] = {}

        for r in rows:
            teacher = safe_str(r.get("section_instructors")) or "Unassigned"
            user_uid = safe_str(r.get("user_uid"))
            user_name = safe_str(r.get("user_name"))
            qid = safe_str(r.get("question_id"))
            pr = to_float(r.get("points_received"))
            pp = to_float(r.get("points_possible"))
            student = teacher_students.setdefault(teacher, {}).setdefault(
                user_uid,
                {
                    "user_uid": user_uid,
                    "user_name": user_name,
                    "cells": {},
                    "band_recv": {},
                    "band_poss": {},
                },
            )
            t_q = teacher_q.setdefault(teacher, {})
            if pp > 0:
                student["cells"][qid] = pr
                code = qid_band.get(qid, "Other")
                student["band_recv"][code] = student["band_recv"].get(code, 0.0) + pr
                student["band_poss"][code] = student["band_poss"].get(code, 0.0) + pp
                per_q_poss[qid] = per_q_poss.get(qid, 0.0) + pp
                per_q_recv[qid] = per_q_recv.get(qid, 0.0) + pr
                band_poss[code] = band_poss.get(code, 0.0) + pp
                band_recv[code] = band_recv.get(code, 0.0) + pr
                tq = t_q.setdefault(qid, [0.0, 0.0])
                tq[0] += pr
                tq[1] += pp
            else:
                student["cells"].setdefault(qid, None)

        def _pct2(recv: float, poss: float) -> Optional[float]:
            # Legacy rounds band / per-question Score% to 2 decimals.
            return round(recv / poss, 2) if poss > 0 else None

        teacher_groups: list[QspTeacherGroup] = []
        grand_recv = 0.0
        grand_poss = 0.0
        for teacher in sorted(teacher_students):
            students_list: list[QspStudentRow] = []
            t_recv = 0.0
            t_poss = 0.0
            for s in teacher_students[teacher].values():
                s_recv = sum(s["band_recv"].values())
                s_poss = sum(s["band_poss"].values())
                students_list.append(
                    QspStudentRow(
                        user_uid=s["user_uid"],
                        user_name=s["user_name"],
                        score_pct=round(s_recv / s_poss, 6) if s_poss > 0 else 0.0,
                        possible_points=round(s_poss, 4),
                        correct_count=round(s_recv, 4),
                        cells=dict(s["cells"]),
                        band_pct={
                            b.cpalms_standard: _pct2(
                                s["band_recv"].get(b.cpalms_standard, 0.0),
                                s["band_poss"].get(b.cpalms_standard, 0.0),
                            )
                            for b in bands
                        },
                    )
                )
                t_recv += s_recv
                t_poss += s_poss
            # Sort students asc by overall score (PBIX ord 6/7 default).
            students_list.sort(key=lambda x: x.score_pct)
            t_q = teacher_q.get(teacher, {})
            teacher_groups.append(
                QspTeacherGroup(
                    section_instructor=teacher,
                    teacher_score_pct=round(t_recv / t_poss, 6) if t_poss > 0 else 0.0,
                    students=students_list,
                    per_question_correct={
                        qid: round(v[0], 4) for qid, v in t_q.items()
                    },
                    per_question_possible={
                        qid: round(v[1], 4) for qid, v in t_q.items()
                    },
                    per_question_pct={
                        qid: (_pct2(v[0], v[1]) or 0.0) for qid, v in t_q.items()
                    },
                )
            )
            grand_recv += t_recv
            grand_poss += t_poss

        grand_total = QspGrandTotal(
            possible_points=round(grand_poss, 4),
            correct_count=round(grand_recv, 4),
            score_pct=round(grand_recv / grand_poss, 6) if grand_poss > 0 else 0.0,
            per_question_possible={k: round(v, 4) for k, v in per_q_poss.items()},
            per_question_correct={k: round(v, 4) for k, v in per_q_recv.items()},
            per_question_pct={
                k: (_pct2(per_q_recv.get(k, 0.0), v) or 0.0)
                for k, v in per_q_poss.items()
            },
            band_possible={k: round(v, 4) for k, v in band_poss.items()},
            band_correct={k: round(v, 4) for k, v in band_recv.items()},
            band_pct={
                k: (_pct2(band_recv.get(k, 0.0), v) or 0.0)
                for k, v in band_poss.items()
            },
        )

        return QuestionSummaryPointsPayload(
            assessment=assessment,
            kpis=kpis,
            questions=questions,
            bands=bands,
            teacher_groups=teacher_groups,
            grand_total=grand_total,
            per_student_available=True,
        )

    @staticmethod
    def _sorting_question_no(qno: str) -> int:
        """Match the SQL ``regexp_replace`` int cast — returns 0 for non-numeric
        labels like ``"Q1"``. ``to_int("Q1")`` returns 0 from a different code
        path so we keep this helper explicit."""
        return int("".join(c for c in qno if c.isdigit()) or 0)

    def _to_paginated_question_row(self, r: dict[str, Any]) -> PaginatedQuestionRow:
        ga = to_float(r.get("grade_average"))
        qno = safe_str(r.get("question_no"))
        # NOTE: keep `question` raw — the client renders it via
        # formatQuestionHtml + RichReportHtml (same as interactive QRA), and
        # server-side _strip_html would discard <img> tags the renderer needs.
        return PaginatedQuestionRow(
            question_id=safe_str(r.get("question_id")),
            question_no=qno,
            sorting_question_no=to_int(r.get("sorting_question_no"))
            or self._sorting_question_no(qno),
            position_number=safe_str(r.get("position_number")) or "n/a",
            question=safe_str(r.get("question")),
            correct_answer=safe_str(r.get("correct_answer")),
            grade_average=round(ga, 6),
            grade_average_pct=_format_pct(ga),
            incorrect_choice_details=safe_str(r.get("incorrect_choice_details")),
            incorrect_details_name=safe_str(r.get("incorrect_details_name")),
            standards=safe_str(r.get("standards")),
            cpalms_standard=safe_str(r.get("cpalms_standard"))
            or safe_str(r.get("standard")),
        )

    async def build_qra_paginated(self, item_id: str) -> QraPaginatedPayload:
        meta_row = await self.cube.get_assessment_meta(item_id)
        if not meta_row:
            raise ResourceNotFoundError("Assessment", item_id)
        assessment = self._build_assessment_meta(
            meta_row, meta_row.get("first_access"), meta_row.get("latest_attempt")
        )
        kpis = await self._build_paginated_kpis(item_id)

        # Reuse the questions_overall reader so paginated base shares
        # exactly the same row math as the interactive QRA (including the
        # canonical per-question grade override and the cube's pre-built
        # ``incorrect_details_name`` named-students string).
        question_rows = await self.cube.get_questions_overall_for_item(item_id)
        canon_per_q = await self.cube.get_canonical_per_question_grades(item_id)
        canon_q_by_id = {
            safe_str(r.get("question_id")): to_float(r.get("grade_average"))
            for r in canon_per_q
        }
        for q in question_rows:
            qid = safe_str(q.get("question_id"))
            if qid in canon_q_by_id:
                q["grade_average"] = canon_q_by_id[qid]

        # Sort ASC by grade_average (PBIX ord 11 default — surfaces problems
        # first). Tiebreak on numeric portion of question_no.
        question_rows.sort(
            key=lambda r: (
                to_float(r.get("grade_average")),
                self._sorting_question_no(safe_str(r.get("question_no"))),
            )
        )

        questions = [self._to_paginated_question_row(r) for r in question_rows]

        return QraPaginatedPayload(
            assessment=assessment, kpis=kpis, questions=questions
        )

    async def build_qra_by_teacher(self, item_id: str) -> QraByTeacherPayload:
        meta_row = await self.cube.get_assessment_meta(item_id)
        if not meta_row:
            raise ResourceNotFoundError("Assessment", item_id)
        assessment = self._build_assessment_meta(
            meta_row, meta_row.get("first_access"), meta_row.get("latest_attempt")
        )
        kpis = await self._build_paginated_kpis(item_id)

        rows = await self.cube.get_qra_by_teacher_rows(item_id)
        groups: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            t = safe_str(r.get("section_instructors")) or "Unassigned"
            groups.setdefault(t, []).append(r)

        teacher_groups: list[QraTeacherGroup] = []
        for teacher in sorted(groups):
            qs = groups[teacher]
            # Average grade across this teacher's questions.
            grades = [to_float(q.get("grade_average")) for q in qs]
            avg = (sum(grades) / len(grades)) if grades else 0.0
            teacher_groups.append(
                QraTeacherGroup(
                    section_instructor=teacher,
                    teacher_grade_average=round(avg, 6),
                    teacher_grade_average_pct=_format_pct(avg),
                    questions=[self._to_paginated_question_row(q) for q in qs],
                )
            )

        return QraByTeacherPayload(
            assessment=assessment, kpis=kpis, teacher_groups=teacher_groups
        )

    async def build_qra_by_standard_teacher(
        self, item_id: str
    ) -> QraByStandardTeacherPayload:
        meta_row = await self.cube.get_assessment_meta(item_id)
        if not meta_row:
            raise ResourceNotFoundError("Assessment", item_id)
        assessment = self._build_assessment_meta(
            meta_row, meta_row.get("first_access"), meta_row.get("latest_attempt")
        )
        kpis = await self._build_paginated_kpis(item_id)

        rows = await self.cube.get_qra_by_standard_teacher_rows(item_id)
        # Group rows into (standard, teacher) nests preserving SQL order.
        # dim_standard can map one schoology_standard to several rows (the
        # course-prefix aliases — see
        # docs/audit/legacy-schoology-cpalms-mapping.md), so the LEFT JOIN
        # fans a single question out into duplicate rows under the same
        # standard (identical grade_average, only the description differs).
        # Dedup on question_id within each (standard, teacher) so a question
        # renders ONCE and "# questions" / the standard average reflect the
        # DISTINCT question set, not the fanned-out row count.
        nested: dict[str, dict[str, list[dict[str, Any]]]] = {}
        seen_qid: dict[str, dict[str, set[str]]] = {}
        std_meta: dict[str, dict[str, Any]] = {}
        for r in rows:
            std = safe_str(r.get("cpalms_standard")) or "Unaligned"
            teacher = safe_str(r.get("section_instructors")) or "Unassigned"
            qid = safe_str(r.get("question_id"))
            teacher_seen = seen_qid.setdefault(std, {}).setdefault(teacher, set())
            if qid and qid in teacher_seen:
                continue
            if qid:
                teacher_seen.add(qid)
            nested.setdefault(std, {}).setdefault(teacher, []).append(r)
            if std not in std_meta:
                std_meta[std] = {
                    "description": _strip_html(
                        safe_str(r.get("standard_description"))
                    ),
                }

        # Iterate in SQL insertion order (dicts preserve it). The query
        # ORDERs BY the full Schoology code then section_instructor, which
        # IS the legacy SSRS group order (PAG-7) — re-sorting here would
        # risk a different collation than the DB.
        standard_groups: list[QraStandardGroup] = []
        for std in nested:
            t_groups: list[QraStandardTeacherGroup] = []
            std_question_grades: list[float] = []
            for teacher in nested[std]:
                qs = nested[std][teacher]
                # Average over the DISTINCT per-question grade_averages now
                # that the standard's alias fan-out is collapsed.
                q_grades = [to_float(q.get("grade_average")) for q in qs]
                t_avg = sum(q_grades) / len(q_grades) if q_grades else 0.0
                std_question_grades.extend(q_grades)
                t_groups.append(
                    QraStandardTeacherGroup(
                        section_instructor=teacher,
                        teacher_standard_average=round(t_avg, 6),
                        teacher_standard_average_pct=_format_pct(t_avg),
                        questions=[
                            self._to_paginated_question_row(q) for q in qs
                        ],
                    )
                )
            s_avg = (
                sum(std_question_grades) / len(std_question_grades)
                if std_question_grades
                else 0.0
            )
            standard_groups.append(
                QraStandardGroup(
                    cpalms_standard=std,
                    standard_description=std_meta[std]["description"],
                    standard_average=round(s_avg, 6),
                    standard_average_pct=_format_pct(s_avg),
                    teacher_groups=t_groups,
                )
            )

        return QraByStandardTeacherPayload(
            assessment=assessment, kpis=kpis, standard_groups=standard_groups
        )
