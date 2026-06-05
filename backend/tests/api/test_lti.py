"""End-to-end LTI 1.3 launch test against a mock platform.

Spins up a threaded HTTP server that serves the *platform's* JWKS, registers a
mock platform, drives /lti/login then /lti/launch with a platform-signed
id_token, and asserts: tenant resolved from the deployment, IMS role mapped,
Supabase user + membership provisioned, replay rejected, tampered token
rejected.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import jwt
import psycopg2
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from httpx import AsyncClient

from app.main import app
from app.services.lti_service import _public_jwk_from_pem

PG = "postgresql://postgres:postgres@127.0.0.1:56322/postgres"
ISS = "https://mock.lti/platform"
CLIENT_ID = "client-abc-123"
DEPLOYMENT_ID = "client-abc-123-1"
PLAT_KID = "platform-key-1"


def _pem(key: rsa.RSAPrivateKey) -> str:
    return key.private_bytes(
        Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()
    ).decode()


@pytest.fixture(scope="module")
def platform_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def jwks_server(platform_key):
    """Serve the mock platform's public JWKS so the tool can fetch it."""
    jwk = _public_jwk_from_pem(_pem(platform_key), PLAT_KID)
    body = json.dumps({"keys": [jwk]}).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # silence
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}/jwks.json"
    server.shutdown()


@pytest.fixture()
def registration(jwks_server):
    """Insert a mock registration + deployment bound to a synthetic school."""
    tool_key = _pem(rsa.generate_private_key(public_exponent=65537, key_size=2048))
    conn = psycopg2.connect(PG)
    conn.autocommit = True
    with conn.cursor() as c:
        c.execute("DELETE FROM lti_registration WHERE issuer=%s", (ISS,))
        c.execute(
            """INSERT INTO lti_registration (issuer, client_id, platform_name,
                 auth_login_url, auth_token_url, jwks_url, tool_private_key, tool_kid)
               VALUES (%s,%s,'MockPlatform','https://mock.lti/auth',
                 'https://mock.lti/token',%s,%s,'tool-key-1') RETURNING id::text""",
            (ISS, CLIENT_ID, jwks_server, tool_key),
        )
        reg_id = c.fetchone()[0]
        c.execute(
            "SELECT school_id::text, name FROM schools "
            "WHERE schoology_building_id='synth-002'"
        )
        school_id, school_name = c.fetchone()
        c.execute(
            "INSERT INTO lti_deployment (registration_id, deployment_id, school_id) "
            "VALUES (%s,%s,%s)",
            (reg_id, DEPLOYMENT_ID, school_id),
        )
    conn.close()
    yield {"reg_id": reg_id, "school_id": school_id, "school_name": school_name}
    conn = psycopg2.connect(PG)
    conn.autocommit = True
    with conn.cursor() as c:
        c.execute("DELETE FROM lti_registration WHERE issuer=%s", (ISS,))  # cascades
    conn.close()


def _fetch_state_nonce(reg_id: str) -> tuple[str, str]:
    conn = psycopg2.connect(PG)
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT state, nonce FROM lti_launch_session "
                "WHERE registration_id=%s AND NOT consumed "
                "ORDER BY created_at DESC LIMIT 1",
                (reg_id,),
            )
            return c.fetchone()
    finally:
        conn.close()


def _make_id_token(platform_key, nonce: str, *, roles, sub="user-sub-1",
                   aud=CLIENT_ID, iss=ISS, deployment=DEPLOYMENT_ID, exp_delta=300):
    now = int(time.time())
    claims = {
        "iss": iss, "aud": aud, "sub": sub, "iat": now, "exp": now + exp_delta,
        "nonce": nonce,
        "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiResourceLinkRequest",
        "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
        "https://purl.imsglobal.org/spec/lti/claim/deployment_id": deployment,
        "https://purl.imsglobal.org/spec/lti/claim/roles": roles,
        "https://purl.imsglobal.org/spec/lti/claim/context": {"id": "c1", "label": "MATH-7"},
        "https://purl.imsglobal.org/spec/lti/claim/resource_link": {"id": "rl-1"},
        "email": f"{sub}@school.test", "name": "Test Educator",
    }
    return jwt.encode(claims, _pem(platform_key), algorithm="RS256",
                      headers={"kid": PLAT_KID})


