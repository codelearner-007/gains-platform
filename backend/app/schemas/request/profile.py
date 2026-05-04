"""Profile request schemas for input validation."""

from typing import Optional

from pydantic import BaseModel, Field


class UpdateProfileRequest(BaseModel):
    """Request body for updating a user profile (partial update)."""

    full_name: Optional[str] = Field(default=None, max_length=255)
    avatar_url: Optional[str] = Field(default=None, max_length=2048)
    department: Optional[str] = Field(default=None, max_length=100)
    timezone: Optional[str] = Field(default=None, max_length=100)
    preferences: Optional[dict] = Field(default=None)
