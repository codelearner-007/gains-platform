"""Bulk user provisioning — assign role + grant school memberships.

Composes the existing ``UserRoleService`` (idempotent, hierarchy-validated role
assignment) and ``UserSchoolService`` (school-existence-validated membership
grant) so the invite flow can provision many users in one request. Each
assignment is applied independently: one user's failure (hierarchy violation,
missing/inactive school, …) is captured and reported, never aborting the rest.
"""

from __future__ import annotations

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.auth import CurrentUser
from app.schemas.request.user_provision import (
    BulkProvisionResponse,
    ProvisionAssignment,
    ProvisionResult,
)
from app.services.user_role_service import UserRoleService
from app.services.user_school_service import UserSchoolService


class UserProvisioningService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.role_service = UserRoleService(session)
        self.school_service = UserSchoolService(session)

    async def bulk_provision(
        self, assignments: List[ProvisionAssignment], actor: CurrentUser
    ) -> BulkProvisionResponse:
        results: List[ProvisionResult] = []
        for a in assignments:
            try:
                if a.role_id:
                    await self.role_service.assign_role(a.user_id, a.role_id, actor)
                # First granted school becomes the user's primary.
                for i, school_id in enumerate(a.school_ids):
                    await self.school_service.grant(
                        user_id=a.user_id,
                        school_id=school_id,
                        school_role=a.school_role,
                        is_primary=(i == 0),
                    )
                results.append(ProvisionResult(user_id=a.user_id, ok=True))
            except Exception as exc:  # noqa: BLE001 — report per-user, never abort the batch
                results.append(
                    ProvisionResult(user_id=a.user_id, ok=False, error=str(exc))
                )
        return BulkProvisionResponse(results=results)
