"""Admin endpoints for the schools (tenant) table."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, require_permission
from app.schemas.admin import (
    CreateSchoolRequest,
    SchoolResponse,
    UpdateSchoolRequest,
)
from app.schemas.auth import CurrentUser
from app.services.audit_service import AuditService
from app.services.school_service import SchoolService

router = APIRouter(prefix="/schools", tags=["Admin / Schools"])


@router.get(
    "",
    response_model=List[SchoolResponse],
    dependencies=[Depends(require_permission("schools:read_all"))],
)
async def list_schools(
    db: AsyncSession = Depends(get_db),
) -> List[SchoolResponse]:
    """List all schools. Requires: schools:read_all"""
    service = SchoolService(db)
    return await service.list_schools()


@router.get(
    "/{school_id}",
    response_model=SchoolResponse,
    dependencies=[Depends(require_permission("schools:read_all"))],
)
async def get_school(
    school_id: str,
    db: AsyncSession = Depends(get_db),
) -> SchoolResponse:
    """Get a single school. Requires: schools:read_all"""
    service = SchoolService(db)
    return await service.get_school(school_id)


@router.post(
    "",
    response_model=SchoolResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("schools:create"))],
)
async def create_school(
    payload: CreateSchoolRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SchoolResponse:
    """Create a school. Requires: schools:create"""
    service = SchoolService(db)
    school = await service.create_school(payload)

    audit = AuditService(db)
    await audit.log_action(
        user_id=current_user.user_id,
        action="school_created",
        module="schools",
        resource_id=school.school_id,
        details={"name": school.name, "schoology_building_id": school.schoology_building_id},
    )
    return school


@router.put(
    "/{school_id}",
    response_model=SchoolResponse,
    dependencies=[Depends(require_permission("schools:update"))],
)
async def update_school(
    school_id: str,
    payload: UpdateSchoolRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SchoolResponse:
    """Update a school. Requires: schools:update"""
    service = SchoolService(db)
    school = await service.update_school(school_id, payload)

    audit = AuditService(db)
    await audit.log_action(
        user_id=current_user.user_id,
        action="school_updated",
        module="schools",
        resource_id=school.school_id,
        details=payload.model_dump(exclude_unset=True),
    )
    return school
