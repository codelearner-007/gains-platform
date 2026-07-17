"""Yearly / school-wide report builders (YTD / standard / strand / DQ).

Mirrors the ``app.api.v1.reports.yearly`` + ``data_quality`` router families.
Verbatim extraction from the former ``app.services.report_service`` monolith
(pre-B2); ``self.<helper>`` / ``self.session`` resolve via MRO from
``_ReportServiceBase``.
"""

from __future__ import annotations

from typing import Any, Optional

from app.schemas.reports import (
    AlignmentDataQuality,
    AlignmentDataQualityReport,
    AlignmentItemRow,
    StandardSummaryFilters,
    StandardSummaryKpis,
    StandardSummaryPayload,
    StandardSummaryRollupRow,
    StrandSummaryFilters,
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
from app.utils.coercion import safe_str, to_float, to_int

from ._helpers import (
    _ALIGNMENT_REMEDIATION,
    _BAND_HIGH_THRESHOLD,
    _classify_alignment,
    _coerce_str_list,
    _decode_html,
    _format_pct,
    _strip_html,
)


class _YearlyMixin:
    """Yearly / school-wide builders composed onto :class:`ReportService`."""

    # ────────────────────────────────────────────────────────────────────
    # Year To Date - Longitudinal Report (cross-assessment, school-wide)
    # ────────────────────────────────────────────────────────────────────
    async def build_year_to_date_performance(
        self,
        filters: Optional["YTDFilters"] = None,
    ) -> YearToDatePerformancePayload:
        """Legacy YTD Longitudinal paginated matrix (PBIX ord 8/9/10).

        Faithful clone of the SSRS matrix, sourced from ``cube_user_summary``
        (legacy's own ``cube_users_summary``) — one scoped GROUP BY, no fact
        re-derivation. Rows are grouped Classroom Instructor → Student; columns
        are the standards assessed YTD for the (session, grade, subject,
        assessment_type[, section]) scope. Per the legacy RDL:

        * per-standard **Score** cell = ``SUM(score)/SUM(possible)`` (``n/N``);
        * per-standard **%** cell = mastery ``SUM(score)/SUM(possible)`` for
          that (student, standard) — the same received/possible ratio the
          per-standard subtotals and grand totals use, so a cell, its column
          subtotal and the grand total all sit on one 0–100 % mastery scale
          (the legacy fully-populated RDL renders these as mastery, banded at
          70/80 %);
        * student **Score %** = mastery ``SUM(score)/SUM(possible)``;
        * **Possible Points** column = ``MAX(user_overall_possible_point)``;
        * **# Correct Answers** column = ``SUM(score)``;
        * year grand-total band reads the precomputed ``*_by_overall_year``
          columns verbatim (not a re-sum of the visible cells).
        """
        f = filters or YTDFilters()
        meta = await self.cube.get_ytd_school_meta(
            session_filter=f.session,
            subject=f.subject,
            grade=f.grade,
            category=f.category,
            section=f.section,
        ) or {}
        rows = await self.cube.get_ytd_cells_from_cus(
            f.session, f.subject, f.grade, f.category, f.section
        )

        school = YTDSchoolInfo(
            name=safe_str(meta.get("name")),
            logo_url=meta.get("logo_url") or None,
            current_session=safe_str(meta.get("current_session")),
            course_unit=safe_str(meta.get("course_unit")),
            assessment_types=_coerce_str_list(meta.get("assessment_types")),
        )

        def _pct(recv: float, poss: float) -> float:
            return round(recv / poss, 6) if poss > 0 else 0.0

        # Year grand-total band = the precomputed ``*_by_overall_year`` columns
        # (constant within a scope); read once off any row.
        grand_year_recv = to_float(rows[0].get("grand_score")) if rows else 0.0
        grand_year_poss = to_float(rows[0].get("grand_possible")) if rows else 0.0

        # ── Standard columns ────────────────────────────────────────────────
        # Legacy orders the standard columns ASCENDING by each standard's overall
        # mastery Score% (SUM(score)/SUM(possible)); ties break alphabetically.
        std_totals: dict[str, list[float]] = {}  # label → [recv, poss]
        unit_names_by_std: dict[str, str] = {}
        unit_count_by_std: dict[str, int] = {}
        for r in rows:
            label = safe_str(r.get("standard_label"))
            if not label:
                continue
            agg = std_totals.setdefault(label, [0.0, 0.0])
            agg[0] += to_float(r.get("points_received"))
            agg[1] += to_float(r.get("points_possible"))
            if label not in unit_names_by_std:
                unit_names_by_std[label] = safe_str(r.get("unit_names"))
                unit_count_by_std[label] = to_int(r.get("unit_count"))

        def _std_score(label: str) -> float:
            recv, poss = std_totals.get(label, [0.0, 0.0])
            return _pct(recv, poss)

        ordered_labels = sorted(std_totals, key=lambda lab: (_std_score(lab), lab))
        standards = [
            YtdStandardColumn(
                standard_label=label,
                schoology_standard=label,
                unit_names=unit_names_by_std.get(label, ""),
                unit_count=unit_count_by_std.get(label, 0),
            )
            for label in ordered_labels
        ]

        # ── Teacher → student → (standard) pivot ────────────────────────────
        # Each (teacher, student, standard) is one SQL row → direct assignment.
        teachers: dict[str, dict[str, dict[str, Any]]] = {}
        for r in rows:
            teacher = safe_str(r.get("section_instructors")) or "Unassigned"
            uid = safe_str(r.get("user_uid"))
            label = safe_str(r.get("standard_label"))
            student = teachers.setdefault(teacher, {}).setdefault(
                uid,
                {
                    "user_name": safe_str(r.get("user_name")),
                    # per-student constants (identical on every one of the
                    # student's rows).
                    "user_overall_possible_point": to_float(
                        r.get("user_overall_possible_point")
                    ),
                    "tests_taken": to_int(r.get("tests_taken")),
                    "cells": {},
                },
            )
            student["cells"][label] = [
                to_float(r.get("points_received")),
                to_float(r.get("points_possible")),
            ]

        def _teacher_score(name: str) -> float:
            recv = sum(v[0] for s in teachers[name].values() for v in s["cells"].values())
            poss = sum(v[1] for s in teachers[name].values() for v in s["cells"].values())
            return _pct(recv, poss)

        teacher_groups: list[YtdTeacherGroup] = []
        grand_std: dict[str, list[float]] = {}

        # Legacy orders Classroom-Instructor groups ASCENDING by teacher mastery
        # Score%, students ASCENDING by their mastery Score%.
        for teacher in sorted(teachers, key=lambda t: (_teacher_score(t), t)):
            students_list: list[YtdStudentRow] = []
            t_std: dict[str, list[float]] = {}
            for uid, s in teachers[teacher].items():
                s_recv = sum(v[0] for v in s["cells"].values())
                s_poss = sum(v[1] for v in s["cells"].values())
                cells = {
                    label: YtdCell(
                        points_received=round(v[0], 4),
                        points_possible=round(v[1], 4),
                        # per-standard "%" = mastery received/possible for that
                        # (student, standard) — same scale as the subtotal and
                        # grand-total Score% this cell sits under.
                        score_pct=_pct(v[0], v[1]),
                    )
                    for label, v in s["cells"].items()
                }
                students_list.append(
                    YtdStudentRow(
                        user_uid=uid,
                        user_name=s["user_name"],
                        score_pct=_pct(s_recv, s_poss),          # mastery
                        tests_taken=s["tests_taken"],
                        points_received=round(s_recv, 4),        # # Correct Answers
                        # "Possible Points" column = Max(user_overall_possible_point).
                        points_possible=round(s["user_overall_possible_point"], 4),
                        cells=cells,
                    )
                )
                for label, v in s["cells"].items():
                    agg = t_std.setdefault(label, [0.0, 0.0])
                    agg[0] += v[0]
                    agg[1] += v[1]
                    g = grand_std.setdefault(label, [0.0, 0.0])
                    g[0] += v[0]
                    g[1] += v[1]
            # Legacy orders students ASCENDING by mastery Score%; break ties on
            # name then uid so row order is fully deterministic across identical
            # requests/exports.
            students_list.sort(key=lambda x: (x.score_pct, x.user_name, x.user_uid))
            t_recv = sum(v[0] for v in t_std.values())
            t_poss = sum(v[1] for v in t_std.values())
            teacher_groups.append(
                YtdTeacherGroup(
                    section_instructor=teacher,
                    teacher_score_pct=_pct(t_recv, t_poss),
                    students=students_list,
                    standard_subtotals={
                        label: YtdStandardTotal(
                            points_received=round(v[0], 4),
                            points_possible=round(v[1], 4),
                            score_pct=_pct(v[0], v[1]),   # subtotal Score% = mastery
                        )
                        for label, v in t_std.items()
                    },
                )
            )

        grand_total = YtdGrandTotal(
            points_received=round(grand_year_recv, 4),        # Score_By_OverallYear
            points_possible=round(grand_year_poss, 4),        # Possible_By_OverallYear
            score_pct=_pct(grand_year_recv, grand_year_poss),
            standard_totals={
                label: YtdStandardTotal(
                    points_received=round(v[0], 4),
                    points_possible=round(v[1], 4),
                    score_pct=_pct(v[0], v[1]),   # per-standard grand = mastery
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
        self, filters: StandardSummaryFilters, cards_only: bool = False
    ) -> StandardSummaryPayload:
        """Legacy Standard Summary (PBIX ord 14): one card per cPalms_Standard.

        Faithful to the legacy page — a per-standard card grid (navy code badge,
        subject/grade tag, strand/cluster/cognitive-complexity, "Number of
        Questions", cleaned description, mini correct/incorrect bar, adopted
        date). The legacy page carries NO KPI-card strip, ranked bar, rollup
        table or by-strand chart — those were non-legacy and are removed from
        the report. The ``kpis`` block is still returned (the dashboard's stat
        cards consume it) but is not rendered on this page. Per-standard
        correct% = AVERAGE(cube_question_summary_overall[Grade_Average]) and
        # of questions = DISTINCTCOUNT(cqso[Question_No]) (from the rollup query).
        """
        meta = await self.cube.get_school_wide_meta() or {}
        rows = await self.cube.get_school_standard_rollup(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
        )

        standards: list[StandardSummaryRollupRow] = []
        at_target = 0
        for row in rows:
            schoology = safe_str(row.get("schoology_standard"))
            if not schoology:
                continue
            grade_avg = to_float(row.get("grade_average"))
            if grade_avg >= _BAND_HIGH_THRESHOLD:
                at_target += 1
            last_change = row.get("last_change_date_time")
            standards.append(
                StandardSummaryRollupRow(
                    schoology_standard=schoology,
                    cpalms_standard=safe_str(row.get("cpalms_standard"))
                    or schoology,
                    strand=_decode_html(safe_str(row.get("strand"))),
                    cluster=safe_str(row.get("cluster")),
                    cognitive_complexity=safe_str(row.get("cognitive_complexity")),
                    description=_strip_html(safe_str(row.get("description"))),
                    subject=safe_str(row.get("subject")),
                    grades=_coerce_str_list(row.get("grades")),
                    num_questions=to_int(row.get("num_questions")),
                    grade_average=round(grade_avg, 6),
                    grade_average_pct=_format_pct(grade_avg),
                    last_change_date_time=(
                        last_change.isoformat() if last_change else None
                    ),
                )
            )

        school = YTDSchoolInfo(
            name=safe_str(meta.get("name")),
            logo_url=meta.get("logo_url") or None,
            current_session=safe_str(meta.get("current_session")),
        )

        # KPI block — NOT rendered on the legacy report page (removed for
        # parity), but the dashboard's stat cards read it (Total Students /
        # Total Standards / school average). Sequential reads (AsyncSession
        # is not safe for concurrent statements on the same connection).
        total_standards = len(standards)
        at_target_pct = at_target / total_standards if total_standards else 0.0
        # The report page (cards_only) never renders these; skip the three
        # cube reads — chiefly the total_students fact scan (~2.5s).
        total_students = 0
        total_questions_cqso = 0
        grade_average = 0.0
        if not cards_only:
            total_students = await self.cube.get_school_total_students(
                session_filter=filters.session,
                subject=filters.subject,
                grade=filters.grade,
                category=filters.category,
            )
            total_questions_cqso = await self.cube.get_school_total_questions(
                session_filter=filters.session,
                subject=filters.subject,
                grade=filters.grade,
                category=filters.category,
            )
            grade_average = await self.cube.get_school_overall_grade_average(
                session_filter=filters.session,
                subject=filters.subject,
                grade=filters.grade,
                category=filters.category,
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

        quality = await self.cube.get_school_alignment_quality(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
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
            data_quality=data_quality,
        )

    # ────────────────────────────────────────────────────────────────────
    # Strand Summary (school-wide, per-Strand grain)
    # ────────────────────────────────────────────────────────────────────
    async def build_strand_summary(
        self, filters: StrandSummaryFilters
    ) -> StrandSummaryPayload:
        """Legacy Strand Summary (PBIX ord 15): one tile per Strand.

        A per-strand card repeater — strand banner, "# Questions"/"# Standards"
        text echoes, a within-strand correct%-per-standard chart, and the
        Adopted/Revised date footer. The legacy page carries NO KPI-card strip,
        treemap, rollup table or band bars (those were non-legacy additions and
        are removed for parity). Per-strand grade_average =
        AVERAGE(cqso[Grade_Average]) (flat); # standards =
        DISTINCTCOUNT(cqso[Standards]) (by code); # questions =
        DISTINCTCOUNT(cqso[Question_No]).
        """
        meta = await self.cube.get_school_wide_meta() or {}
        strand_rows = await self.cube.get_school_strand_rollup(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
        )
        strands_rollup: list[StrandSummaryRollupRow] = []
        for row in strand_rows:
            strand_name = _decode_html(safe_str(row.get("strand")))
            if not strand_name:
                continue
            grade_avg = to_float(row.get("grade_average"))
            subjects_raw = row.get("subjects")
            subjects = [
                _decode_html(safe_str(s))
                for s in (subjects_raw if isinstance(subjects_raw, list) else [])
                if s
            ]
            strands_rollup.append(
                StrandSummaryRollupRow(
                    strand=strand_name,
                    num_standards=to_int(row.get("num_standards")),
                    num_questions=to_int(row.get("num_questions")),
                    grade_average=round(grade_avg, 6),
                    grade_average_pct=_format_pct(grade_avg),
                    incorrect_pct=round(max(0.0, 1.0 - grade_avg), 6),
                    subjects=subjects,
                )
            )

        std_rows = await self.cube.get_school_standard_rollup(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
            strand=filters.strand,
        )
        standards_rollup: list[StrandSummaryStandardRow] = [
            StrandSummaryStandardRow(
                strand=_decode_html(safe_str(r.get("strand"))),
                schoology_standard=safe_str(r.get("schoology_standard")),
                cluster=safe_str(r.get("cluster")),
                num_questions=to_int(r.get("num_questions")),
                grade_average=round(to_float(r.get("grade_average")), 6),
                grade_average_pct=_format_pct(to_float(r.get("grade_average"))),
            )
            for r in std_rows
            if safe_str(r.get("schoology_standard"))
        ]

        school = YTDSchoolInfo(
            name=safe_str(meta.get("name")),
            logo_url=meta.get("logo_url") or None,
            current_session=safe_str(meta.get("current_session")),
        )
        data_refreshed_at = (await self.cube.get_school_data_refreshed_at()) or ""

        quality = await self.cube.get_school_alignment_quality(
            session_filter=filters.session,
            subject=filters.subject,
            grade=filters.grade,
            category=filters.category,
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
            strands_rollup=strands_rollup,
            standards_rollup=standards_rollup,
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
