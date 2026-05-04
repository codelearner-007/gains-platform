"""User role assignment endpoints."""

from typing import List

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user, get_db, require_permission
from app.core.exceptions import PermissionDeniedError
from app.core.rate_limit import limiter
from app.schemas.auth import CurrentUser
from app.schemas.request.user_role import AssignUserRoleRequest
from app.schemas.response.user_role import UserRoleResponse
from app.services.audit_service import AuditService
from app.services.user_role_service import UserRoleService

router = APIRouter(prefix="/users", tags=["User Roles"])


@router.get(
    "/{user_id}/roles",
    response_model=List[UserRoleResponse],
)
async def list_user_roles(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[UserRoleResponse]:
    """
    List all roles assigned to a user.

    Users can view their own roles. Viewing other users' roles requires users:read_all.
    """
    if user_id != current_user.user_id and not current_user.has_permission("users:read_all"):
        raise PermissionDeniedError("users:read_all")

    service = UserRoleService(db)
    user_roles = await service.list_user_roles(user_id)

    return [UserRoleResponse.model_validate(ur) for ur in user_roles]


@router.post(
    "/{user_id}/roles",
    response_model=UserRoleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("users:assign_roles"))],
)
@limiter.limit(settings.RATE_LIMIT_USER_ROLES_ASSIGN)
async def assign_role_to_user(
    request: Request,
    user_id: str,
    role_data: AssignUserRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UserRoleResponse:
    """Assign a role to a user. Requires: users:assign_roles"""
    service = UserRoleService(db)
    user_role = await service.assign_role(user_id, role_data.role_id, current_user)

    audit_service = AuditService(db)
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="user_role_assigned",
        module="user_roles",
        resource_id=user_role.id,
        details={"target_user_id": user_id, "role_id": role_data.role_id},
    )

    # Refresh to load role relationship
    await db.refresh(user_role, ["role"])

    return UserRoleResponse.model_validate(user_role)


@router.delete(
    "/{user_id}/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("users:assign_roles"))],
)
@limiter.limit(settings.RATE_LIMIT_USER_ROLES_REMOVE)
async def remove_role_from_user(
    request: Request,
    user_id: str,
    role_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Remove a role from a user. Requires: users:assign_roles"""
    service = UserRoleService(db)
    deleted = await service.remove_role(user_id, role_id, current_user)

    if deleted:
        audit_service = AuditService(db)
        await audit_service.log_action(
            user_id=current_user.user_id,
            action="user_role_removed",
            module="user_roles",
            resource_id=None,
            details={"target_user_id": user_id, "role_id": role_id},
        )
