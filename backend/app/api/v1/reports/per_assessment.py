"""Per-assessment report routes (item_id-scoped).

QRA, Standards Deep Dive, Incorrect Answer Details, QSR question-summary matrix,
and the three QRA paginated variants (paginated / by-teacher / by-standard+teacher).
Each route delegates to a single ``ReportService.build_*`` method. Paths, params,
response models and permissions are byte-identical to the former ``reports.py``.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.middleware.rls import get_db_with_rls
from app.schemas.reports import (
    IncorrectAnswerDetailsPayload,
    QraByStandardTeacherPayload,
    QraByTeacherPayload,
    QraPaginatedPayload,
    QuestionResponseAnalysisPayload,
    QuestionSummaryPointsPayload,
    StandardsDeepDivePayload,
)
from app.services.reports import ReportService

router = APIRouter()


@router.get(
    "/question-response-analysis/{item_id}",
    response_model=QuestionResponseAnalysisPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def question_response_analysis(
    item_id: str,
    instructor: Optional[str] = Query(None, max_length=2000),
    db: AsyncSession = Depends(get_db_with_rls),
) -> QuestionResponseAnalysisPayload:
    """Composed QRA payload matching frontend dataset.ts. Requires: reports:read

    ``instructor`` (OPTIONAL) is a single comma-separated string of section
    instructors (e.g. ``"Jane Doe,John Smith"``). When provided, the merged
    multi-section report is narrowed to the sections taught by ANY of the
    listed instructors. Empty/omitted = no filter (full merge, byte-identical).
    """
    instructor = instructor.strip() if instructor and instructor.strip() else None
    service = ReportService(db)
    return await service.build_question_response_analysis(item_id, instructor)


@router.get(
    "/standards-deep-dive/{item_id}",
    response_model=StandardsDeepDivePayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def standards_deep_dive(
    item_id: str,
    instructor: Optional[str] = Query(None, max_length=2000),
    db: AsyncSession = Depends(get_db_with_rls),
) -> StandardsDeepDivePayload:
    """Per-assessment SDD payload (mirrors PBIX page #16). Requires: reports:read

    ``instructor`` (OPTIONAL) is a single comma-separated string of section
    instructors (e.g. ``"Jane Doe,John Smith"``). When provided, the merged
    multi-section report is narrowed to the sections taught by ANY of the
    listed instructors. Empty/omitted = no filter (full merge, byte-identical).
    """
    instructor = instructor.strip() if instructor and instructor.strip() else None
    service = ReportService(db)
    return await service.build_standards_deep_dive(item_id, instructor)


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
    "/question-summary-paginated/{item_id}",
    response_model=QuestionSummaryPointsPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def question_summary_paginated(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> QuestionSummaryPointsPayload:
    """Per-(student × question) partial-credit matrix for the QSR paginated
    family (PBIX ord 6, 7, 16). Each cell is ``points_received`` (may be
    fractional); "# Correct Answers" is SUM(received) and every Score% is
    SUM(received)/SUM(possible) — matching the legacy SSRS PDFs, the xlsx
    export, and the grade-average KPI. Variants (base / teacher subtotal /
    redacted) are rendered from this same payload via query-string flags on
    the frontend. Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_question_summary_matrix_points(item_id)


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
