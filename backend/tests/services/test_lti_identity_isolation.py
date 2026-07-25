"""H1 — LTI identity isolation: a launch can NEVER merge onto a pre-existing account.

THE INVARIANT: an LTI launch authenticates ONLY as the LTI-provisioned account for
its exact (registration_id, sub). It can never resolve to / create-as / mint a
session for any pre-existing non-LTI (password / staff / invited) account — even
when the platform's signed id_token carries a claim ``email`` that exactly matches
that account's email.

THE FIX UNDER TEST: ``provision`` derives the AUTH-account email from
``synthetic_lti_email(registration_id, sub)`` (registration-namespaced sha256), NOT
from the claim email. So ``_create_auth_user``'s bare ``WHERE email =`` lookup can
only ever hit the LTI account for this (reg, sub); the colliding victim email is
never consulted for lookup, creation, the identity row, or the handoff ticket.

Self-cleaning (mirrors ``_lti_fixtures`` discipline — reverse-FK, key-scoped, NEVER
truncate): the LTI-created account is reaped by the fixture teardown via its
``lti_user_identity`` link; the standalone pre-seeded victim account (which has NO
identity link) is deleted here by its EXACT email key in a ``finally``.
"""

from __future__ import annotations

from sqlalchemy import text

from app.services.lti_service import LtiService, synthetic_lti_email

from ._lti_fixtures import lti_fixture, make_synthetic_user

# A pre-existing NON-LTI account (think: an invited staff member or password user)
# whose email the attacker replays inside a signed LTI id_token to try to take over.
VICTIM_EMAIL = "victim-staff@school.test"


def _claims(sub: str, *, deployment_id: str, email: str) -> dict:
    """A minimal verified-claims dict as validate_launch would return."""
    return {
        "sub": sub,
        "email": email,
        "name": "Attacker Display Name",
        "https://purl.imsglobal.org/spec/lti/claim/deployment_id": deployment_id,
        "https://purl.imsglobal.org/spec/lti/claim/roles": [
            "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
        ],
        "https://purl.imsglobal.org/spec/lti/claim/context": {"label": "Course-101"},
    }


async def _delete_victim(session) -> None:
    await session.execute(
        text("DELETE FROM user_schools WHERE user_id IN "
             "(SELECT id FROM auth.users WHERE email = :e)"),
        {"e": VICTIM_EMAIL},
    )
    await session.execute(
        text("DELETE FROM auth.users WHERE email = :e"), {"e": VICTIM_EMAIL}
    )
    await session.commit()


async def test_colliding_claim_email_does_not_merge_onto_preexisting_account():
    """The core H1 proof: a claim email equal to a pre-existing account's email
    yields a DISTINCT, LTI-namespaced account — never the victim's id."""
    async with lti_fixture(is_active=True) as fx:
        try:
            # Belt-and-suspenders: clear any residue from a crashed prior run.
            await _delete_victim(fx.session)

            # Pre-seed the NON-LTI victim account with the exact email the attacker
            # will replay in the signed claim.
            victim_id = await make_synthetic_user(fx.session, VICTIM_EMAIL)

            svc = LtiService(fx.session)
            sub = "attacker-sub-collision"
            result = await svc.provision(
                fx.registration_id,
                _claims(sub, deployment_id=fx.deployment_id, email=VICTIM_EMAIL),
            )

            # (1) The provisioned account is NOT the victim account.
            assert result.user_id != victim_id, (
                "ACCOUNT TAKEOVER: LTI launch merged onto a pre-existing account"
            )

            # (2) Its identity email is the deterministic synthetic value, never the
            # claim email.
            expected = synthetic_lti_email(fx.registration_id, sub)
            assert result.email == expected
            assert result.email != VICTIM_EMAIL

            # (3) The auth.users row actually carries the synthetic email (so the
            # bridge's generateLink(email) can only ever resolve THIS account).
            db_email = (
                await fx.session.execute(
                    text("SELECT email FROM auth.users WHERE id = CAST(:u AS UUID)"),
                    {"u": result.user_id},
                )
            ).first()[0]
            assert db_email == expected

            # (4) The victim account is untouched (still its own email, no LTI
            # membership grafted onto it).
            victim_email = (
                await fx.session.execute(
                    text("SELECT email FROM auth.users WHERE id = CAST(:u AS UUID)"),
                    {"u": victim_id},
                )
            ).first()[0]
            assert victim_email == VICTIM_EMAIL
        finally:
            await _delete_victim(fx.session)


async def test_relaunch_same_reg_sub_is_idempotent_same_account():
    """Determinism guard: re-launching the same (reg, sub) resolves to the SAME
    LTI account (no fork), because the synthetic email is deterministic."""
    async with lti_fixture(is_active=True) as fx:
        svc = LtiService(fx.session)
        sub = "returning-teacher-sub"
        first = await svc.provision(
            fx.registration_id,
            _claims(sub, deployment_id=fx.deployment_id, email="teacher@real.example"),
        )
        # Second launch with a DIFFERENT claim email but the same (reg, sub) must
        # land on the same account (claim email is display-only, not identity).
        second = await svc.provision(
            fx.registration_id,
            _claims(sub, deployment_id=fx.deployment_id, email="renamed@real.example"),
        )
        assert first.user_id == second.user_id
        assert first.email == second.email == synthetic_lti_email(fx.registration_id, sub)
