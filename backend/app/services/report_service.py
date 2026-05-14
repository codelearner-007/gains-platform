"""Composes the Question-Response-Analysis (QRA) and Standards-Deep-Dive
report payloads from the cube_* / dim_* tables.

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
    SddBandStrandRow,
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
    YTDGradeDistribution,
    YTDHeatmapCell,
    YTDKpis,
    YTDPeriodInfo,
    YTDSchoolInfo,
    YTDStudentScatter,
    YTDStudentSummary,
    YTDTimelinePoint,
)

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: Optional[str]) -> str:
    if not s:
        return ""
    return _HTML_TAG_RE.sub("", s).strip()


def _format_pct(v: float) -> str:
    return f"{v * 100:.1f}%"


# PBIX 70/80 traffic-light hexes (see lib/reports/colors.ts). Matched here so
# the server can stamp the perf-color directly into the payload — saves the
# client from recomputing for every row.
_PERF_PINK = "#FFCCFF"
_PERF_YELLOW = "#FFFF00"
_PERF_GREEN = "#00FF06"


def _perf_color(grade: float) -> str:
    if grade is None or grade <= 0:
        return ""
    if grade < 0.7:
        return _PERF_PINK
    if grade < 0.8:
        return _PERF_YELLOW
    return _PERF_GREEN


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
                cpalms_standard=safe_str(r.get("cpalms_standard")),
                schoology_standard=safe_str(r.get("schoology_standard")),
                strand=_decode_html(safe_str(r.get("strand"))),
                num_questions=to_int(r.get("num_questions")),
                grade_average=round(to_float(r.get("grade_average")), 6),
                grade_average_pct=_format_pct(to_float(r.get("grade_average"))),
            )
            for r in standard_rows
        ]
        return strands_rollup, standards_rollup

    # ────────────────────────────────────────────────────────────────────
    # Question-Response-Analysis (composed payload)
    # ────────────────────────────────────────────────────────────────────
    async def build_question_response_analysis(
        self, item_id: str
    ) -> QuestionResponseAnalysisPayload:
        meta_row = await self.cube.get_assessment_meta(item_id)
        if not meta_row:
            raise ResourceNotFoundError("Assessment", item_id)

        school_summary = await self.cube.get_school_summary_for_item(item_id)
        grade_summary = await self.cube.get_grade_summary_for_item(item_id)
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

        # ─── KPIs ──────────────────────────────────────────────────────────
        # Prefer cube_school_summary's pre-aggregated values; fall back to
        # cube_grade_summary for min/max.
        total_questions = to_int((school_summary or {}).get("total_questions"))
        total_standards = to_int((school_summary or {}).get("total_standards"))
        total_students = to_int((school_summary or {}).get("total_students"))
        total_possible_point = to_float(
            (school_summary or {}).get("total_possible_point")
        )
        total_score = to_float((school_summary or {}).get("total_score"))
        grade_average = to_float((school_summary or {}).get("grade_average"))

        # Min/max from grade summary; if absent, fall back to per-question stats
        grade_min = to_float((grade_summary or {}).get("grade_min"))
        grade_max = to_float((grade_summary or {}).get("grade_max"))
        if not grade_summary and question_rows:
            qa_values = [to_float(q.get("grade_average")) for q in question_rows]
            grade_min = min(qa_values, default=0.0)
            grade_max = max(qa_values, default=0.0)

        instructors = self._split_instructors(
            safe_str(meta_row.get("section_instructors"))
        )

        kpis = KPIs(
            instructors=instructors,
            grade_average=round(grade_average, 6),
            grade_average_pct=_format_pct(grade_average),
            total_questions=total_questions,
            total_standards=total_standards,
            total_students=total_students,
            grade_min=round(grade_min, 6),
            grade_max=round(grade_max, 6),
            grade_min_pct=_format_pct(grade_min),
            grade_max_pct=_format_pct(grade_max),
            total_possible_point=round(total_possible_point, 4),
            total_score=round(total_score, 4),
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
                description=safe_str(q.get("description")),
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

        # ─── Strands & Standards rollups (per assessment) ─────────────────
        strands_rollup, standards_rollup = await self._build_strand_standard_rollups(
            item_id
        )

        return QuestionResponseAnalysisPayload(
            assessment=assessment,
            kpis=kpis,
            students=students,
            questions_overall=questions_overall,
            incorrect_choices=incorrect_choices,
            raw_question_options=raw_question_options,
            strands_rollup=strands_rollup,
            standards_rollup=standards_rollup,
        )

    # ────────────────────────────────────────────────────────────────────
    # Standards Deep Dive (per-assessment, mirrors PBIX page #16)
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

        # ─── Strand + standard rollups (shared with QRA) ──────────────────
        strands_rollup, standards_rollup = await self._build_strand_standard_rollups(
            item_id
        )

        # ─── KPI strip values ─────────────────────────────────────────────
        school_summary = await self.cube.get_school_summary_for_item(item_id)
        total_students = to_int((school_summary or {}).get("total_students"))

        # Number of Questions / Standards per spec §3 use DISTINCTCOUNT on
        # cube_question_summary_overall, which after our strand-aware
        # aggregation reduces to summing the strand-level counts (each
        # ukey is unique across strands for an item once we drop NULL
        # strand rows).
        total_questions = sum(s.num_questions for s in strands_rollup)
        total_standards = sum(s.num_standards for s in strands_rollup)

        # Grade Average across the standards within this assessment
        # (Measure.Grade_Average_Standard_Measure).
        if standards_rollup:
            grade_average = sum(s.grade_average for s in standards_rollup) / len(
                standards_rollup
            )
        else:
            grade_average = to_float((school_summary or {}).get("grade_average"))

        instructors = self._split_instructors(
            safe_str(meta_row.get("section_instructors"))
        )

        kpis = SddKpis(
            instructors=instructors,
            total_students=total_students,
            total_questions=total_questions,
            total_standards=total_standards,
            grade_average=round(grade_average, 6),
            grade_average_pct=_format_pct(grade_average),
        )

        # ─── Performance bands (3 × 100% stacked bar charts) ──────────────
        # PBIX traffic-light: green ≥0.8, yellow [0.7, 0.8), pink <0.7.
        band_high: list[SddBandStrandRow] = []
        band_mid: list[SddBandStrandRow] = []
        band_low: list[SddBandStrandRow] = []
        for s in strands_rollup:
            row = SddBandStrandRow(
                strand=s.strand,
                num_standards=s.num_standards,
                num_questions=s.num_questions,
                grade_average=s.grade_average,
            )
            if s.grade_average >= 0.8:
                band_high.append(row)
            elif s.grade_average >= 0.7:
                band_mid.append(row)
            else:
                band_low.append(row)

        return StandardsDeepDivePayload(
            assessment=assessment,
            kpis=kpis,
            strands_rollup=strands_rollup,
            standards_rollup=standards_rollup,
            band_high=band_high,
            band_mid=band_mid,
            band_low=band_low,
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
    # Year-To-Date Performance (cross-assessment, school-wide)
    # ────────────────────────────────────────────────────────────────────
    async def build_year_to_date_performance(
        self,
    ) -> YearToDatePerformancePayload:
        meta = await self.cube.get_ytd_school_meta() or {}
        kpi_row = await self.cube.get_ytd_overall_kpis() or {}
        timeline_rows = await self.cube.get_ytd_timeline()
        grade_dist_rows = await self.cube.get_ytd_grade_distribution()
        prog_rows = await self.cube.get_ytd_student_progression()
        heatmap_rows = await self.cube.get_ytd_strand_heatmap()

        date_from = meta.get("date_from")
        date_to = meta.get("date_to")
        school = YTDSchoolInfo(
            name=safe_str(meta.get("name")),
            logo_url=meta.get("logo_url") or None,
            current_session=safe_str(meta.get("current_session")),
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
            total_students=to_int(kpi_row.get("total_students")),
            total_assessments=to_int(kpi_row.get("total_assessments")),
            total_questions_answered=to_int(
                kpi_row.get("total_questions_answered")
            ),
            overall_avg_pct=_format_pct(overall_avg),
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
        grade_sum = 0.0
        at_target = 0
        total_questions_acc = 0
        for row in rows:
            cpalms = safe_str(row.get("cpalms_standard"))
            if not cpalms:
                continue
            grade_avg = to_float(row.get("grade_average"))
            num_q = to_int(row.get("num_questions"))
            num_a = to_int(row.get("num_assessments"))
            strand = _decode_html(safe_str(row.get("strand")))
            description_raw = safe_str(row.get("description"))
            description = _strip_html(description_raw)
            last_change = row.get("last_change_date_time")
            standards.append(
                StandardSummaryRollupRow(
                    cpalms_standard=cpalms,
                    schoology_standard=safe_str(row.get("schoology_standard")),
                    strand=strand,
                    cluster=safe_str(row.get("cluster")),
                    cognitive_complexity=safe_str(row.get("cognitive_complexity")),
                    description=description,
                    subject=safe_str(row.get("subject")),
                    num_questions=num_q,
                    num_assessments=num_a,
                    grade_average=round(grade_avg, 6),
                    grade_average_pct=_format_pct(grade_avg),
                    perf_color=_perf_color(grade_avg),
                    last_change_date_time=(
                        last_change.isoformat() if last_change else None
                    ),
                )
            )
            grade_sum += grade_avg
            total_questions_acc += num_q
            if grade_avg >= 0.8:
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
        grade_average = grade_sum / total_standards if total_standards else 0.0
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

        kpis = StandardSummaryKpis(
            total_standards=total_standards,
            total_questions=total_questions_acc,
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

        return StandardSummaryPayload(
            school=school,
            filters_applied=filters,
            kpis=kpis,
            standards=standards,
            strand_counts=strand_counts,
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
                    perf_color=_perf_color(grade_avg),
                    subjects=subjects,
                )
            )
            band_row = StrandSummaryBandRow(
                strand=strand_name,
                num_standards=num_standards,
                num_questions=num_questions,
                grade_average=round(grade_avg, 6),
            )
            if grade_avg >= 0.8:
                band_high.append(band_row)
            elif grade_avg >= 0.7:
                band_mid.append(band_row)
            else:
                band_low.append(band_row)
            if num_questions > 0 and grade_avg < worst_grade:
                worst_grade = grade_avg
                worst_strand = strand_name

        standards_rollup: list[StrandSummaryStandardRow] = [
            StrandSummaryStandardRow(
                strand=_decode_html(safe_str(r.get("strand"))),
                cpalms_standard=safe_str(r.get("cpalms_standard")),
                schoology_standard=safe_str(r.get("schoology_standard")),
                cluster=safe_str(r.get("cluster")),
                num_questions=to_int(r.get("num_questions")),
                num_assessments=to_int(r.get("num_assessments")),
                grade_average=round(to_float(r.get("grade_average")), 6),
                grade_average_pct=_format_pct(to_float(r.get("grade_average"))),
                perf_color=_perf_color(to_float(r.get("grade_average"))),
            )
            for r in std_rows
            if safe_str(r.get("cpalms_standard"))
        ]

        total_strands = len(strands_rollup)
        total_standards = sum(s.num_standards for s in strands_rollup)
        total_questions = sum(s.num_questions for s in strands_rollup)
        total_assessments_set: set[int] = set()
        # Count distinct assessment ids across the union of strands; the
        # strand-rollup itself counts per-strand-distinct only.
        for r in strand_rows:
            num_a = to_int(r.get("num_assessments"))
            if num_a:
                total_assessments_set.add(num_a)
        # Since we don't carry item_ids back, fall back to using max of the
        # per-strand counts as a lower bound. For an exact value we'd need a
        # second query — pragmatic compromise: take the max.
        total_assessments = max(
            (to_int(r.get("num_assessments")) for r in strand_rows), default=0
        )

        if strands_rollup:
            grade_average = sum(s.grade_average for s in strands_rollup) / len(
                strands_rollup
            )
        else:
            grade_average = 0.0
            worst_strand = ""
            worst_grade = 0.0

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

        school = YTDSchoolInfo(
            name=safe_str(meta.get("name")),
            logo_url=meta.get("logo_url") or None,
            current_session=safe_str(meta.get("current_session")),
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
        )
