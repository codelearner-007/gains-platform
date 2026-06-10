"""Request schemas for per-school membership grant/revoke."""

from typing import Literal

from pydantic import BaseModel, Field

# Mirrors the CHECK constraint on public.user_schools.school_role.
SchoolRole = Literal["admin", "teacher", "student", "member"]


class GrantUserSchoolRequest(BaseModel):
    """Grant a user access to a specific school.

    The acting admin's authority comes from the JWT claim (``users:assign_roles``),
    never from this body. ``school_id`` is validated server-side against the
    ``schools`` table (must exist AND be active) before any write.
    """

    school_id: str = Field(..., description="Target school (tenant) UUID")
    school_role: SchoolRole = Field(
        default="member", description="The user's role WITHIN this school"
    )
    is_primary: bool = Field(
        default=False,
        description="Mark as the user's default school. Demotes any prior primary.",
    )
