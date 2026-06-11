#!/usr/bin/env python3
"""LTI 1.3 setup for the GAINS tool.

Two modes:

    seed        Register the Schoology 1.3 platform template (real endpoints,
                placeholder client_id — the org admin fills it in after
                installing the app in Schoology) and generate the tool's RSA
                keypair. This is the only registration shipped by default.

    launch      Run a FULL mock LTI 1.3 launch against the local backend to
                prove the flow without a real Schoology org. The mock platform
                registration + its deployment are created TRANSIENTLY at the
                start of the run (bound to the first active school) and removed
                afterward, so this command never depends on demo/synthetic data
                and leaves no rows behind. Dev/test only.

Usage:
    backend/venv/bin/python supabase/seeds/seed_lti.py seed
    backend/venv/bin/python supabase/seeds/seed_lti.py launch [--role teacher]
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import jwt
import psycopg2
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat,
)

PG = "postgresql://postgres:postgres@127.0.0.1:56322/postgres"
BACKEND = "http://127.0.0.1:8000"

# Real Schoology LTI 1.3 platform endpoints (from research). client_id/keyset
# get filled in by the org admin after installing the app in Schoology.
SCHOOLOGY = {
    "issuer": "https://schoology.schoology.com",
    "auth_login_url": "https://lti-service.svc.schoology.com/lti-service/authorize-redirect",
    "auth_token_url": "https://lti-service.svc.schoology.com/lti-service/access-token",
    "jwks_url": "https://lti-service.svc.schoology.com/lti-service/.well-known/jwks",
}

# Mock platform constants — used ONLY by the `launch` test harness, which
# registers + tears these down within a single run (never persisted by `seed`).
MOCK_ISS = "https://mock.lti/platform"
MOCK_CLIENT = "mock-client-1"
MOCK_DEPLOYMENT = "mock-client-1-1"
MOCK_KID = "mock-platform-key"
MOCK_JWKS_PORT = 8799


def pem(key: rsa.RSAPrivateKey) -> str:
    return key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL,
                             NoEncryption()).decode()


def cmd_seed() -> int:
    """Register the Schoology 1.3 template (the only persistent registration)."""
    tool_key = pem(rsa.generate_private_key(public_exponent=65537, key_size=2048))
    conn = psycopg2.connect(PG)
    conn.autocommit = True
    c = conn.cursor()

    # Schoology template (placeholder client_id; admin replaces after install).
    c.execute("DELETE FROM lti_registration WHERE issuer=%s AND client_id=%s",
              (SCHOOLOGY["issuer"], "REPLACE_AFTER_SCHOOLOGY_INSTALL"))
    c.execute(
        """INSERT INTO lti_registration (issuer, client_id, platform_name,
             auth_login_url, auth_token_url, jwks_url, tool_private_key, tool_kid)
           VALUES (%s,'REPLACE_AFTER_SCHOOLOGY_INSTALL','Schoology',%s,%s,%s,%s,'gains-tool-1')""",
        (SCHOOLOGY["issuer"], SCHOOLOGY["auth_login_url"],
         SCHOOLOGY["auth_token_url"], SCHOOLOGY["jwks_url"], tool_key),
    )
    conn.close()
    print("Seeded LTI registration:")
    print(f"  - Schoology template ({SCHOOLOGY['issuer']}) — fill client_id post-install")
    print("Run a mock launch (dev/test):  "
          "backend/venv/bin/python supabase/seeds/seed_lti.py launch")
    return 0


def _register_mock_platform(conn, tool_key: str) -> tuple[str, str]:
    """Create a transient mock registration + deployment for the launch harness.

    Bound to the FIRST active school (not a deleted synthetic one). Returns
    (registration_id, school_id). Caller is responsible for cleanup.
    """
    c = conn.cursor()
    c.execute("DELETE FROM lti_registration WHERE issuer=%s", (MOCK_ISS,))
    c.execute(
        """INSERT INTO lti_registration (issuer, client_id, platform_name,
             auth_login_url, auth_token_url, jwks_url, tool_private_key, tool_kid)
           VALUES (%s,%s,'MockPlatform',%s,'http://127.0.0.1:%s/token',
             'http://127.0.0.1:%s/jwks.json',%s,'gains-tool-mock')
           RETURNING id::text""",
        (MOCK_ISS, MOCK_CLIENT, f"http://127.0.0.1:{MOCK_JWKS_PORT}/auth",
         MOCK_JWKS_PORT, MOCK_JWKS_PORT, tool_key),
    )
    reg_id = c.fetchone()[0]
    c.execute("SELECT school_id::text, name FROM schools "
              "WHERE is_active = TRUE ORDER BY short_name LIMIT 1")
    row = c.fetchone()
    if row is None:
        raise SystemExit("no active school to bind the mock LTI deployment to — "
                         "run gains_data seed first")
    school_id, school_name = row
    c.execute("INSERT INTO lti_deployment (registration_id, deployment_id, school_id) "
              "VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
              (reg_id, MOCK_DEPLOYMENT, school_id))
    print(f"  mock platform ({MOCK_ISS}) -> {school_name} (transient)")
    return reg_id, school_id


def _cleanup_mock_platform(conn) -> None:
    """Remove the transient mock registration + its deployments/sessions."""
    c = conn.cursor()
    c.execute("DELETE FROM lti_registration WHERE issuer=%s", (MOCK_ISS,))


def cmd_launch(role: str) -> int:
    role_uri = {
        "teacher": "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor",
        "student": "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner",
        "admin": "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Administrator",
    }[role]

    # Register a transient mock platform for this run (cleaned up in finally).
    tool_key = pem(rsa.generate_private_key(public_exponent=65537, key_size=2048))
    reg_conn = psycopg2.connect(PG)
    reg_conn.autocommit = True
    _register_mock_platform(reg_conn, tool_key)

    # platform keypair + JWKS server
    plat = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    from app.services.lti_service import _public_jwk_from_pem  # type: ignore
    jwk = _public_jwk_from_pem(pem(plat), MOCK_KID)
    body = json.dumps({"keys": [jwk]}).encode()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", MOCK_JWKS_PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with httpx.Client(base_url=BACKEND, follow_redirects=False) as cli:
            r = cli.get("/api/v1/lti/login",
                        params={"iss": MOCK_ISS, "client_id": MOCK_CLIENT,
                                "login_hint": "demo"})
            print(f"login -> {r.status_code}")
            # fetch the freshly-created state/nonce
            conn = psycopg2.connect(PG)
            with conn.cursor() as c:
                c.execute("SELECT s.state, s.nonce FROM lti_launch_session s "
                          "JOIN lti_registration r ON r.id=s.registration_id "
                          "WHERE r.issuer=%s AND NOT s.consumed "
                          "ORDER BY s.created_at DESC LIMIT 1", (MOCK_ISS,))
                state, nonce = c.fetchone()
            conn.close()
            now = int(time.time())
            token = jwt.encode({
                "iss": MOCK_ISS, "aud": MOCK_CLIENT, "sub": f"demo-{role}",
                "iat": now, "exp": now + 300, "nonce": nonce,
                "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiResourceLinkRequest",
                "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
                "https://purl.imsglobal.org/spec/lti/claim/deployment_id": MOCK_DEPLOYMENT,
                "https://purl.imsglobal.org/spec/lti/claim/roles": [role_uri],
                "https://purl.imsglobal.org/spec/lti/claim/context": {"id": "c1", "label": "DEMO"},
                "https://purl.imsglobal.org/spec/lti/claim/resource_link": {"id": "rl-1"},
                "email": f"demo-{role}@lti.demo", "name": f"Demo {role.title()}",
            }, pem(plat), algorithm="RS256", headers={"kid": MOCK_KID})
            r = cli.post("/api/v1/lti/launch", data={"id_token": token, "state": state})
            print(f"launch -> {r.status_code}")
            print(f"redirect: {r.headers.get('location')}")
            return 0 if r.status_code == 302 else 1
    finally:
        srv.shutdown()
        _cleanup_mock_platform(reg_conn)
        reg_conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed")
    lp = sub.add_parser("launch")
    lp.add_argument("--role", default="teacher", choices=["teacher", "student", "admin"])
    args = ap.parse_args()
    if args.cmd == "seed":
        return cmd_seed()
    return cmd_launch(args.role)


if __name__ == "__main__":
    sys.path.insert(0, "/Users/mac/Desktop/PS_P/gains-platform/backend")
    raise SystemExit(main())
