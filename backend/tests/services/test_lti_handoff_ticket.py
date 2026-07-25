"""C — handoff ticket mint + consume (DB fixtures).

Locks the SINGLE-USE invariant of the session-handoff bridge: a minted ticket is
opaque + short-lived (60s), consumes to exactly one identity payload, and can
NEVER be consumed twice, after expiry, or forged. This is the last hop between a
verified LTI launch and a real Supabase session — a replayable ticket would be a
session-forgery primitive.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy import text

from app.services.lti_service import LtiService

from ._lti_fixtures import (
    insert_handoff_ticket,
    lti_fixture,
    make_synthetic_user,
    now_utc,
)

EMAIL = "wave4-handoff@test.lti"


async def _provisioned_user(fx) -> str:
    """Create a synthetic auth user linked to the fixture registration.

    The lti_user_identity link ensures the fixture teardown reaps this user (and
    its tickets/memberships) with the rest of the synthetic graph.
    """
    user_id = await make_synthetic_user(fx.session, EMAIL)
    await fx.session.execute(
        text(
            "INSERT INTO lti_user_identity (registration_id, sub, user_id) "
            "VALUES (CAST(:rid AS UUID), :sub, CAST(:uid AS UUID))"
        ),
        {"rid": fx.registration_id, "sub": f"wave4-{secrets.token_hex(6)}", "uid": user_id},
    )
    await fx.session.commit()
    return user_id


async def test_mint_creates_unconsumed_short_lived_opaque_ticket():
    async with lti_fixture() as fx:
        svc = LtiService(fx.session)
        user_id = await _provisioned_user(fx)

        ticket = await svc.mint_handoff_ticket(user_id, fx.school_id, EMAIL)

        # Opaque: a long, high-entropy token (secrets.token_urlsafe(32)).
        assert isinstance(ticket, str) and len(ticket) >= 32

        row = (
            await fx.session.execute(
                text(
                    "SELECT consumed, "
                    "  extract(epoch FROM (expires_at - now())) AS ttl "
                    "FROM lti_handoff_ticket WHERE ticket = :t"
                ),
                {"t": ticket},
            )
        ).first()
        assert row is not None
        assert row._mapping["consumed"] is False
        # expires_at ≈ now()+60s (generous band for clock/exec jitter).
        assert 30 <= row._mapping["ttl"] <= 60


async def test_consume_valid_returns_identity_and_marks_consumed():
    async with lti_fixture() as fx:
        svc = LtiService(fx.session)
        user_id = await _provisioned_user(fx)
        ticket = await svc.mint_handoff_ticket(user_id, fx.school_id, EMAIL)

        result = await svc.consume_handoff_ticket(ticket)
        assert result == {"user_id": user_id, "email": EMAIL, "school_id": fx.school_id}

        consumed = (
            await fx.session.execute(
                text("SELECT consumed FROM lti_handoff_ticket WHERE ticket = :t"),
                {"t": ticket},
            )
        ).scalar_one()
        assert consumed is True


async def test_replay_second_consume_returns_none():
    async with lti_fixture() as fx:
        svc = LtiService(fx.session)
        user_id = await _provisioned_user(fx)
        ticket = await svc.mint_handoff_ticket(user_id, fx.school_id, EMAIL)

        assert await svc.consume_handoff_ticket(ticket) is not None
        # Replay: the single-use guard must reject the second consume.
        assert await svc.consume_handoff_ticket(ticket) is None


async def test_expired_ticket_returns_none_and_stays_unconsumed():
    async with lti_fixture() as fx:
        svc = LtiService(fx.session)
        user_id = await _provisioned_user(fx)
        # Insert a ticket that already expired 10s ago.
        ticket = await insert_handoff_ticket(
            fx.session,
            user_id=user_id,
            school_id=fx.school_id,
            email=EMAIL,
            expires_at=now_utc() - timedelta(seconds=10),
        )

        assert await svc.consume_handoff_ticket(ticket) is None
        # The atomic guard (WHERE ... expires_at > now()) must NOT have flipped
        # consumed — an expired ticket is untouched, not silently "used up".
        consumed = (
            await fx.session.execute(
                text("SELECT consumed FROM lti_handoff_ticket WHERE ticket = :t"),
                {"t": ticket},
            )
        ).scalar_one()
        assert consumed is False


async def test_forged_random_ticket_returns_none():
    async with lti_fixture() as fx:
        svc = LtiService(fx.session)
        assert await svc.consume_handoff_ticket(f"forged-{secrets.token_urlsafe(24)}") is None
