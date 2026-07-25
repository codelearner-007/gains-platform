"""Admin-dynamic LTI binding management (logic layer).

Lets an admin onboard a school's LTI 1.3 binding entirely from the dashboard:
paste the district's client_id + deployment_id, hand three tool URLs back, and
flip the per-school enable — no CLI, no SQL.

Registration reuse: a district installs the GAINS app once and gets ONE
client_id; several of its schools then bind distinct deployment_ids under that
same registration. So ``save_school_lti`` reuses an existing registration keyed
on (issuer, client_id) and only mints a fresh tool keypair when the
registration is new. Keypair generation + the Schoology default URLs come from
``lti_service`` (single source), never duplicated here.
"""

from __future__ import annotations

import os
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.lti_repository import LtiRepository
from app.services.lti_service import SCHOOLOGY_DEFAULTS, generate_tool_keypair

# Origin the tool is reachable at (same var the public LTI router uses). The
# three tool URLs handed to the district are derived from this.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:3000")


class LtiAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = LtiRepository(session)

    def tool_urls(self, tool_kid: Optional[str] = None) -> dict:
        """The three URLs an admin copies back to the district's Schoology app.

        Derived from PUBLIC_BASE_URL so they always match where the tool is
        actually served. ``tool_kid`` is included when the school is bound (the
        district may need it to pin the tool key).
        """
        base = PUBLIC_BASE_URL.rstrip("/")
        return {
            "login_init": f"{base}/api/v1/lti/login",
            "launch": f"{base}/api/v1/lti/launch",
            "jwks": f"{base}/api/v1/lti/.well-known/jwks.json",
            "tool_kid": tool_kid,
        }

    async def get_school_lti(self, school_id: str) -> dict:
        """Return the school's binding, or an empty (unbound) shape for display."""
        binding = await self.repo.get_binding_for_school(school_id)
        return {
            "school_id": school_id,
            "bound": binding is not None,
            "binding": binding,
        }

    async def save_school_lti(
        self,
        *,
        school_id: str,
        client_id: str,
        deployment_id: str,
        issuer: Optional[str] = None,
        platform_name: Optional[str] = None,
        is_active: bool = True,
    ) -> dict:
        """Create/reuse the registration, then (re)bind the school's deployment.

        Returns the fresh binding (via get_school_lti). No tool_private_key ever
        surfaces in the return value.
        """
        issuer = issuer or SCHOOLOGY_DEFAULTS["issuer"]

        existing = await self.repo.get_registration_by_issuer_client(issuer, client_id)
        if existing:
            registration_id = existing["registration_id"]
        else:
            tool_private_key, tool_kid = generate_tool_keypair()
            registration_id = await self.repo.insert_registration(
                issuer=issuer,
                client_id=client_id,
                platform_name=platform_name or "Schoology",
                auth_login_url=SCHOOLOGY_DEFAULTS["auth_login_url"],
                auth_token_url=SCHOOLOGY_DEFAULTS["auth_token_url"],
                jwks_url=SCHOOLOGY_DEFAULTS["jwks_url"],
                tool_private_key=tool_private_key,
                tool_kid=tool_kid,
            )

        await self.repo.upsert_deployment(
            registration_id=registration_id,
            deployment_id=deployment_id,
            school_id=school_id,
            is_active=is_active,
        )
        # NB: no commit here — the router writes the audit-log row and issues a
        # SINGLE commit so the binding change + its audit entry persist
        # atomically (matches admin/schools.py). get_school_lti reads back the
        # still-uncommitted write within this same session, which is correct.
        return await self.get_school_lti(school_id)

    async def delete_school_lti(self, school_id: str) -> None:
        """Unbind the school (delete its deployment; keep the registration).

        No commit here — the router commits the delete together with its
        audit-log row atomically (matches admin/schools.py).
        """
        await self.repo.delete_deployment_for_school(school_id)
