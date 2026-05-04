"""Authentication response schemas for API output serialization."""

from typing import List

from pydantic import BaseModel, EmailStr


class CurrentUserResponse(BaseModel):
    """Response schema for GET /auth/me endpoint."""

    user_id: str
    email: EmailStr
    user_role: str
    hierarchy_level: int
    permissions: List[str]
