"""Repository for the ``public.user_schools`` membership table.

This is the single data-access path for per-school membership grant/revoke.
Like ``SchoolRepository`` it runs over the service-role connection (the FastAPI
worker connects as ``postgres`` and bypasses RLS); authorization is enforced in
the API/service layer (``users:read_all`` / ``users:assign_roles``), NEVER from
client-supplied tenant context.

Writes mirror the LTI provisioning upsert (``lti_service.provision``) so the two
membership-creation paths stay consistent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repository import row_to_dict

_MEMBERSHIP_COLUMNS = (
    "id::text AS id, "
    "user_id::text AS user_id, "
    "school_id::text AS school_id, "
    "school_role, is_primary, created_at, updated_at"
)


class UserSchoolRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        """All of a user's memberships, joined with the school name/short_name."""
        sql = text(
            """
            SELECT
                us.id::text AS id,
                us.user_id::text AS user_id,
                us.school_id::text AS school_id,
                us.school_role, us.is_primary, us.created_at, us.updated_at,
                s.name AS school_name, s.short_name AS school_short_name,
                s.is_active AS school_is_active
            FROM public.user_schools us
            JOIN public.schools s ON s.school_id = us.school_id
            WHERE us.user_id = CAST(:uid AS uuid)
            ORDER BY us.is_primary DESC, s.name
            """
        )
        result = await self.session.execute(sql, {"uid": user_id})
        return [dict(r._mapping) for r in result.all()]

    async def list_by_users(
        self, user_ids: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Bulk-fetch memberships for many users, grouped by user_id.

        Mirrors ``UserRoleRepository.list_by_users`` so the admin users list can
        embed each user's schools without an N+1 per-row lookup.
        """
        if not user_ids:
            return {}
        sql = text(
            """
            SELECT
                us.user_id::text AS user_id,
                us.school_id::text AS school_id,
                us.school_role, us.is_primary,
                s.name AS school_name, s.short_name AS school_short_name
            FROM public.user_schools us
            JOIN public.schools s ON s.school_id = us.school_id
            WHERE us.user_id::text = ANY(:uids)
            ORDER BY us.is_primary DESC, s.name
            """
        )
        result = await self.session.execute(sql, {"uids": list(user_ids)})
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for r in result.all():
            m = dict(r._mapping)
            grouped.setdefault(m["user_id"], []).append(m)
        return grouped

    async def get(self, user_id: str, school_id: str) -> Optional[Dict[str, Any]]:
        sql = text(
            f"""
            SELECT {_MEMBERSHIP_COLUMNS}
            FROM public.user_schools
            WHERE user_id = CAST(:uid AS uuid) AND school_id = CAST(:sid AS uuid)
            LIMIT 1
            """
        )
        result = await self.session.execute(sql, {"uid": user_id, "sid": school_id})
        row = result.first()
        return row_to_dict(row) if row else None

    async def clear_primary_for_user(self, user_id: str) -> None:
        """Demote any existing primary membership for the user.

        Keeps the one-primary-per-user partial unique index satisfiable before
        promoting a new primary in the same transaction.
        """
        await self.session.execute(
            text(
                "UPDATE public.user_schools SET is_primary = FALSE, "
                "updated_at = now() WHERE user_id = CAST(:uid AS uuid) AND is_primary"
            ),
            {"uid": user_id},
        )

    async def upsert(
        self, user_id: str, school_id: str, school_role: str, is_primary: bool
    ) -> Dict[str, Any]:
        """Grant (or update) a membership.

        ON CONFLICT mirrors ``lti_service.provision``: re-granting an existing
        membership updates its role/primary flag rather than erroring.
        """
        sql = text(
            f"""
            INSERT INTO public.user_schools (user_id, school_id, school_role, is_primary)
            VALUES (CAST(:uid AS uuid), CAST(:sid AS uuid), :role, :primary)
            ON CONFLICT (user_id, school_id)
            DO UPDATE SET
                school_role = EXCLUDED.school_role,
                is_primary  = EXCLUDED.is_primary,
                updated_at  = now()
            RETURNING {_MEMBERSHIP_COLUMNS}
            """
        )
        result = await self.session.execute(
            sql,
            {"uid": user_id, "sid": school_id, "role": school_role, "primary": is_primary},
        )
        row = result.first()
        return row_to_dict(row)

    async def delete(self, user_id: str, school_id: str) -> bool:
        result = await self.session.execute(
            text(
                "DELETE FROM public.user_schools "
                "WHERE user_id = CAST(:uid AS uuid) AND school_id = CAST(:sid AS uuid)"
            ),
            {"uid": user_id, "sid": school_id},
        )
        return result.rowcount > 0
