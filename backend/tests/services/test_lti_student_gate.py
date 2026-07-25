"""Q5 — student-privacy gate: only STAFF launches get a school membership.

THE EXPOSURE (regression-locked here): ``provision`` maps the IMS roles to a
school_role, but the membership row in ``user_schools`` is what actually grants
school-scoped RLS access to every school-wide + per-student report. Before the
gate, a LEARNER launch created that membership too — so a student who launched
the tool from Schoology could read every report a teacher can. GAINS surfaces
per-student performance analytics, so that is a hard student-privacy blocker.

THE GATE UNDER TEST: ``provision`` now writes ``user_schools`` ONLY when the
resolved role is staff (admin/teacher). A student (or any unknown role, which
``map_lti_roles`` floors to 'student') is still provisioned — auth.users row +
``lti_user_identity`` exist and a session can still be minted — but with ZERO
membership → empty school_ids in the JWT claims hook → RLS denies all report
data. This file is the lock that keeps the student path membership-free.

Self-cleaning (mirrors ``_lti_fixtures`` discipline — reverse-FK, key-scoped,
NEVER truncate): every account/identity/membership this file provisions is
reaped by the fixture teardown via the synthetic ``lti_user_identity`` link.
"""

from __future__ import annotations

from sqlalchemy import text

from app.services.lti_service import LtiService

from ._lti_fixtures import lti_fixture

# Real IMS LIS v2 membership URIs, exactly as Schoology sends them.
INSTRUCTOR = "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
LEARNER = "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner"
ADMINISTRATOR = "http://purl.imsglobal.org/vocab/lis/v2/membership#Administrator"


def _claims(sub: str, *, deployment_id: str, role_uri: str) -> dict:
    """A minimal verified-claims dict as validate_launch would return."""
    return {
        "sub": sub,
        "email": f"{sub}@real.example",
        "name": "Launch Display Name",
        "https://purl.imsglobal.org/spec/lti/claim/deployment_id": deployment_id,
        "https://purl.imsglobal.org/spec/lti/claim/roles": [role_uri],
        "https://purl.imsglobal.org/spec/lti/claim/context": {"label": "Course-101"},
    }


async def _membership_count(session, user_id: str) -> int:
    row = await session.execute(
        text("SELECT count(*) FROM user_schools WHERE user_id = CAST(:u AS UUID)"),
        {"u": user_id},
    )
    return row.first()[0]


async def _identity_count(session, user_id: str) -> int:
    row = await session.execute(
        text("SELECT count(*) FROM lti_user_identity WHERE user_id = CAST(:u AS UUID)"),
        {"u": user_id},
    )
    return row.first()[0]


async def test_teacher_launch_creates_membership():
    """An Instructor launch must produce exactly one user_schools row for the
    bound school with school_role='teacher' (the teacher path must still work)."""
    async with lti_fixture(is_active=True) as fx:
        svc = LtiService(fx.session)
        result = await svc.provision(
            fx.registration_id,
            _claims("teacher-gate-sub", deployment_id=fx.deployment_id, role_uri=INSTRUCTOR),
        )

        assert result.school_role == "teacher"
        assert result.school_id == fx.school_id

        row = (
            await fx.session.execute(
                text(
                    "SELECT school_role FROM user_schools "
                    "WHERE user_id = CAST(:u AS UUID) "
                    "AND school_id = CAST(:s AS UUID)"
                ),
                {"u": result.user_id, "s": fx.school_id},
            )
        ).first()
        assert row is not None, "teacher launch MUST create a school membership"
        assert row[0] == "teacher"
        assert await _membership_count(fx.session, result.user_id) == 1


async def test_admin_launch_creates_membership():
    """An Administrator launch is staff too → membership with school_role='admin'."""
    async with lti_fixture(is_active=True) as fx:
        svc = LtiService(fx.session)
        result = await svc.provision(
            fx.registration_id,
            _claims("admin-gate-sub", deployment_id=fx.deployment_id, role_uri=ADMINISTRATOR),
        )

        assert result.school_role == "admin"
        row = (
            await fx.session.execute(
                text(
                    "SELECT school_role FROM user_schools "
                    "WHERE user_id = CAST(:u AS UUID) "
                    "AND school_id = CAST(:s AS UUID)"
                ),
                {"u": result.user_id, "s": fx.school_id},
            )
        ).first()
        assert row is not None, "admin launch MUST create a school membership"
        assert row[0] == "admin"
        assert await _membership_count(fx.session, result.user_id) == 1


async def test_student_launch_creates_no_membership():
    """THE REGRESSION LOCK for the Q5 exposure.

    A Learner launch must be provisioned (account + identity + resolvable role +
    resolved school) but MUST NOT get a user_schools membership → so the JWT
    claims hook gives empty school_ids and RLS denies every report.
    """
    async with lti_fixture(is_active=True) as fx:
        svc = LtiService(fx.session)
        result = await svc.provision(
            fx.registration_id,
            _claims("student-gate-sub", deployment_id=fx.deployment_id, role_uri=LEARNER),
        )

        # The account IS provisioned: role resolves to student, school resolves,
        # the identity row exists (a session could still be minted for them).
        assert result.school_role == "student"
        assert result.school_id == fx.school_id, (
            "school still resolves — the gate is on the membership, not the tenant"
        )
        assert await _identity_count(fx.session, result.user_id) == 1

        # But ZERO membership — this is the exposure being closed.
        assert await _membership_count(fx.session, result.user_id) == 0, (
            "STUDENT PRIVACY LEAK: a Learner launch created a school membership → "
            "RLS would grant the student every school-wide + per-student report"
        )


async def test_unknown_role_launch_creates_no_membership():
    """Defence in depth: an unrecognised role floors to 'student' (least
    privilege) and therefore ALSO gets no membership — the allowlist is
    positive (staff-only), not a student denylist."""
    async with lti_fixture(is_active=True) as fx:
        svc = LtiService(fx.session)
        result = await svc.provision(
            fx.registration_id,
            _claims(
                "mentor-gate-sub",
                deployment_id=fx.deployment_id,
                role_uri="http://purl.imsglobal.org/vocab/lis/v2/membership#Mentor",
            ),
        )
        assert result.school_role == "student"
        assert await _membership_count(fx.session, result.user_id) == 0
