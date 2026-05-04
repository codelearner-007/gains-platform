"""Role request schemas for input validation."""

from typing import List

from pydantic import BaseModel, Field


class CreateRoleRequest(BaseModel):
    """Request body for creating a new role."""

    name: str = Field(..., min_length=2, max_length=50, description="Role name")
    description: str | None = Field(None, description="Role description")
    hierarchy_level: int = Field(
        default=0,
        ge=0,
        le=100000,
        description="Hierarchy level (higher = more privileged). New roles default to 0 until configured.",
    )


class UpdateRoleRequest(BaseModel):
    """Request body for updating an existing role (partial update)."""

    name: str | None = Field(None, min_length=2, max_length=50)
    description: str | None = None
    hierarchy_level: int | None = Field(None, ge=0, le=100000)


class UpdateRolePermissionsRequest(BaseModel):
    """Request body for bulk-replacing role permissions."""

    permission_ids: List[str] = Field(
        ..., description="List of permission IDs to assign to the role"
    )
