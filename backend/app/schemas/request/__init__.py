"""Request schemas for API input validation."""

from app.schemas.request.permission import CreatePermissionRequest
from app.schemas.request.profile import UpdateProfileRequest
from app.schemas.request.role import (
    CreateRoleRequest,
    UpdateRolePermissionsRequest,
    UpdateRoleRequest,
)
from app.schemas.request.user_role import AssignUserRoleRequest

__all__ = [
    "CreatePermissionRequest",
    "CreateRoleRequest",
    "UpdateRoleRequest",
    "UpdateRolePermissionsRequest",
    "AssignUserRoleRequest",
    "UpdateProfileRequest",
]
