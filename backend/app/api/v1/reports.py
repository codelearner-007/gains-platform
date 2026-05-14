"""Composed report endpoints (Question-Response-Analysis, Standards Deep Dive)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.middleware.rls import get_db_with_rls
from app.schemas.reports import (
    IncorrectAnswerDetailsPayload,
    QuestionResponseAnalysisPayload,
    StandardSummaryFilters,
    StandardSummaryPayload,
    StandardsDeepDivePayload,
    StrandSummaryFilters,
    StrandSummaryPayload,
    YearToDatePerformancePayload,
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
    db: AsyncSession = Depends(get_db_with_rls),
) -> YearToDatePerformancePayload:
    """Cross-assessment, school-wide YTD performance dashboard.

    Composes timeline, grade distribution, student progression and a
    strand heatmap from cube_user_summary / cube_standard_summary.
    Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_year_to_date_performance()


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
    db: AsyncSession = Depends(get_db_with_rls),
) -> StrandSummaryPayload:
    """School-wide strand rollup (mirrors PBIX page #15).

    Aggregates cube_question_summary by strand across all assessments in
    the selected scope. All filter params optional; default = whole-school
    rollup. Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_strand_summary(
        StrandSummaryFilters(
            session=session,
            category=category,
            subject=subject,
            grade=grade,
            section=section,
        )
    )
