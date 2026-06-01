"""Authentication and authorization schemas."""

from typing import List, Optional

from pydantic import BaseModel, EmailStr


class CurrentUser(BaseModel):
    """Current authenticated user with permissions and school membership."""

    user_id: str
    email: EmailStr
    user_role: str
    hierarchy_level: int
    permissions: List[str]
    # Multi-tenant membership (injected by the JWT claims hook).
    school_ids: List[str] = []
    primary_school_id: Optional[str] = None
    is_super_admin: bool = False

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        return permission in self.permissions

    def can_access_school(self, school_id: str) -> bool:
        """Whether this user may scope to the given tenant.

        Super-admins are cross-tenant and may access any school; members are
        restricted to schools they belong to.
        """
        return self.is_super_admin or school_id in self.school_ids


