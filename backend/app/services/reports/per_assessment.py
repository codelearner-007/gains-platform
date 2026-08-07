"""Per-assessment report builders (QRA / SDD / IAD / QSR / paginated).

Mirrors the ``app.api.v1.reports.per_assessment`` router family. Verbatim
extraction from the former ``app.services.report_service`` monolith (pre-B2);
``self.<helper>`` / ``self.session`` resolve via MRO from ``_ReportServiceBase``.
"""

from __future__ import annotations

from typing import Any, Optional

from app.core.exceptions import ResourceNotFoundError
from app.schemas.reports import (
    IadDistractorRow,
    IadKpis,
    IadQuestionContext,
    IadStudentAttempt,
    IncorrectAnswerDetailsPayload,
    KPIs,
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
    StandardsDeepDivePayload,
)
from app.utils.coercion import safe_str, to_float, to_int

from ._helpers import (
    _BAND_HIGH_THRESHOLD,
    _BAND_MID_THRESHOLD,
    _decode_html,
    _format_pct,
    _strip_html,
)


class _PerAssessmentMixin:
    """Per-assessment builders composed onto :class:`ReportService`."""

    # ────────────────────────────────────────────────────────────────────
    # Question-Response-Analysis (composed payload)
    # ────────────────────────────────────────────────────────────────────
    async def build_question_response_analysis(
        self, item_id: str, instructor: Optional[str] = None
    ) -> QuestionResponseAnalysisPayload:
        """Composed QRA payload for one MERGED assessment.

        ``instructor`` (OPTIONAL, single comma-separated string) narrows the
        merged multi-section report to the sections taught by ANY of the listed
        instructors. NULL/empty = no filter, byte-identical to the full merge.
        """
        meta_row = await self.cube.get_assessment_meta(item_id, instructor)
        if not meta_row:
            raise ResourceNotFoundError("Assessment", item_id)

        question_rows = await self.cube.get_questions_overall_for_item(
            item_id, instructor
        )

        # ─── AssessmentMeta ────────────────────────────────────────────────
        first_access = meta_row.get("first_access")
        latest_attempt = meta_row.get("latest_attempt")

        assessment = self._build_assessment_meta(
            meta_row, first_access, latest_attempt
        )

        # ─── KPIs (canonical, legacy-DAX-equivalent) ──────────────────────
        # Both QRA and SDD compute KPIs through this helper so the strip
        # values can never disagree for the same item.
        canon = await self._compute_canonical_kpis_for_item(item_id, instructor)

        # ─── Strands & Standards rollups (per assessment) ─────────────────
        # Compute BEFORE building the KPI strip so the "Other" synthesis
        # (Schoology / legacy PBIX parity for unaligned assessments) can
        # bump ``canon["total_standards"]`` to 1 before the KPI is frozen.
        strands_rollup, standards_rollup = await self._build_strand_standard_rollups(
            item_id, instructor
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
        canon_per_q = await self.cube.get_canonical_per_question_grades(
            item_id, instructor
        )
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
        data_quality = await self._build_alignment_data_quality_for_item(
            item_id, instructor
        )

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
        self, item_id: str, instructor: Optional[str] = None
    ) -> StandardsDeepDivePayload:
        """Per-assessment SDD payload for one MERGED assessment.

        ``instructor`` (OPTIONAL, single comma-separated string) narrows the
        merged multi-section report to the sections taught by ANY of the listed
        instructors. NULL/empty = no filter, byte-identical to the full merge.
        """
        meta_row = await self.cube.get_assessment_meta(item_id, instructor)
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
        canon = await self._compute_canonical_kpis_for_item(item_id, instructor)

        # ─── Strand + standard rollups (shared with QRA) ──────────────────
        # Compute BEFORE building the KPI strip so the "Other" synthesis
        # (Schoology / legacy PBIX parity for unaligned assessments) can
        # bump ``canon["total_standards"]`` to 1 before the KPI is frozen.
        strands_rollup, standards_rollup = await self._build_strand_standard_rollups(
            item_id, instructor
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
        band_rows = await self.cube.get_standard_bands_for_item(item_id, instructor)
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

        data_quality = await self._build_alignment_data_quality_for_item(
            item_id, instructor
        )

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
            description=_strip_html(safe_str(question_row.get("description"))),
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
    # Paginated reports (PBIX ord 6/7/16, 11, 12, 13)
    # ────────────────────────────────────────────────────────────────────
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
