"""Business logic for per-school membership grant/revoke.

Authorization (``users:read_all`` / ``users:assign_roles``) is enforced by the
router. This service owns the server-side invariants:

  * the target ``school_id`` must EXIST and be ACTIVE (validated against the
    ``schools`` table — never trusted from the request);
  * exactly one primary school per user (the partial unique index backs this,
    but we demote the prior primary first so the grant doesn't fail).
"""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.repositories.school_repository import SchoolRepository
from app.repositories.user_school_repository import UserSchoolRepository


class UserSchoolService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserSchoolRepository(session)
        self.school_repo = SchoolRepository(session)

    async def list_memberships(self, user_id: str) -> List[Dict[str, Any]]:
        return await self.repo.list_for_user(user_id)

    async def grant(
        self,
        user_id: str,
        school_id: str,
        school_role: str,
        is_primary: bool,
    ) -> Dict[str, Any]:
        # Server-side validation: the school must exist and be active. This is
        # the no-client-trusted-school_id guarantee for the write path.
        school = await self.school_repo.get(school_id)
        if not school:
            raise ResourceNotFoundError("School", school_id)
        if not school.get("is_active"):
            raise ValidationError(
                "Cannot grant access to an inactive school.", field="school_id"
            )

        # Enforce the one-primary invariant before insert: demote any current
        # primary so the partial unique index never trips.
        if is_primary:
            await self.repo.clear_primary_for_user(user_id)

        await self.repo.upsert(
            user_id=user_id,
            school_id=school_id,
            school_role=school_role,
            is_primary=is_primary,
        )
        await self.session.commit()
        # Re-read the enriched (joined) row so the response carries school metadata.
        rows = await self.repo.list_for_user(user_id)
        match = next((r for r in rows if r["school_id"] == school_id), None)
        if match is None:  # pragma: no cover - upsert just succeeded
            raise ResourceNotFoundError("UserSchool", school_id)
        return match

    async def revoke(self, user_id: str, school_id: str) -> bool:
        deleted = await self.repo.delete(user_id, school_id)
        await self.session.commit()
        return deleted
