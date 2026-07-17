"""Request/response schemas for bulk user provisioning.

Used by the invite flow: after the Next.js route sends the Supabase invite
emails and gets back the new user ids, the client makes ONE call to
``POST /api/v1/users/bulk/provision`` to assign the platform role and grant
school memberships for every invited user in a single round-trip (replacing the
old per-user, per-school sequential N+1). Each assignment is applied
independently and reported individually so a partial failure is never silent.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ProvisionAssignment(BaseModel):
    """Role + school memberships to apply to one already-created user."""

    user_id: str
    role_id: Optional[str] = None
    school_ids: List[str] = Field(default_factory=list)
    school_role: str = "member"


class BulkProvisionRequest(BaseModel):
    assignments: List[ProvisionAssignment] = Field(..., min_length=1, max_length=50)


class ProvisionResult(BaseModel):
    user_id: str
    ok: bool
    error: Optional[str] = None


class BulkProvisionResponse(BaseModel):
    results: List[ProvisionResult]
