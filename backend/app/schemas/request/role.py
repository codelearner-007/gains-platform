"""Role request schemas for input validation."""

from typing import List

from pydantic import BaseModel, Field


class CreateRoleRequest(BaseModel):
    """Request body for creating a new role."""

    name: str = Field(..., min_length=2, max_length=50, description="Role name")
    description: str | None = Field(None, description="Role description")
    # No rank field: new roles append as the most-junior custom role; seniority
    # is set only by drag-and-drop reorder.


class UpdateRoleRequest(BaseModel):
    """Request body for updating an existing role (partial update)."""

    name: str | None = Field(None, min_length=2, max_length=50)
    description: str | None = None
    # No rank field: seniority changes only via /roles/reorder.


class UpdateRolePermissionsRequest(BaseModel):
    """Request body for bulk-replacing role permissions."""

    permission_ids: List[str] = Field(
        ..., description="List of permission IDs to assign to the role"
    )


class RoleReorderRequest(BaseModel):
    """Request body for drag-and-drop role reordering.

    ``ordered_role_ids`` = exactly the custom roles the caller may manage
    (strictly junior to them), most-senior first. The server recomputes the
    contiguous ordinal ranks; system roles and any senior roles are never
    touched.
    """

    ordered_role_ids: List[str] = Field(..., min_length=1, max_length=500)
