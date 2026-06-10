"""Per-school membership endpoints (grant / list / revoke).

Owns ``public.user_schools`` writes. Distinct from:
  * ``user_roles.py`` — platform RBAC role assignment (super_admin/user);
  * ``admin/schools.py`` — the schools (tenant) catalog CRUD.

The acting admin's authority is the JWT permission claim (enforced by
``require_permission``); the target ``user_id`` (path) + ``school_id`` (body)
are validated server-side. A member can never grant themselves a school — the
gate is ``users:assign_roles``, which members do not hold.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user, get_db, require_permission
from app.core.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.core.rate_limit import limiter
from app.schemas.auth import CurrentUser
from app.schemas.request.user_school import GrantUserSchoolRequest
from app.schemas.response.user_school import UserSchoolResponse
from app.services.audit_service import AuditService
from app.services.user_school_service import UserSchoolService

router = APIRouter(prefix="/users", tags=["User Schools"])


@router.get(
    "/{user_id}/schools",
    response_model=List[UserSchoolResponse],
)
async def list_user_schools(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[UserSchoolResponse]:
    """List a user's school memberships.

    Users may view their own memberships; viewing another user's requires
    ``users:read_all``.
    """
    if user_id != current_user.user_id and not current_user.has_permission(
        "users:read_all"
    ):
        raise PermissionDeniedError("users:read_all")

    service = UserSchoolService(db)
    rows = await service.list_memberships(user_id)
    return [UserSchoolResponse.model_validate(r) for r in rows]


@router.post(
    "/{user_id}/schools",
    response_model=UserSchoolResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("users:assign_roles"))],
)
@limiter.limit(settings.RATE_LIMIT_USER_ROLES_ASSIGN)
async def grant_user_school(
    request: Request,
    user_id: str,
    payload: GrantUserSchoolRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UserSchoolResponse:
    """Grant a user access to a school. Requires: users:assign_roles

    The ``school_id`` is validated server-side (must exist + be active). The
    one-primary-per-user invariant is enforced.
    """
    service = UserSchoolService(db)
    membership = await service.grant(
        user_id=user_id,
        school_id=payload.school_id,
        school_role=payload.school_role,
        is_primary=payload.is_primary,
    )

    audit = AuditService(db)
    await audit.log_action(
        user_id=current_user.user_id,
        action="user_school_granted",
        module="user_schools",
        resource_id=membership["id"],
        details={
            "target_user_id": user_id,
            "school_id": payload.school_id,
            "school_role": payload.school_role,
            "is_primary": payload.is_primary,
        },
    )

    return UserSchoolResponse.model_validate(membership)


@router.delete(
    "/{user_id}/schools/{school_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("users:assign_roles"))],
)
@limiter.limit(settings.RATE_LIMIT_USER_ROLES_REMOVE)
async def revoke_user_school(
    request: Request,
    user_id: str,
    school_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Revoke a user's access to a school. Requires: users:assign_roles"""
    service = UserSchoolService(db)
    deleted = await service.revoke(user_id, school_id)
    if not deleted:
        raise ResourceNotFoundError("UserSchool", school_id)

    audit = AuditService(db)
    await audit.log_action(
        user_id=current_user.user_id,
        action="user_school_revoked",
        module="user_schools",
        resource_id=None,
        details={"target_user_id": user_id, "school_id": school_id},
    )
