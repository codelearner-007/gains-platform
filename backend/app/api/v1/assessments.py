"""Assessment listing + drill-down endpoints."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.middleware.rls import get_db_with_rls
from app.schemas.assessments import (
    AssessmentDetail,
    AssessmentSummary,
    AssessmentSummaryPage,
)
from app.schemas.reports import (
    IncorrectChoice,
    QuestionOverall,
    StandardSummaryRow,
)
from app.services.assessment_service import (
    DEFAULT_SUMMARY_PAGE_SIZE,
    AssessmentService,
)

router = APIRouter(prefix="/assessments", tags=["Assessments"])


@router.get(
    "/summary-list",
    response_model=AssessmentSummaryPage,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def list_assessment_summaries(
    session: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    subject: Optional[str] = Query(default=None),
    grade: Optional[str] = Query(default=None),
    section: Optional[str] = Query(default=None),
    instructor: Optional[str] = Query(default=None, max_length=200),
    q: Optional[str] = Query(default=None, max_length=200),
    sort: str = Query(default="date"),
    dir: str = Query(default="desc"),
    limit: int = Query(default=DEFAULT_SUMMARY_PAGE_SIZE, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_with_rls),
) -> AssessmentSummaryPage:
    """One server-paginated page of the dashboard's By-Assessment grid (per-item
    grade average + student count) plus the full filter-scoped total. Supports
    server-side name search (``q``), sort (date/item/grade/students/average +
    ``dir``) and ``limit``/``offset`` so a school with thousands of assessments
    only transfers one page. ``sort``/``dir`` are validated in the service (which
    owns the column whitelist). Requires: reports:read"""
    q_norm = q.strip() if q and q.strip() else None
    service = AssessmentService(db)
    return await service.list_assessment_summaries(
        session_filter=session,
        category=category,
        subject=subject,
        grade=grade,
        section=section,
        instructor=instructor,
        q=q_norm,
        sort=sort,
        direction=dir,
        limit=limit,
        offset=offset,
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
