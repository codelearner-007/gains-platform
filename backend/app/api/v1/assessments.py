"""Assessment listing + drill-down endpoints."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.middleware.rls import get_db_with_rls
from app.schemas.assessments import (
    AssessmentDetail,
    AssessmentListRow,
    AssessmentSummary,
    AssessmentSummaryListRow,
)
from app.schemas.reports import (
    IncorrectChoice,
    QuestionOverall,
    StandardSummaryRow,
)
from app.services.assessment_service import AssessmentService

router = APIRouter(prefix="/assessments", tags=["Assessments"])


@router.get(
    "",
    response_model=List[AssessmentListRow],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def list_assessments(
    session: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    subject: Optional[str] = Query(default=None),
    grade: Optional[str] = Query(default=None),
    section: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db_with_rls),
) -> List[AssessmentListRow]:
    """List dim_item filtered for the user's school. Requires: reports:read"""
    service = AssessmentService(db)
    return await service.list_assessments(
        session_filter=session,
        category=category,
        subject=subject,
        grade=grade,
        section=section,
    )


@router.get(
    "/summary-list",
    response_model=List[AssessmentSummaryListRow],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def list_assessment_summaries(
    session: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    subject: Optional[str] = Query(default=None),
    grade: Optional[str] = Query(default=None),
    section: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db_with_rls),
) -> List[AssessmentSummaryListRow]:
    """Assessment list with per-item grade average + student count for the
    dashboard's By-Assessment grade-average bars (one batched rollup, no N+1).
    Requires: reports:read"""
    service = AssessmentService(db)
    return await service.list_assessment_summaries(
        session_filter=session,
        category=category,
        subject=subject,
        grade=grade,
        section=section,
    )


@router.get(
    "/{item_id}",
    response_model=AssessmentDetail,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def get_assessment(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> AssessmentDetail:
    """Single assessment metadata. Requires: reports:read"""
    service = AssessmentService(db)
    return await service.get_assessment(item_id)


@router.get(
    "/{item_id}/summary",
    response_model=AssessmentSummary,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def get_assessment_summary(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> AssessmentSummary:
    """Per-assessment aggregate (cube_school_summary + cube_grade_summary)."""
    service = AssessmentService(db)
    return await service.get_summary(item_id)


@router.get(
    "/{item_id}/questions",
    response_model=List[QuestionOverall],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def get_assessment_questions(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> List[QuestionOverall]:
    """cube_question_summary_overall slice for one assessment."""
    service = AssessmentService(db)
    return await service.get_questions(item_id)


@router.get(
    "/{item_id}/standards",
    response_model=List[StandardSummaryRow],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def get_assessment_standards(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> List[StandardSummaryRow]:
    """cube_standard_summary join dim_standard for one assessment."""
    service = AssessmentService(db)
    return await service.get_standards(item_id)


@router.get(
    "/{item_id}/incorrect-choices",
    response_model=List[IncorrectChoice],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def get_assessment_incorrect_choices(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> List[IncorrectChoice]:
    """cube_questionincorrectchoice_summary slice for one assessment."""
    service = AssessmentService(db)
    return await service.get_incorrect_choices(item_id)
