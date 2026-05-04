"""User role request schemas for input validation."""

from pydantic import BaseModel, Field


class AssignUserRoleRequest(BaseModel):
    """Request body for assigning a role to a user."""

    role_id: str = Field(..., description="Role ID to assign")
