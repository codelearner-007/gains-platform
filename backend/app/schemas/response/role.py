"""Role response schemas for API output serialization."""

from typing import List


from app.schemas.common import TimestampSchema
from app.schemas.response.permission import PermissionResponse


class RoleResponse(TimestampSchema):
    """Response schema for a single role."""

    id: str
    name: str
    description: str | None = None
    hierarchy_level: int = 0
    is_system: bool = False

    model_config = {"from_attributes": True}


class RoleWithPermissionsResponse(RoleResponse):
    """Response schema for a role with its assigned permissions."""

    permissions: List[PermissionResponse]

    model_config = {"from_attributes": True}