@pytest.fixture(scope="module", autouse=True)
def _lti_routes_enabled():
    """Mount the LTI router for this module so the protocol surface is reachable.

    LTI is disabled by default (settings.LTI_ENABLED is False), which leaves
    /api/v1/lti/* unregistered on the app. These end-to-end tests exercise the
    LTI feature itself, so we mount the router here (the LTI_ENABLED=true case)
    and remove it on teardown. test_lti_disabled.py covers the default-off 404.
    """
    from app.api.v1 import lti as lti_module

    already_mounted = any(
        getattr(r, "path", "").startswith("/api/v1/lti") for r in app.router.routes
    )
    added_paths: set[str] = set()
    if not already_mounted:
        before = {id(r) for r in app.router.routes}
        app.include_router(lti_module.router, prefix="/api/v1")
        added_paths = {id(r) for r in app.router.routes} - before
    yield
    if added_paths:
        app.router.routes = [r for r in app.router.routes if id(r) not in added_paths]


@pytest_asyncio.fixture(autouse=True)
async def _reset_session_manager():
    import app.db.session as sm
    if sm._session_manager is not None:
        try:
            await sm._session_manager.close()
        except Exception:
            pass
        sm._session_manager = None
    yield


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


async def _client() -> AsyncClient:
    return AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.anyio
async def test_login_redirects_with_oidc_params(registration):
    async with await _client() as ac:
        r = await ac.get("/api/v1/lti/login", params={
            "iss": ISS, "login_hint": "lh-1", "client_id": CLIENT_ID,
            "target_link_uri": "https://tool/launch",
        })
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("https://mock.lti/auth?")
    for needle in ("response_type=id_token", "response_mode=form_post",
                   "scope=openid", f"client_id={CLIENT_ID}", "state=", "nonce="):
        assert needle in loc


@pytest.mark.anyio
async def test_full_launch_provisions_user_and_tenant(registration, platform_key):
    async with await _client() as ac:
        await ac.get("/api/v1/lti/login", params={
            "iss": ISS, "login_hint": "lh", "client_id": CLIENT_ID})
        state, nonce = _fetch_state_nonce(registration["reg_id"])
        token = _make_id_token(platform_key, nonce, roles=[
            "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"])
        r = await ac.post("/api/v1/lti/launch",
                          data={"id_token": token, "state": state})
    assert r.status_code == 302, r.text
    assert f"school_id={registration['school_id']}" in r.headers["location"]

    # provisioning side-effects
    conn = psycopg2.connect(PG)
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT u.user_id::text FROM lti_user_identity u "
                "WHERE u.registration_id=%s AND u.sub='user-sub-1'",
                (registration["reg_id"],),
            )
            row = c.fetchone()
            assert row, "user identity not provisioned"
            uid = row[0]
            c.execute(
                "SELECT school_role FROM user_schools "
                "WHERE user_id=%s AND school_id=%s",
                (uid, registration["school_id"]),
            )
            mrow = c.fetchone()
            assert mrow and mrow[0] == "teacher", f"expected teacher, got {mrow}"
    finally:
        conn.close()


@pytest.mark.anyio
async def test_replayed_state_is_rejected(registration, platform_key):
    async with await _client() as ac:
        await ac.get("/api/v1/lti/login", params={"iss": ISS, "client_id": CLIENT_ID})
        state, nonce = _fetch_state_nonce(registration["reg_id"])
        token = _make_id_token(platform_key, nonce, roles=[
            "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner"])
        first = await ac.post("/api/v1/lti/launch",
                              data={"id_token": token, "state": state})
        assert first.status_code == 302
        replay = await ac.post("/api/v1/lti/launch",
                               data={"id_token": token, "state": state})
    assert replay.status_code == 400
    assert "consumed" in replay.json()["error"].lower()


@pytest.mark.anyio
async def test_wrong_audience_is_rejected(registration, platform_key):
    async with await _client() as ac:
        await ac.get("/api/v1/lti/login", params={"iss": ISS, "client_id": CLIENT_ID})
        state, nonce = _fetch_state_nonce(registration["reg_id"])
        bad = _make_id_token(platform_key, nonce, roles=[], aud="some-other-client")
        r = await ac.post("/api/v1/lti/launch", data={"id_token": bad, "state": state})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_learner_maps_to_student(registration, platform_key):
    async with await _client() as ac:
        await ac.get("/api/v1/lti/login", params={"iss": ISS, "client_id": CLIENT_ID})
        state, nonce = _fetch_state_nonce(registration["reg_id"])
        token = _make_id_token(platform_key, nonce, sub="learner-9", roles=[
            "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner"])
        r = await ac.post("/api/v1/lti/launch",
                          data={"id_token": token, "state": state})
    assert r.status_code == 302
    conn = psycopg2.connect(PG)
    try:
        with conn.cursor() as c:
            c.execute(
                "SELECT us.school_role FROM user_schools us "
                "JOIN lti_user_identity i ON i.user_id=us.user_id "
                "WHERE i.registration_id=%s AND i.sub='learner-9'",
                (registration["reg_id"],),
            )
            assert c.fetchone()[0] == "student"
    finally:
        conn.close()
