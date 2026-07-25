"""B — _resolve_school + per-school is_active gate (DB fixtures).

Locks the tenant-resolution invariant: a launch resolves to a bound school ONLY
when the (registration_id, deployment_id) binding exists AND is_active. This is
the per-school fail-close off-switch and the cross-registration isolation
boundary. We assert on the RESOLVED school_id value (not any redirect), because
that value is what gates membership provisioning and therefore every downstream
RLS read.
"""

from __future__ import annotations

from sqlalchemy import text

from app.services.lti_service import LtiService

from ._lti_fixtures import lti_fixture


async def test_active_binding_resolves_to_bound_school():
    async with lti_fixture(is_active=True) as fx:
        svc = LtiService(fx.session)
        resolved = await svc._resolve_school(fx.registration_id, fx.deployment_id)
        assert resolved == fx.school_id


async def test_unknown_deployment_resolves_to_none_no_leak():
    # A deployment_id that was never bound must resolve to None — never leak the
    # school of some OTHER binding under the same registration.
    async with lti_fixture(is_active=True) as fx:
        svc = LtiService(fx.session)
        resolved = await svc._resolve_school(fx.registration_id, "never-bound-xyz")
        assert resolved is None


async def test_inactive_binding_fails_closed_to_none():
    # The per-school off-switch: is_active=FALSE resolves to NO school even though
    # the (registration, deployment) pair genuinely exists. Assert on the
    # resolved value — this is the fail-close invariant.
    async with lti_fixture(is_active=False) as fx:
        svc = LtiService(fx.session)
        resolved = await svc._resolve_school(fx.registration_id, fx.deployment_id)
        assert resolved is None


async def test_reactivating_binding_restores_school():
    # Flip the off-switch back ON in the SAME row and confirm the school resolves
    # again — proves is_active is the sole gate, not some incidental state.
    async with lti_fixture(is_active=False) as fx:
        svc = LtiService(fx.session)
        assert await svc._resolve_school(fx.registration_id, fx.deployment_id) is None

        await fx.session.execute(
            text(
                "UPDATE lti_deployment SET is_active = TRUE "
                "WHERE registration_id = CAST(:rid AS UUID) AND deployment_id = :did"
            ),
            {"rid": fx.registration_id, "did": fx.deployment_id},
        )
        await fx.session.commit()

        resolved = await svc._resolve_school(fx.registration_id, fx.deployment_id)
        assert resolved == fx.school_id


async def test_wrong_registration_for_real_deployment_is_isolated():
    # Cross-registration isolation: a real deployment_id queried under a DIFFERENT
    # (random) registration_id must resolve to None. A registration must never see
    # another registration's deployment binding.
    async with lti_fixture(is_active=True) as fx:
        svc = LtiService(fx.session)
        foreign_registration = "00000000-0000-0000-0000-0000000000ff"
        resolved = await svc._resolve_school(foreign_registration, fx.deployment_id)
        assert resolved is None
