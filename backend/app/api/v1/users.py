"""User management endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_permission
from app.schemas.common import PaginatedResponse
from app.schemas.response.user import UserStatsResponse, UserWithRolesResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/stats",
    response_model=UserStatsResponse,
    dependencies=[Depends(require_permission("users:read_all"))],
)
async def get_user_stats(
    db: AsyncSession = Depends(get_db),
) -> UserStatsResponse:
    """Get user statistics. Requires: users:read_all"""
    service = UserService(db)
    return await service.get_stats()


@router.get(
    "/with-roles",
    response_model=PaginatedResponse[UserWithRolesResponse],
    dependencies=[Depends(require_permission("users:read_all"))],
)
async def list_users_with_roles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: Optional[str] = Query(None),
    email_verified: Optional[bool] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[UserWithRolesResponse]:
    """List users with pagination, filtering, and embedded roles. Requires: users:read_all"""
    service = UserService(db)
    return await service.list_users_with_roles(
        page=page, page_size=page_size,
        role=role, email_verified=email_verified,
        status=status, search=search,
    )
