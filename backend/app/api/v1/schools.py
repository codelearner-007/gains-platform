"""User-facing schools endpoints (the school switcher).

Distinct from ``admin/schools.py`` (CRUD, gated on ``schools:*``). Any
authenticated user may list the schools they can scope to: super-admins get
every active school, members get only the schools they belong to. This drives
the tenant switcher in the app shell.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.schemas.auth import CurrentUser
from app.services.school_service import SchoolService

router = APIRouter(prefix="/schools", tags=["Schools"])


class AccessibleSchool(BaseModel):
    school_id: str
    name: str
    short_name: str
    is_active: bool


@router.get("/accessible", response_model=List[AccessibleSchool])
async def list_accessible_schools(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[AccessibleSchool]:
    """Schools the current user may scope to (drives the switcher)."""
    service = SchoolService(db)
    rows = await service.list_accessible(
        is_super_admin=current_user.is_super_admin,
        school_ids=current_user.school_ids,
    )
    return [AccessibleSchool(**r) for r in rows]
