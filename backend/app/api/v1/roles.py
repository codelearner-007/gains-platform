"""Role management endpoints."""

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, require_permission
from app.schemas.auth import CurrentUser
from app.schemas.request.role import (
    CreateRoleRequest,
    UpdateRolePermissionsRequest,
    UpdateRoleRequest,
)
from app.schemas.response.permission import PermissionResponse
from app.schemas.response.role import RoleResponse, RoleWithPermissionsResponse
from app.services.audit_service import AuditService
from app.services.role_service import RoleService

router = APIRouter(prefix="/roles", tags=["Roles"])


@router.get(
    "",
    response_model=List[RoleResponse],
    dependencies=[Depends(require_permission("roles:read"))],
)
async def list_roles(
    db: AsyncSession = Depends(get_db),
) -> List[RoleResponse]:
    """List all roles. Requires: roles:read"""
    service = RoleService(db)
    roles = await service.list_roles()
    return [RoleResponse.model_validate(role) for role in roles]


@router.post(
    "",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("roles:create"))],
)
async def create_role(
    role_data: CreateRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> RoleResponse:
    """Create a new role. Requires: roles:create"""
    service = RoleService(db)
    role = await service.create_role(role_data, current_user)

    audit_service = AuditService(db)
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="role_created",
        module="roles",
        resource_id=role.id,
        details={"role_name": role.name, "hierarchy_level": role.hierarchy_level},
    )

    return RoleResponse.model_validate(role)


@router.get(
    "/{role_id}",
    response_model=RoleWithPermissionsResponse,
    dependencies=[Depends(require_permission("roles:read"))],
)
async def get_role(
    role_id: str,
    db: AsyncSession = Depends(get_db),
) -> RoleWithPermissionsResponse:
    """Get role details with permissions. Requires: roles:read"""
    service = RoleService(db)
    role = await service.get_role_with_permissions(role_id)

    permissions = [
        PermissionResponse.model_validate(rp.permission) for rp in role.role_permissions
    ]

    response_data = RoleResponse.model_validate(role).model_dump()
    response_data["permissions"] = permissions

    return RoleWithPermissionsResponse(**response_data)


@router.patch(
    "/{role_id}",
    response_model=RoleResponse,
    dependencies=[Depends(require_permission("roles:update"))],
)
async def update_role(
    role_id: str,
    role_data: UpdateRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> RoleResponse:
    """Update a role. Requires: roles:update"""
    service = RoleService(db)
    role = await service.update_role(role_id, role_data, current_user)

    audit_service = AuditService(db)
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="role_updated",
        module="roles",
        resource_id=role.id,
        details=role_data.model_dump(exclude_unset=True),
    )

    return RoleResponse.model_validate(role)


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("roles:delete"))],
)
async def delete_role(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete a role. Requires: roles:delete"""
    service = RoleService(db)
    role = await service.get_role(role_id)

    await service.delete_role(role_id, current_user)

    audit_service = AuditService(db)
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="role_deleted",
        module="roles",
        resource_id=role_id,
        details={"role_name": role.name},
    )


@router.get(
    "/{role_id}/permissions",
    response_model=List[PermissionResponse],
    dependencies=[Depends(require_permission("roles:read"))],
)
async def get_role_permissions(
    role_id: str,
    db: AsyncSession = Depends(get_db),
) -> List[PermissionResponse]:
    """Get permissions for a role. Requires: roles:read"""
    service = RoleService(db)
    role = await service.get_role_with_permissions(role_id)

    return [
        PermissionResponse.model_validate(rp.permission) for rp in role.role_permissions
    ]


@router.put(
    "/{role_id}/permissions",
    response_model=List[PermissionResponse],
    dependencies=[Depends(require_permission("roles:update"))],
)
async def update_role_permissions(
    role_id: str,
    permissions_data: UpdateRolePermissionsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[PermissionResponse]:
    """Bulk update role permissions (replaces existing). Requires: roles:update"""
    service = RoleService(db)
    role = await service.assign_permissions(
        role_id, permissions_data.permission_ids, current_user
    )

    audit_service = AuditService(db)
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="role_permissions_updated",
        module="roles",
        resource_id=role_id,
        details={"permission_ids": permissions_data.permission_ids},
    )

    return [
        PermissionResponse.model_validate(rp.permission) for rp in role.role_permissions
    ]
