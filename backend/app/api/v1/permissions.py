"""Permission management endpoints."""

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, require_permission
from app.schemas.auth import CurrentUser
from app.schemas.request.permission import CreatePermissionRequest
from app.schemas.response.permission import (
    PermissionResponse,
    PermissionsGroupedByModuleResponse,
)
from app.services.audit_service import AuditService
from app.services.permission_service import PermissionService

router = APIRouter(prefix="/permissions", tags=["Permissions"])


@router.get(
    "",
    response_model=List[PermissionsGroupedByModuleResponse],
    dependencies=[Depends(require_permission("permissions:read"))],
)
async def list_permissions_grouped(
    db: AsyncSession = Depends(get_db),
) -> List[PermissionsGroupedByModuleResponse]:
    """List all permissions grouped by module. Requires: permissions:read"""
    service = PermissionService(db)
    grouped = await service.list_grouped_by_module()

    return [
        PermissionsGroupedByModuleResponse(
            module=module,
            permissions=[PermissionResponse.model_validate(p) for p in permissions],
        )
        for module, permissions in grouped.items()
    ]


@router.post(
    "",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("permissions:create"))],
)
async def create_permission(
    permission_data: CreatePermissionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PermissionResponse:
    """Create a new permission. Requires: permissions:create"""
    service = PermissionService(db)
    permission = await service.create_permission(permission_data)

    audit_service = AuditService(db)
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="permission_created",
        module="permissions",
        resource_id=permission.id,
        details={"permission_name": permission.name, "permission_module": permission.module},
    )

    return PermissionResponse.model_validate(permission)


@router.delete(
    "/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("permissions:delete"))],
)
async def delete_permission(
    permission_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete a permission. Requires: permissions:delete"""
    service = PermissionService(db)
    permission = await service.get_permission(permission_id)

    await service.delete_permission(permission_id)

    audit_service = AuditService(db)
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="permission_deleted",
        module="permissions",
        resource_id=permission_id,
        details={"permission_name": permission.name},
    )
