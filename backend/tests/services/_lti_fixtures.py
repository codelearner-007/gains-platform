"""Shared, self-cleaning DB fixtures for the Wave-4 LTI security suite.

SAFETY CONTRACT (STRICT — see the suite task spec + the historic-lock template
in ``tests/jobs/test_historic_lock.py``):

  * Every row this helper writes carries a SYNTHETIC sentinel identity
    (``TEST_ISSUER`` / ``TEST_CLIENT`` for registrations; a random ``sub`` /
    ``ticket`` / ``state`` per test) that can NEVER collide with the seeded
    Schoology template (client_id ``REPLACE_AFTER_SCHOOLOGY_INSTALL``) or any
    real tenant data.
  * The LTI service methods under test COMMIT (mint/consume/_consume_state are
    single-statement atomic guards that must be durable), so we cannot rely on a
    rollback-only session. Instead the fixture commits its synthetic rows and
    guarantees deletion in a ``finally`` — reverse-FK order, by EXACT key — so
    the before/after counts of every lti_* / auth.users / user_schools table are
    identical.
  * A FRESH throwaway engine per test binds to THIS test's event loop (the app's
    global session manager caches a pool tied to the loop it was first used on;
    reusing it across pytest-asyncio's per-test loops raises "attached to a
    different loop"). The engine is disposed in ``finally``.
  * NEVER TRUNCATE, NEVER ``session_replication_role=replica``, NEVER a blanket
    delete. Only the exact synthetic keys are removed.
"""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.services.lti_service import generate_tool_keypair

# Sentinel platform identity. Fixed so a stray row (if a test crashed mid-run)
# is still deletable by these constants, and unmistakably NOT the seeded
# Schoology template.
TEST_ISSUER = "https://test.lti/wave4-security"
TEST_CLIENT = "wave4-test-client"
TEST_DEPLOYMENT = "wave4-test-deployment-1"


@asynccontextmanager
async def fresh_session() -> AsyncGenerator[AsyncSession, None]:
    """A DB session on a FRESH engine bound to THIS test's event loop."""
    url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url, poolclass=None)
    try:
        async with AsyncSession(engine) as session:
            yield session
    finally:
        await engine.dispose()


async def _a_real_school_id(session: AsyncSession) -> str:
    """A real school_id to satisfy the lti_deployment FK. Read-only."""
    row = (
        await session.execute(text("SELECT school_id::text FROM schools LIMIT 1"))
    ).first()
    assert row is not None, "no schools in local DB — cannot run LTI fixtures"
    return row[0]


@dataclass
class LtiFixture:
    session: AsyncSession
    registration_id: str
    school_id: str
    deployment_id: str
    tool_private_key: str
    tool_kid: str


async def _purge_synthetic(session: AsyncSession) -> None:
    """Delete EVERY synthetic row (reverse-FK order) by sentinel identity.

    Idempotent belt-and-suspenders cleanup: safe even if a prior test aborted
    mid-way. auth.users rows we provisioned carry the sentinel deployment/issuer
    in their linked lti_user_identity, so we reap them via that join, then the
    registration (its ON DELETE CASCADE FKs mop up identities + launch sessions).
    """
    # handoff tickets + memberships + auth users provisioned under our identities
    await session.execute(
        text(
            "DELETE FROM lti_handoff_ticket WHERE user_id IN ("
            "  SELECT ui.user_id FROM lti_user_identity ui "
            "  JOIN lti_registration r ON r.id = ui.registration_id "
            "  WHERE r.issuer = :iss)"
        ),
        {"iss": TEST_ISSUER},
    )
    await session.execute(
        text(
            "DELETE FROM user_schools WHERE user_id IN ("
            "  SELECT ui.user_id FROM lti_user_identity ui "
            "  JOIN lti_registration r ON r.id = ui.registration_id "
            "  WHERE r.issuer = :iss)"
        ),
        {"iss": TEST_ISSUER},
    )
    await session.execute(
        text(
            "DELETE FROM auth.users WHERE id IN ("
            "  SELECT ui.user_id FROM lti_user_identity ui "
            "  JOIN lti_registration r ON r.id = ui.registration_id "
            "  WHERE r.issuer = :iss)"
        ),
        {"iss": TEST_ISSUER},
    )
    # registration delete cascades lti_deployment / lti_launch_session /
    # lti_user_identity (all FK registration_id ON DELETE CASCADE).
    await session.execute(
        text("DELETE FROM lti_registration WHERE issuer = :iss"),
        {"iss": TEST_ISSUER},
    )
    await session.commit()


