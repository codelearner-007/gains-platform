"""Permission request schemas for input validation."""

from pydantic import BaseModel, Field, field_validator


class CreatePermissionRequest(BaseModel):
    """Request body for creating a new permission."""

    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Permission name in module:action format (e.g., 'users:read_all')",
    )
    description: str | None = Field(None, description="Permission description")

    @field_validator("name")
    @classmethod
    def validate_name_format(cls, v: str) -> str:
        """Validate permission name is in module:action format."""
        if ":" not in v:
            raise ValueError("Permission name must be in 'module:action' format")
        parts = v.split(":")
        if len(parts) != 2 or not all(parts):
            raise ValueError("Permission name must have exactly one ':' separator")
        return v
