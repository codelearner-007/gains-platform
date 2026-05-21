"""Authentication and authorization schemas."""

from typing import List

from pydantic import BaseModel, EmailStr


class CurrentUser(BaseModel):
    """Current authenticated user with permissions."""

    user_id: str
    email: EmailStr
    user_role: str
    hierarchy_level: int
    permissions: List[str]

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        return permission in self.permissions


