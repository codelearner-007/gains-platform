"""Regression: a synthetic LTI email must flow through CurrentUser.

An LTI-provisioned user carries a synthetic address ``lti-<hash>@lti.local``
(see ``synthetic_lti_email``). ``CurrentUser`` is built from the JWT claims on
EVERY authenticated request (``dependencies.get_current_user`` →
``CurrentUser(**claims)``). When ``CurrentUser.email`` was ``EmailStr``, Pydantic
rejected the reserved ``.local`` TLD ("special-use or reserved name"), raising a
ValidationError → FastAPI 422 on ``loc=["email"]`` → the LTI user could not read
ANY data (dashboard empty, every report "Could not load"). The email is a
trusted claim from our own bridge-minted JWT, never used for authz, so it is a
plain ``str``. These tests lock that: a synthetic ``.local`` email must not break
request construction.
"""

from __future__ import annotations

from app.core.security import extract_user_claims
from app.schemas.auth import CurrentUser
from app.schemas.response.auth import CurrentUserResponse
from app.services.lti_service import synthetic_lti_email


def test_currentuser_accepts_synthetic_lti_local_email():
    # Direct schema construction with a reserved-TLD synthetic address.
    user = CurrentUser(
        user_id="019f9aa1-bd15-7297-9890-fd550de8d83b",
        email="lti-011168b24119608ca028f360cedda42d13cbf9cf@lti.local",
        user_role="user",
        hierarchy_rank=100,
        permissions=["reports:read"],
        school_ids=["019eb11c-410a-7ffb-86e6-a0294c669670"],
    )
    assert user.email.endswith("@lti.local")
    assert user.can_access_school("019eb11c-410a-7ffb-86e6-a0294c669670")


def test_dependency_claims_path_accepts_synthetic_lti_email():
    # Mirror get_current_user: JWT payload -> extract_user_claims -> CurrentUser.
    # This is the exact path that 422'd for LTI users before the fix.
    payload = {
        "sub": "019f9aa1-bd15-7297-9890-fd550de8d83b",
        "email": "lti-deadbeef@lti.local",
        "user_role": "user",
        "permissions": ["reports:read"],
        "school_ids": ["019eb11c-410a-7ffb-86e6-a0294c669670"],
        "is_super_admin": False,
    }
    user = CurrentUser(**extract_user_claims(payload))
    assert user.email == "lti-deadbeef@lti.local"
    assert user.has_permission("reports:read")
    assert user.school_ids == ["019eb11c-410a-7ffb-86e6-a0294c669670"]


def test_synthetic_lti_email_output_survives_currentuser():
    # The exact string synthetic_lti_email() emits must construct a CurrentUser.
    email = synthetic_lti_email("some-registration-id", "demo-teacher")
    assert email.endswith("@lti.local")
    user = CurrentUser(
        user_id="u", email=email, user_role="user",
        hierarchy_rank=100, permissions=[], school_ids=[],
    )
    assert user.email == email


def test_currentuserresponse_accepts_synthetic_lti_email():
    # The OUTBOUND response_model for GET /api/v1/auth/me validates on
    # construction; a synthetic .local email must not 500 the endpoint.
    resp = CurrentUserResponse(
        user_id="u",
        email=synthetic_lti_email("reg", "demo-admin"),
        user_role="user",
        hierarchy_rank=100,
        permissions=["reports:read"],
    )
    assert resp.email.endswith("@lti.local")
