"""LTI users are locked to analytics-only: the account-mutation guard + claim.

Schoology-embedded (LTI) users get a dashboard/reports-only experience. The
account-mutation endpoints (PATCH /profile, POST /profile/avatar) carry no
permission of their own, so ``forbid_lti_user`` is the API backstop that rejects
them there — enforce, don't just hide. The ``is_lti_user`` flag flows from the
signed JWT claim through ``extract_user_claims`` into ``CurrentUser``; an absent
claim (e.g. a token minted before the claim existed) defaults to ``False`` — the
safe direction for a lock-down (a real LTI user's next token refresh carries it,
and the middleware route wall gates in the meantime).
"""

from __future__ import annotations

import pytest

from app.core.dependencies import forbid_lti_user
from app.core.exceptions import LtiActionForbiddenError
from app.core.security import extract_user_claims
from app.schemas.auth import CurrentUser


def _user(**overrides) -> CurrentUser:
    base = dict(
        user_id="019f9aa1-bd15-7297-9890-fd550de8d83b",
        email="teacher@example.com",
        user_role="user",
        hierarchy_rank=100,
        permissions=["reports:read"],
        school_ids=["019eb11c-410a-7ffb-86e6-a0294c669670"],
    )
    base.update(overrides)
    return CurrentUser(**base)


def test_extract_user_claims_reads_is_lti_user():
    payload = {"sub": "u", "email": "lti-abc@lti.local", "is_lti_user": True}
    claims = extract_user_claims(payload)
    assert claims["is_lti_user"] is True
    assert CurrentUser(**claims).is_lti_user is True


def test_extract_user_claims_defaults_is_lti_user_false_when_absent():
    claims = extract_user_claims({"sub": "u", "email": "teacher@school.edu"})
    assert claims["is_lti_user"] is False
    assert CurrentUser(**claims).is_lti_user is False


async def test_forbid_lti_user_rejects_lti_user():
    with pytest.raises(LtiActionForbiddenError) as exc_info:
        await forbid_lti_user(current_user=_user(is_lti_user=True))
    assert exc_info.value.status_code == 403
    # Generic message — leaks nothing about the account.
    assert "Schoology" in exc_info.value.message


async def test_forbid_lti_user_allows_normal_user():
    user = _user(is_lti_user=False)
    assert await forbid_lti_user(current_user=user) is user


async def test_forbid_lti_user_allows_when_flag_defaulted():
    # A non-LTI user constructed without the flag at all must pass through.
    user = _user()
    assert user.is_lti_user is False
    assert await forbid_lti_user(current_user=user) is user
