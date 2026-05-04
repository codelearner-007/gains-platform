"""Permission response schemas for API output serialization."""

from pydantic import BaseModel

from app.schemas.common import CreatedAtSchema


class PermissionResponse(CreatedAtSchema):
    """Response schema for a single permission."""

    id: str
    module: str
    action: str
    name: str  # Computed property from model (module:action)
    description: str | None

    model_config = {"from_attributes": True}


class PermissionsGroupedByModuleResponse(BaseModel):
    """Response schema for permissions grouped by module name."""

    module: str
    permissions: list[PermissionResponse]
