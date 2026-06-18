"""Dimension lookup endpoints."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, require_permission
from app.middleware.rls import get_db_with_rls
from app.schemas.auth import CurrentUser
from app.schemas.dim import (
    AssessmentTypeRow,
    GradeRow,
    InstructorRow,
    SectionRow,
    SessionRow,
    StandardRow,
    StrandRow,
    SubjectRow,
)
from app.services.dim_service import DimService

router = APIRouter(prefix="/dim", tags=["Dimensions"])


@router.get(
    "/standards",
    response_model=List[StandardRow],
)
async def list_standards(
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[StandardRow]:
    """Global ``dim_standard`` lookup (no RLS). Cached for 1h."""
    service = DimService(db)
    rows = await service.list_standards()
    response.headers["Cache-Control"] = "public, max-age=3600"
    return rows


@router.get(
    "/strands",
    response_model=List[StrandRow],
)
async def list_strands(
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[StrandRow]:
    """Global ``dim_strand`` lookup (no RLS). Cached for 1h."""
    service = DimService(db)
    rows = await service.list_strands()
    response.headers["Cache-Control"] = "public, max-age=3600"
    return rows


@router.get(
    "/subjects",
    response_model=List[SubjectRow],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def list_subjects(
    db: AsyncSession = Depends(get_db_with_rls),
) -> List[SubjectRow]:
    """Per-school ``dim_subject`` lookup (RLS applied)."""
    service = DimService(db)
    return await service.list_subjects()


@router.get(
    "/grades",
    response_model=List[GradeRow],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def list_grades(
    db: AsyncSession = Depends(get_db_with_rls),
) -> List[GradeRow]:
    """Per-school ``dim_grade`` lookup (RLS applied)."""
    service = DimService(db)
    return await service.list_grades()


@router.get(
    "/sections",
    response_model=List[SectionRow],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def list_sections(
    db: AsyncSession = Depends(get_db_with_rls),
) -> List[SectionRow]:
    """Per-school ``dim_section`` lookup (RLS applied)."""
    service = DimService(db)
    return await service.list_sections()


@router.get(
    "/sessions",
    response_model=List[SessionRow],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def list_sessions(
    db: AsyncSession = Depends(get_db_with_rls),
) -> List[SessionRow]:
    """Per-school ``dim_session`` lookup (RLS applied)."""
    service = DimService(db)
    return await service.list_sessions()


@router.get(
    "/assessment-types",
    response_model=List[AssessmentTypeRow],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def list_assessment_types(
    db: AsyncSession = Depends(get_db_with_rls),
) -> List[AssessmentTypeRow]:
    """Distinct per-school ``assessment_type`` values (RLS applied)."""
    service = DimService(db)
    return await service.list_assessment_types()


@router.get(
    "/instructors",
    response_model=List[InstructorRow],
    dependencies=[Depends(require_permission("reports:read"))],
)
async def list_instructors(
    db: AsyncSession = Depends(get_db_with_rls),
) -> List[InstructorRow]:
    """Distinct classroom instructors parsed from ``section_instructors`` (RLS applied)."""
    service = DimService(db)
    return await service.list_instructors()
