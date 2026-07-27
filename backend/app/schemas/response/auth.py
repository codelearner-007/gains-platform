"""Authentication response schemas for API output serialization."""

from typing import List

from pydantic import BaseModel


class CurrentUserResponse(BaseModel):
    """Response schema for GET /auth/me endpoint."""

    user_id: str
    # Plain str, not EmailStr: mirrors CurrentUser.email — this is the outbound
    # response_model for GET /api/v1/auth/me, and an LTI user's synthetic
    # lti-<hash>@lti.local address (reserved .local TLD) would fail EmailStr's
    # response validation -> 500. The value is a trusted, already-verified claim.
    email: str
    user_role: str
    hierarchy_rank: int
    permissions: List[str]
