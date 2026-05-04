"""Profile response schemas for API output serialization."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProfileResponse(BaseModel):
    """Response schema for user profile."""

    id: str
    user_id: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    department: Optional[str] = None
    timezone: Optional[str] = None
    preferences: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
