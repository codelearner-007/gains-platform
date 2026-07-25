"""Data-access layer for admin-dynamic LTI binding management.

Operates on the LTI *infra* tables (lti_registration, lti_deployment) — these
carry no tenant column and are NOT under RLS, so this repository takes the same
privileged ``get_db`` session the LTI protocol service uses. It never selects
``tool_private_key`` on read paths: the tool's private key never leaves the
backend.

Router → Service → Repository → Database. The service owns keypair generation
and the Schoology default URLs; this layer is pure SQL.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class LtiRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_binding_for_school(self, school_id: str) -> Optional[dict]:
        """Return the deployment binding + its registration for a school.

        Joins lti_deployment → lti_registration. Returns None when the school has
        no binding. NEVER returns ``tool_private_key``.
        """
        row = await self.session.execute(
            text(
                "SELECT r.id::text AS registration_id, r.issuer, r.client_id, "
                "r.platform_name, r.tool_kid, "
                "d.deployment_id, d.is_active "
                "FROM lti_deployment d "
                "JOIN lti_registration r ON r.id = d.registration_id "
                "WHERE d.school_id = :sid LIMIT 1"
            ),
            {"sid": school_id},
        )
        r = row.first()
        return dict(r._mapping) if r else None

    async def get_registration_by_issuer_client(
        self, issuer: str, client_id: str
    ) -> Optional[dict]:
        """Look up a registration by its (issuer, client_id) unique key."""
        row = await self.session.execute(
            text(
                "SELECT id::text AS registration_id, issuer, client_id, "
                "platform_name, tool_kid FROM lti_registration "
                "WHERE issuer = :iss AND client_id = :cid LIMIT 1"
            ),
            {"iss": issuer, "cid": client_id},
        )
        r = row.first()
        return dict(r._mapping) if r else None

    async def insert_registration(
        self,
        *,
        issuer: str,
        client_id: str,
        platform_name: Optional[str],
        auth_login_url: str,
        auth_token_url: str,
        jwks_url: str,
        tool_private_key: str,
        tool_kid: str,
    ) -> str:
        """Insert a new registration, returning its id."""
        row = await self.session.execute(
            text(
                "INSERT INTO lti_registration (issuer, client_id, platform_name, "
                "auth_login_url, auth_token_url, jwks_url, tool_private_key, tool_kid) "
                "VALUES (:iss, :cid, :pname, :login, :token, :jwks, :pk, :kid) "
                "RETURNING id::text"
            ),
            {
                "iss": issuer,
                "cid": client_id,
                "pname": platform_name,
                "login": auth_login_url,
                "token": auth_token_url,
                "jwks": jwks_url,
                "pk": tool_private_key,
                "kid": tool_kid,
            },
        )
        return row.first()[0]

    async def upsert_deployment(
        self,
        *,
        registration_id: str,
        deployment_id: str,
        school_id: str,
        is_active: bool,
    ) -> None:
        """Bind (or rebind) a deployment to a school, keyed on the
        (registration_id, deployment_id) unique constraint."""
        await self.session.execute(
            text(
                "INSERT INTO lti_deployment "
                "(registration_id, deployment_id, school_id, is_active) "
                "VALUES (:rid, :did, :sid, :active) "
                "ON CONFLICT (registration_id, deployment_id) DO UPDATE SET "
                "school_id = EXCLUDED.school_id, is_active = EXCLUDED.is_active"
            ),
            {
                "rid": registration_id,
                "did": deployment_id,
                "sid": school_id,
                "active": is_active,
            },
        )

    async def delete_deployment_for_school(self, school_id: str) -> None:
        """Delete a school's deployment binding.

        Leaves the registration in place — a district client_id may back several
        schools' deployments, and the registration also publishes the tool key.
        """
        await self.session.execute(
            text("DELETE FROM lti_deployment WHERE school_id = :sid"),
            {"sid": school_id},
        )
