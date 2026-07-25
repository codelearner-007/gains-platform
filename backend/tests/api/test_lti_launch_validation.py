"""E — launch id_token + state validation via LtiService (DB fixtures + local keys).

Locks the launch-validation invariant: validate_launch only returns claims when
the id_token signature (platform JWKS), aud, message_type, and nonce all check
out AND the single-use OIDC state is fresh. Every rejection path raises LtiError
(→ 400 to the platform). We sign test id_tokens locally with a mock RSA keypair
and patch PyJWKClient to serve its public key — NO network, NO real Schoology.

These are the OIDC replay/spoofing defenses: replayed state, expired state, wrong
aud, wrong message_type, nonce mismatch, and a wrong-key signature must ALL be
rejected, and the happy path must return (claims, registration_id).
"""

from __future__ import annotations

import secrets
import time
from datetime import timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from sqlalchemy import text

import app.services.lti_service as lti_mod
from app.services.lti_service import LtiError, LtiService

from ..services._lti_fixtures import TEST_CLIENT, TEST_ISSUER, lti_fixture, now_utc

MOCK_KID = "wave4-platform-key"
MSG_TYPE_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/message_type"


def _pem(key: rsa.RSAPrivateKey) -> str:
    return key.private_bytes(
        Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()
    ).decode()


class _FakeSigningKey:
    def __init__(self, public_key):
        self.key = public_key


class _FakeJWKClient:
    """Stand-in for jwt.PyJWKClient — returns a fixed public key, no network."""

    _public_key = None  # set per-test to the mock platform's public key

    def __init__(self, _url):
        pass

    def get_signing_key_from_jwt(self, _token):
        return _FakeSigningKey(type(self)._public_key)


