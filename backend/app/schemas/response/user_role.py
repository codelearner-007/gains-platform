"""User role response schemas for API output serialization."""

from app.schemas.common import CreatedAtSchema
from app.schemas.response.role import RoleResponse


class UserRoleResponse(CreatedAtSchema):
    """Response schema for a user-role assignment."""

    id: str
    user_id: str
    role_id: str
    role: RoleResponse

    model_config = {"from_attributes": True}
