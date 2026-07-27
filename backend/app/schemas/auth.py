"""Authentication and authorization schemas."""

from typing import List, Optional

from pydantic import BaseModel


class CurrentUser(BaseModel):
    """Current authenticated user with permissions and school membership."""

    user_id: str
    # Plain str, not EmailStr: this is a trusted claim from our own JWT, not user
    # input, and LTI users carry a synthetic address (lti-<hash>@lti.local, see
    # synthetic_lti_email) whose reserved `.local` TLD EmailStr rejects — which
    # would 422 every authenticated request for an LTI user. Authorization never
    # uses email (only permissions/school_ids/is_super_admin).
    email: str
    user_role: str
    hierarchy_rank: int
    permissions: List[str]
    # Multi-tenant membership (injected by the JWT claims hook).
    school_ids: List[str] = []
    primary_school_id: Optional[str] = None
    is_super_admin: bool = False
    # True for Schoology-embedded (LTI-provisioned) accounts. Defaults False so an
    # absent claim (e.g. a token minted before the claim existed) is treated as a
    # normal account — the safe default for a lock-down (the middleware route wall
    # is the real enforcement; this flag gates account-mutation endpoints).
    is_lti_user: bool = False

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        return permission in self.permissions

    def can_access_school(self, school_id: str) -> bool:
        """Whether this user may scope to the given tenant.

        Super-admins are cross-tenant and may access any school; members are
        restricted to schools they belong to.
        """
        return self.is_super_admin or school_id in self.school_ids