@pytest.fixture
def platform_key(monkeypatch):
    """A mock platform RSA keypair whose public half PyJWKClient will serve."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _FakeJWKClient._public_key = key.public_key()
    monkeypatch.setattr(lti_mod, "PyJWKClient", _FakeJWKClient)
    return key


def _sign(key: rsa.RSAPrivateKey, *, nonce: str, aud=TEST_CLIENT,
          iss=TEST_ISSUER, msg_type="LtiResourceLinkRequest", exp_offset=300) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": iss,
            "aud": aud,
            "sub": f"wave4-{secrets.token_hex(6)}",
            "iat": now,
            "exp": now + exp_offset,
            "nonce": nonce,
            MSG_TYPE_CLAIM: msg_type,
            "https://purl.imsglobal.org/spec/lti/claim/deployment_id": "wave4-test-deployment-1",
            "https://purl.imsglobal.org/spec/lti/claim/roles": [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ],
            "email": "launch@test.lti",
        },
        _pem(key),
        algorithm="RS256",
        headers={"kid": MOCK_KID},
    )


async def _insert_state(fx, *, nonce: str, expires, consumed=False) -> str:
    state = f"wave4-state-{secrets.token_urlsafe(16)}"
    await fx.session.execute(
        text(
            "INSERT INTO lti_launch_session "
            "(state, nonce, registration_id, expires_at, consumed) "
            "VALUES (:s, :n, CAST(:rid AS UUID), :e, :c)"
        ),
        {"s": state, "n": nonce, "rid": fx.registration_id, "e": expires, "c": consumed},
    )
    await fx.session.commit()
    return state


async def test_happy_path_returns_claims_and_registration_id(platform_key):
    async with lti_fixture() as fx:
        svc = LtiService(fx.session)
        nonce = secrets.token_urlsafe(16)
        state = await _insert_state(fx, nonce=nonce, expires=now_utc() + timedelta(minutes=5))
        token = _sign(platform_key, nonce=nonce)

        claims, registration_id = await svc.validate_launch(token, state)

        assert registration_id == fx.registration_id
        assert claims["aud"] == TEST_CLIENT
        assert claims["nonce"] == nonce


async def test_replayed_state_is_rejected(platform_key):
    async with lti_fixture() as fx:
        svc = LtiService(fx.session)
        nonce = secrets.token_urlsafe(16)
        state = await _insert_state(fx, nonce=nonce, expires=now_utc() + timedelta(minutes=5))

        # First launch consumes the state.
        await svc.validate_launch(_sign(platform_key, nonce=nonce), state)
        # Replay with a freshly-signed (otherwise valid) token → state already consumed.
        with pytest.raises(LtiError, match="already consumed"):
            await svc.validate_launch(_sign(platform_key, nonce=nonce), state)


async def test_expired_state_is_rejected(platform_key):
    async with lti_fixture() as fx:
        svc = LtiService(fx.session)
        nonce = secrets.token_urlsafe(16)
        state = await _insert_state(fx, nonce=nonce, expires=now_utc() - timedelta(seconds=1))
        with pytest.raises(LtiError, match="expired"):
            await svc.validate_launch(_sign(platform_key, nonce=nonce), state)


async def test_unknown_state_is_rejected(platform_key):
    async with lti_fixture() as fx:
        svc = LtiService(fx.session)
        with pytest.raises(LtiError, match="Unknown launch state"):
            await svc.validate_launch(
                _sign(platform_key, nonce="x"), "wave4-state-never-inserted"
            )


async def test_wrong_aud_is_rejected(platform_key):
    async with lti_fixture() as fx:
        svc = LtiService(fx.session)
        nonce = secrets.token_urlsafe(16)
        state = await _insert_state(fx, nonce=nonce, expires=now_utc() + timedelta(minutes=5))
        token = _sign(platform_key, nonce=nonce, aud="some-other-client")
        with pytest.raises(LtiError):
            await svc.validate_launch(token, state)


async def test_wrong_message_type_is_rejected(platform_key):
    async with lti_fixture() as fx:
        svc = LtiService(fx.session)
        nonce = secrets.token_urlsafe(16)
        state = await _insert_state(fx, nonce=nonce, expires=now_utc() + timedelta(minutes=5))
        token = _sign(platform_key, nonce=nonce, msg_type="LtiDeepLinkingRequest")
        with pytest.raises(LtiError, match="message_type"):
            await svc.validate_launch(token, state)


async def test_nonce_mismatch_is_rejected(platform_key):
    async with lti_fixture() as fx:
        svc = LtiService(fx.session)
        # State stores one nonce; the token carries a DIFFERENT one.
        state = await _insert_state(
            fx, nonce="the-real-nonce", expires=now_utc() + timedelta(minutes=5)
        )
        token = _sign(platform_key, nonce="a-forged-nonce")
        with pytest.raises(LtiError, match="nonce"):
            await svc.validate_launch(token, state)


async def test_bad_signature_is_rejected(platform_key):
    # Sign with a DIFFERENT key than the one PyJWKClient serves → signature fails.
    async with lti_fixture() as fx:
        svc = LtiService(fx.session)
        nonce = secrets.token_urlsafe(16)
        state = await _insert_state(fx, nonce=nonce, expires=now_utc() + timedelta(minutes=5))
        wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = _sign(wrong_key, nonce=nonce)
        with pytest.raises(LtiError, match="validation failed"):
            await svc.validate_launch(token, state)


async def test_registration_disabled_between_login_and_launch_is_rejected(platform_key):
    # L-3 consistency: login-init already filters `is_active` when resolving a
    # registration; get_registration (the launch-leg reload) must too. If an admin
    # disables the registration AFTER login-init minted the state but BEFORE launch,
    # the launch leg must fail the same way (→ LtiError → 400), not sail through on
    # a stale binding.
    async with lti_fixture() as fx:
        svc = LtiService(fx.session)
        nonce = secrets.token_urlsafe(16)
        state = await _insert_state(fx, nonce=nonce, expires=now_utc() + timedelta(minutes=5))

        # Admin flips the registration off after the OIDC login-init.
        await fx.session.execute(
            text("UPDATE lti_registration SET is_active = FALSE WHERE id = CAST(:rid AS UUID)"),
            {"rid": fx.registration_id},
        )
        await fx.session.commit()

        token = _sign(platform_key, nonce=nonce)
        with pytest.raises(LtiError, match="no longer exists"):
            await svc.validate_launch(token, state)
