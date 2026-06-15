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

Tenant resolution (claim-driven)
--------------------------------
The authenticated user's school membership is injected into the JWT by
``custom_access_token_hook`` as ``school_ids`` / ``primary_school_id`` /
``is_super_admin``. Resolution order for the active tenant:

1. ``?school_id=<uuid>`` override — super-admins may scope to ANY school;
   members may only scope to a school they belong to (else 403).
2. The member's ``primary_school_id`` claim.
3. Super-admins with no membership and no override fall back to Athenian
   (env ``DEFAULT_SCHOOL_BUILDING_ID``) so the admin/pilot surface is unblocked.
4. Otherwise no tenant is set, and RLS returns zero rows (fail-closed).
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.schemas.auth import CurrentUser

logger = logging.getLogger(__name__)

# Super-admin fallback: a cross-tenant operator with no membership and no
# explicit ?school_id scopes to Athenian so the admin/pilot surface is unblocked.
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

    Resolution order (see module docstring):

    1. ``?school_id=<uuid>`` override — super-admin → any; member → only a
       school they belong to (else HTTP 403).
    2. The member's ``primary_school_id`` JWT claim.
    3. Super-admin fallback to Athenian.
    4. ``None`` → RLS returns no rows (fail-closed).
    """

    # 1) explicit query-param override
    qp_school_id = request.query_params.get("school_id")
    if qp_school_id and _is_valid_uuid(qp_school_id):
        if current_user.can_access_school(qp_school_id):
            return qp_school_id
        # A member explicitly asked for a school they don't belong to. Fail
        # loudly rather than silently downgrading to their own tenant.
        logger.warning(
            "user_id=%s attempted to scope to unauthorized school_id=%s",
            current_user.user_id,
            qp_school_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to that school.",
        )

    # 2) member's primary school from the JWT claim
    if current_user.primary_school_id and _is_valid_uuid(
        current_user.primary_school_id
    ):
        return current_user.primary_school_id

    # 3) super-admin fallback to Athenian (cross-tenant operator, no membership)
    if current_user.is_super_admin:
        return await _get_fallback_school_id(session)

    # 4) no resolvable tenant — fail closed
    return None


async def set_school_id_for_session(
    request: Request,
    session: AsyncSession,
    current_user: CurrentUser,
) -> Optional[str]:
    """Set ROLE + ``app.current_school_id`` GUC on the session for RLS.

    Fail-closed: we ALWAYS switch to the ``authenticated`` role first, even when
    no tenant resolves. The connecting role may be a superuser (``postgres``)
    that bypasses RLS entirely; if we returned early without switching, a user
    with no resolvable school would see *every* tenant's rows. With the role
    switched and no GUC set, ``current_setting('app.current_school_id', true)``
    is NULL and every per-tenant policy matches zero rows.
    """
    school_id = await _resolve_school_id(request, current_user, session)

    # Drop superuser bypass so RLS engages no matter what (fail-closed).
    # SET LOCAL resets when the connection returns to the pool.
    await session.execute(text("SET LOCAL ROLE authenticated"))

    if not school_id or not _is_valid_uuid(school_id):
        return None

    # NB: Postgres does NOT allow bind parameters in SET / SET LOCAL. The UUID
    # is validated above, so embedding it in the statement is safe.
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
