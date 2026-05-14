"""Row-Level Security GUC middleware.

The Postgres RLS policies on every per-tenant table are of the form::

    USING (school_id = current_setting('app.current_school_id', true)::uuid)

For RLS to actually enforce we must:

1. Switch the session role from the connecting role (which may be a superuser
   like ``postgres`` that bypasses RLS) to ``authenticated`` (which does not
   bypass RLS).
2. Set the ``app.current_school_id`` GUC to the user's tenant UUID.

Both are done with ``SET LOCAL`` so they only apply for the current
transaction/connection-checkout — once the request completes and the session
goes back to the pool the next checkout starts clean.

Phase-5 tenant assignment fallback
----------------------------------
The platform's first phase only has one school (Athenian) wired up and the
JWT claim ``school_id`` is not yet populated. Until the Phase-7 onboarding
flow lands, every authenticated request maps to Athenian by looking up its
UUID by ``schoology_building_id``. Super-admins may pass ``?school_id=<uuid>``
to scope to a specific tenant; if they don't, they also fall through to the
Athenian fallback so the pilot page is unblocked.
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.schemas.auth import CurrentUser

logger = logging.getLogger(__name__)

# Phase-5 fallback: every authenticated user maps to Athenian until proper
# school assignment lands in Phase 7 (D6 onboarding flow).
ATHENIAN_BUILDING_ID = os.getenv("DEFAULT_SCHOOL_BUILDING_ID", "186370968")

# Process-lifetime cache of the Athenian fallback school_id. Populated on the
# first request that needs it; reset only by restarting the worker. The schools
# row is effectively immutable in pilot deployments, so the cache is safe.
_athenian_fallback_school_id: Optional[str] = None


async def _get_fallback_school_id(session: AsyncSession) -> Optional[str]:
    """Resolve (and memoize) the Athenian fallback school_id.

    Phase 7 will replace this with a JWT claim. Until then we hit the DB
    exactly once per worker process instead of once per request.
    """
    global _athenian_fallback_school_id
    if _athenian_fallback_school_id is not None:
        return _athenian_fallback_school_id
    result = await session.execute(
        text(
            "SELECT school_id FROM public.schools "
            "WHERE schoology_building_id = :bid LIMIT 1"
        ),
        {"bid": ATHENIAN_BUILDING_ID},
    )
    sid = result.scalar()
    if sid is None:
        return None
    _athenian_fallback_school_id = str(sid)
    return _athenian_fallback_school_id


def _is_valid_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


async def _resolve_school_id(
    request: Request,
    current_user: CurrentUser,
    session: AsyncSession,
) -> Optional[str]:
    """Resolve the tenant UUID to inject into ``app.current_school_id``.

    Resolution order:

    1. ``?school_id=<uuid>`` query parameter (super-admin only).
    2. Future: ``school_id`` JWT claim (not present in current schema).
    3. Athenian fallback (Phase-5 single-tenant MVP).
    """

    # 1) explicit query-param override (super_admin only)
    qp_school_id = request.query_params.get("school_id")
    if qp_school_id and _is_valid_uuid(qp_school_id):
        if current_user.user_role == "super_admin":
            return qp_school_id
        # Non-super_admins must not be allowed to spoof tenants via ?school_id=
        logger.warning(
            "non super_admin user_id=%s attempted school_id override",
            current_user.user_id,
        )

    # 2) JWT claim — TODO Phase 7. The current CurrentUser schema does not
    # carry school_id; once it does, plumb it here.

    # 3) Phase-5 fallback to Athenian (cached after first lookup)
    return await _get_fallback_school_id(session)


async def set_school_id_for_session(
    request: Request,
    session: AsyncSession,
    current_user: CurrentUser,
) -> Optional[str]:
    """Set ROLE + ``app.current_school_id`` GUC on the session for RLS."""
    school_id = await _resolve_school_id(request, current_user, session)
    if not school_id:
        return None

    # Switch role so RLS is enforced. SET LOCAL ROLE is reset at end of txn
    # but commit/rollback returns the connection to the pool fresh.
    #
    # NB: Postgres does NOT allow bind parameters in SET / SET LOCAL. We
    # validate the UUID earlier so embedding it in the SQL is safe.
    if not _is_valid_uuid(school_id):
        return None
    await session.execute(text("SET LOCAL ROLE authenticated"))
    await session.execute(
        text(f"SET LOCAL app.current_school_id = '{school_id}'")
    )
    return school_id


async def get_db_with_rls(
    request: Request,
    session: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AsyncSession:
    """Per-request DB dependency that enforces tenant RLS on the session.

    Use this anywhere a route reads from per-tenant tables (cubes, dims,
    fact). Routes that intentionally bypass RLS (admin schools list, ingestion
    runs, dim_standard / dim_strand global lookups) should depend on
    ``get_db`` directly.
    """
    await set_school_id_for_session(request, session, current_user)
    return session
