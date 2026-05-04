"""Response schemas for API output serialization."""

from app.schemas.response.audit import AuditLogResponse
from app.schemas.response.auth import CurrentUserResponse
from app.schemas.response.dashboard import DashboardStatsResponse
from app.schemas.response.permission import (
    PermissionResponse,
    PermissionsGroupedByModuleResponse,
)
from app.schemas.response.profile import ProfileResponse
from app.schemas.response.role import RoleResponse, RoleWithPermissionsResponse
from app.schemas.response.user import UserStatsResponse, UserWithRolesResponse
from app.schemas.response.user_role import UserRoleResponse

__all__ = [
    "AuditLogResponse",
    "CurrentUserResponse",
    "DashboardStatsResponse",
    "PermissionResponse",
    "PermissionsGroupedByModuleResponse",
    "ProfileResponse",
    "RoleResponse",
    "RoleWithPermissionsResponse",
    "UserRoleResponse",
    "UserStatsResponse",
    "UserWithRolesResponse",
]
