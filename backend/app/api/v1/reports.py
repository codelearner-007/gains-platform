"""Composed report endpoints.

Each route here delegates to a single ``ReportService.build_*`` method.
The currently exposed reports are: Question Response Analysis Interactive,
Standards Deep Dive interactive, Incorrect Answer Details, Year To Date -
Longitudinal Report, Standard Summary, and Strand Summary.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.middleware.rls import get_db_with_rls
from app.schemas.reports import (
    AlignmentDataQualityReport,
    IncorrectAnswerDetailsPayload,
    QraByStandardTeacherPayload,
    QraByTeacherPayload,
    QraPaginatedPayload,
    QuestionResponseAnalysisPayload,
    QuestionSummaryMatrixPayload,
    StandardSummaryFilters,
    StandardSummaryPayload,
    StandardsDeepDivePayload,
    StrandSummaryFilters,
    StrandSummaryPayload,
    YearToDatePerformancePayload,
    YTDFilters,
)
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get(
    "/question-response-analysis/{item_id}",
    response_model=QuestionResponseAnalysisPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def question_response_analysis(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> QuestionResponseAnalysisPayload:
    """Composed QRA payload matching frontend dataset.ts. Requires: reports:read"""
    service = ReportService(db)
    return await service.build_question_response_analysis(item_id)


@router.get(
    "/standards-deep-dive/{item_id}",
    response_model=StandardsDeepDivePayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def standards_deep_dive(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StandardsDeepDivePayload:
    """Per-assessment SDD payload (mirrors PBIX page #16). Requires: reports:read"""
    service = ReportService(db)
    return await service.build_standards_deep_dive(item_id)


@router.get(
    "/incorrect-answer-details/{item_id}/{question_id}",
    response_model=IncorrectAnswerDetailsPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def incorrect_answer_details(
    item_id: str,
    question_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> IncorrectAnswerDetailsPayload:
    """Drill-through deep dive for a single question (PBIX page #20).

    Returns the assessment header, the question context (text, correct answer,
    standards, description), KPI strip, full distractor breakdown, and every
    student × answer attempt. Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_incorrect_answer_details(item_id, question_id)


@router.get(
    "/year-to-date-performance",
    response_model=YearToDatePerformancePayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def year_to_date_performance(
    session: Optional[str] = None,
    category: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    section: Optional[str] = None,
    db: AsyncSession = Depends(get_db_with_rls),
) -> YearToDatePerformancePayload:
    """Legacy YTD Longitudinal paginated matrix (PBIX ord 8/9/10 rdlVisual).

    POINTS-based per-(Classroom Instructor → Student) matrix with one column
    per standard assessed YTD, per-teacher subtotals, and grand totals — a
    faithful clone of the three legacy "Longitudinal Report - Year To Date"
    reports (the variant differences are purely client-side rendering). The
    report is one longitudinal unit per (session, grade, subject,
    assessment_type); ``category`` carries the assessment type. ``section`` is
    accepted for filter-bar compatibility but not applied at this grain.
    Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_year_to_date_performance(
        YTDFilters(
            session=session,
            category=category,
            subject=subject,
            grade=grade,
            section=section,
        )
    )


@router.get(
    "/standard-summary",
    response_model=StandardSummaryPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def standard_summary(
    session: Optional[str] = None,
    category: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    section: Optional[str] = None,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StandardSummaryPayload:
    """School-wide standards rollup (mirrors PBIX page #14).

    Aggregates cube_standard_summary across all assessments in the
    selected scope. All filter params optional; default = whole-school
    rollup. Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_standard_summary(
        StandardSummaryFilters(
            session=session,
            category=category,
            subject=subject,
            grade=grade,
            section=section,
        )
    )


@router.get(
    "/data-quality/standards-alignment",
    response_model=AlignmentDataQualityReport,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def standards_alignment_data_quality(
    db: AsyncSession = Depends(get_db_with_rls),
) -> AlignmentDataQualityReport:
    """Tenant-scoped audit of standards-alignment coverage per assessment.

    Surfaces assessments whose Schoology CSV shipped no ``Standards`` columns
    (because the underlying questions weren't aligned to learning objectives
    in Schoology), so admins know which items to flag back to teachers for
    alignment before SDD / Strand / Standard reports can populate.
    Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_alignment_data_quality()


@router.get(
    "/strand-summary",
    response_model=StrandSummaryPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def strand_summary(
    session: Optional[str] = None,
    category: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    section: Optional[str] = None,
    strand: Optional[str] = None,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StrandSummaryPayload:
    """School-wide strand rollup (mirrors PBIX page #15).

    Aggregates cube_question_summary by strand across all assessments in
    the selected scope. All filter params optional; default = whole-school
    rollup. The ``strand`` filter narrows the per-standard drill list
    when the client cross-filters on a strand selection. Requires:
    reports:read.
    """
    service = ReportService(db)
    return await service.build_strand_summary(
        StrandSummaryFilters(
            session=session,
            category=category,
            subject=subject,
            grade=grade,
            section=section,
            strand=strand,
        )
    )


# ─── Paginated reports (PBIX ord 6/7/16, 11, 12, 13) ──────────────────────


@router.get(
    "/question-summary-paginated/{item_id}",
    response_model=QuestionSummaryMatrixPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def question_summary_paginated(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> QuestionSummaryMatrixPayload:
    """Per-(student × question) matrix for the QSR paginated family
    (PBIX ord 6, 7, 16). Variants (base / teacher subtotal / header
    highlights) are rendered from the same payload via query-string flags
    on the frontend. Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_question_summary_matrix(item_id)


@router.get(
    "/question-response-analysis-paginated/{item_id}",
    response_model=QraPaginatedPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def question_response_analysis_paginated(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> QraPaginatedPayload:
    """PBIX ord 11. Flat list of questions with per-question student-name
    list for every incorrect answer. Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_qra_paginated(item_id)


@router.get(
    "/question-response-analysis-by-teacher/{item_id}",
    response_model=QraByTeacherPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def question_response_analysis_by_teacher(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> QraByTeacherPayload:
    """PBIX ord 12. Questions grouped by classroom instructor with per-teacher
    average shown in the group header. Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_qra_by_teacher(item_id)


@router.get(
    "/question-response-analysis-by-standard-and-teacher/{item_id}",
    response_model=QraByStandardTeacherPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def question_response_analysis_by_standard_and_teacher(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> QraByStandardTeacherPayload:
    """PBIX ord 13. Questions grouped by CPALMS standard then by classroom
    instructor, with both standard-wide and teacher-within-standard averages.
    Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_qra_by_standard_teacher(item_id)
