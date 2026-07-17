"""User response schemas for API output serialization."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator

from app.schemas.response.user_role import UserRoleResponse


class UserStatsResponse(BaseModel):
    """User statistics for admin dashboard."""

    total_users: int
    active_users: int
    banned_users: int
    verified_users: int
    new_users_30d: int


class UserSchoolBrief(BaseModel):
    """A user's school membership, embedded in admin user listings."""

    school_id: str
    school_name: str
    school_short_name: str | None = None
    school_role: str
    is_primary: bool = False


class UserWithRolesResponse(BaseModel):
    """User with embedded roles + schools for admin user listings."""

    id: str
    email: str | None
    created_at: datetime | None
    updated_at: datetime | None
    last_sign_in_at: Optional[datetime] = None
    email_confirmed_at: Optional[datetime] = None
    banned_until: Optional[datetime] = None
    is_banned: bool = False
    roles: List[UserRoleResponse]
    schools: List[UserSchoolBrief] = []

    @field_validator("is_banned", mode="before")
    @classmethod
    def validate_is_banned(cls, v: object) -> bool:
        """Convert None to False for is_banned field."""
        return False if v is None else bool(v)