@asynccontextmanager
async def lti_fixture(
    *, is_active: bool = True, with_deployment: bool = True
) -> AsyncGenerator[LtiFixture, None]:
    """Insert a synthetic registration (+deployment) bound to a real school.

    Yields their ids; deletes EXACTLY what it created (reverse-FK) in teardown,
    even on failure. ``is_active`` controls the deployment binding's off-switch
    for the per-school fail-close test.
    """
    async with fresh_session() as session:
        try:
            # Pre-clean any residue from a crashed prior run under our sentinel.
            await _purge_synthetic(session)

            tool_key, tool_kid = generate_tool_keypair(kid_prefix="wave4-test")
            school_id = await _a_real_school_id(session)
            reg_row = await session.execute(
                text(
                    "INSERT INTO lti_registration (issuer, client_id, platform_name, "
                    "auth_login_url, auth_token_url, jwks_url, tool_private_key, tool_kid) "
                    "VALUES (:iss, :cid, 'Wave4Test', "
                    "  'https://test.lti/auth', 'https://test.lti/token', "
                    "  'https://test.lti/jwks', :key, :kid) "
                    "RETURNING id::text"
                ),
                {"iss": TEST_ISSUER, "cid": TEST_CLIENT, "key": tool_key, "kid": tool_kid},
            )
            registration_id = reg_row.first()[0]

            if with_deployment:
                await session.execute(
                    text(
                        "INSERT INTO lti_deployment "
                        "(registration_id, deployment_id, school_id, is_active) "
                        "VALUES (:rid, :did, CAST(:sid AS UUID), :active)"
                    ),
                    {
                        "rid": registration_id,
                        "did": TEST_DEPLOYMENT,
                        "sid": school_id,
                        "active": is_active,
                    },
                )
            await session.commit()

            yield LtiFixture(
                session=session,
                registration_id=registration_id,
                school_id=school_id,
                deployment_id=TEST_DEPLOYMENT,
                tool_private_key=tool_key,
                tool_kid=tool_kid,
            )
        finally:
            # Guaranteed teardown — remove every synthetic row by sentinel key.
            await _purge_synthetic(session)


async def insert_handoff_ticket(
    session: AsyncSession,
    *,
    user_id: str,
    school_id: Optional[str],
    email: str,
    expires_at: datetime,
    consumed: bool = False,
) -> str:
    """Insert a handoff-ticket row directly (for expiry/replay control).

    Returns the opaque ticket string. Cleaned up by ``_purge_synthetic`` via the
    owning synthetic auth.user, or by the caller if it inserted a bespoke user.
    """
    ticket = f"wave4-{secrets.token_urlsafe(24)}"
    await session.execute(
        text(
            "INSERT INTO lti_handoff_ticket "
            "(ticket, user_id, school_id, email, consumed, expires_at) "
            "VALUES (:t, CAST(:u AS UUID), :s, :e, :c, :exp)"
        ),
        {
            "t": ticket,
            "u": user_id,
            "s": school_id,
            "e": email,
            "c": consumed,
            "exp": expires_at,
        },
    )
    await session.commit()
    return ticket


async def make_synthetic_user(session: AsyncSession, email: str) -> str:
    """Provision a minimal synthetic auth.users row; returns its id.

    Mirrors LtiService._create_auth_user's NOT-NULL-string columns so GoTrue's
    schema scan is satisfied. Reaped by ``_purge_synthetic`` only when linked via
    lti_user_identity; standalone users must be deleted by the caller's fixture.
    """
    row = await session.execute(
        text(
            """
            INSERT INTO auth.users (
                id, instance_id, aud, role, email, email_confirmed_at,
                raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
                confirmation_token, recovery_token, email_change,
                email_change_token_new, email_change_token_current,
                phone_change, phone_change_token, reauthentication_token)
            VALUES (
                uuid_generate_v7(), '00000000-0000-0000-0000-000000000000',
                'authenticated', 'authenticated', CAST(:email AS text), now(),
                '{"provider":"lti","providers":["lti"]}'::jsonb,
                '{}'::jsonb, now(), now(),
                '', '', '', '', '', '', '', '')
            RETURNING id::text
            """
        ),
        {"email": email},
    )
    await session.commit()
    return row.first()[0]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
