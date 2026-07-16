"""User management endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user, get_db, require_permission
from app.core.rate_limit import limiter
from app.schemas.auth import CurrentUser
from app.schemas.common import PaginatedResponse
from app.schemas.request.user_provision import (
    BulkProvisionRequest,
    BulkProvisionResponse,
)
from app.schemas.response.user import UserStatsResponse, UserWithRolesResponse
from app.services.user_provisioning_service import UserProvisioningService
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
    school_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[UserWithRolesResponse]:
    """List users with pagination, filtering, and embedded roles + schools.

    ``school_id`` narrows to users who hold a membership in that school.
    Requires: users:read_all
    """
    service = UserService(db)
    return await service.list_users_with_roles(
        page=page, page_size=page_size,
        role=role, email_verified=email_verified,
        status=status, search=search, school_id=school_id,
    )


@router.post(
    "/bulk/provision",
    response_model=BulkProvisionResponse,
    dependencies=[Depends(require_permission("users:assign_roles"))],
)
@limiter.limit(settings.RATE_LIMIT_USER_ROLES_ASSIGN)
async def bulk_provision_users(
    request: Request,
    body: BulkProvisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> BulkProvisionResponse:
    """Assign a role + grant school memberships for many users in one call.

    Used by the multi-email invite flow after the invites are sent. Each
    assignment is hierarchy-validated (via the same services as the single-user
    routes) and applied independently — per-user results are returned so a
    partial failure is surfaced, never swallowed. Requires: users:assign_roles.
    """
    service = UserProvisioningService(db)
    return await service.bulk_provision(body.assignments, current_user)
