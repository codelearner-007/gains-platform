"""Authentication and authorization schemas."""

from typing import List

from pydantic import BaseModel, EmailStr, Field


class UserClaims(BaseModel):
    """JWT claims extracted from Supabase token."""

    user_id: str = Field(..., description="User UUID from auth.users")
    email: EmailStr = Field(..., description="User email address")
    user_role: str = Field(default="user", description="User's assigned role name")
    hierarchy_level: int = Field(default=100, description="Role hierarchy level")
    permissions: List[str] = Field(
        default_factory=list, description="List of permissions (e.g., 'users:read_all')"
    )


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

    def has_any_permission(self, permissions: List[str]) -> bool:
        """Check if user has any of the specified permissions."""
        return any(p in self.permissions for p in permissions)

    def has_all_permissions(self, permissions: List[str]) -> bool:
        """Check if user has all of the specified permissions."""
        return all(p in self.permissions for p in permissions)


