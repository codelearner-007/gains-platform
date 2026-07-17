"""Shared base for the report builder mixins.

Holds ``__init__`` and every private helper method used across the
per-assessment / yearly / dashboard families. Verbatim extraction from the
former ``app.services.report_service`` monolith (pre-B2).
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.cube_repository import CubeRepository
from app.repositories.dim_repository import DimRepository
from app.schemas.reports import (
    AlignmentDataQuality,
    AssessmentMeta,
    PaginatedKpis,
    PaginatedQuestionRow,
    SddStandardRow,
    SddStrandRow,
)
from app.utils.coercion import safe_str, to_float, to_int

from ._helpers import (
    _ALIGNMENT_REMEDIATION,
    _classify_alignment,
    _classify_alignment_cause,
    _decode_html,
    _format_pct,
    _format_pct_opt,
    _round_opt,
)


class _ReportServiceBase:
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
        self, item_id: str, instructor: Optional[str] = None
    ) -> dict[str, Any]:
        """Single source of truth for per-assessment KPI strip values.

        ``instructor`` (OPTIONAL, single comma-separated string) narrows the
        merged report to the sections taught by ANY of the listed instructors;
        Total Students and every numeric recompute over that narrowed section
        set. NULL/empty = no filter (byte-identical to the full merge).

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
        row = await self.cube.get_canonical_kpis_for_item(item_id, instructor) or {}
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
        self, item_id: str, instructor: Optional[str] = None
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
        quality = await self.cube.get_alignment_quality_for_item(item_id, instructor)
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
                item_id, limit=5, instructor=instructor
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
        self, item_id: str, instructor: Optional[str] = None
    ) -> tuple[list[SddStrandRow], list[SddStandardRow]]:
        """Shared aggregation used by both SDD and QRA endpoints.

        ``instructor`` (OPTIONAL) narrows the merged report to the matching
        sections; NULL/empty = no filter (byte-identical).
        """
        strand_rows = await self.cube.get_strand_rollup_for_item(item_id, instructor)
        standard_rows = await self.cube.get_standard_rollup_for_item(
            item_id, instructor
        )

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
