"""LTI 1.3 / Advantage tool-provider logic.

Replicates the legacy EdvanceLearning GAINS launch (LTI 1.3, OIDC + id_token):

  1. OIDC third-party login init  -> redirect to platform authorize endpoint
  2. id_token form-POST back      -> validate signature (platform JWKS), iss,
     aud, exp, nonce + single-use state (replay protection)
  3. map IMS roles -> school_role, resolve tenant from the deployment binding,
     provision/lookup the Supabase user + membership, then hand off a session.

JWTs are handled with PyJWT (RS256). The platform's public keys are fetched
from the registration's ``jwks_url``; the tool's own keypair (per registration)
is published at ``/.well-known/jwks.json`` for outbound Advantage calls.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import jwt
from jwt import PyJWKClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# IMS LIS v2 membership / institution / system role URIs -> in-school role.
_ROLE_URIS = {
    "admin": (
        "membership#administrator",
        "institution/person#administrator",
        "system/person#administrator",
    ),
    "teacher": (
        "membership#instructor",
        "institution/person#instructor",
        "membership#contentdeveloper",
        "membership#teachingassistant",
    ),
    "student": (
        "membership#learner",
        "institution/person#student",
    ),
}

LAUNCH_TTL_SECONDS = 300
CLOCK_SKEW_SECONDS = 60
LTI_MSG_RESOURCE_LINK = "LtiResourceLinkRequest"


def map_lti_roles(roles: list[str]) -> str:
    """Collapse the IMS roles array to admin/teacher/student (most-privileged).

    Mirrors the legacy reporting collapse. Defaults to 'student' (least
    privilege) when nothing matches.
    """
    low = [r.lower() for r in (roles or [])]

    def has(suffixes: tuple[str, ...]) -> bool:
        return any(any(s in r for s in suffixes) for r in low)

    if has(_ROLE_URIS["admin"]):
        return "admin"
    if has(_ROLE_URIS["teacher"]):
        return "teacher"
    if has(_ROLE_URIS["student"]):
        return "student"
    return "student"


@dataclass
class LaunchResult:
    user_id: str
    email: str
    school_id: Optional[str]
    school_role: str
    registration_id: str
    deployment_id: str
    context_label: Optional[str]
    resource_link_id: Optional[str]


class LtiError(Exception):
    """A recoverable LTI protocol error (returned as 400 to the platform)."""


class LtiService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- registration lookup -------------------------------------------------
    async def get_registration_by_issuer(
        self, issuer: str, client_id: Optional[str]
    ) -> Optional[dict]:
        if client_id:
            row = await self.session.execute(
                text(
                    "SELECT id::text, issuer, client_id, auth_login_url, "
                    "auth_token_url, jwks_url, tool_private_key, tool_kid "
                    "FROM lti_registration "
                    "WHERE issuer = :iss AND client_id = :cid AND is_active LIMIT 1"
                ),
                {"iss": issuer, "cid": client_id},
            )
        else:
            row = await self.session.execute(
                text(
                    "SELECT id::text, issuer, client_id, auth_login_url, "
                    "auth_token_url, jwks_url, tool_private_key, tool_kid "
                    "FROM lti_registration WHERE issuer = :iss AND is_active LIMIT 1"
                ),
                {"iss": issuer},
            )
        r = row.first()
        return dict(r._mapping) if r else None

    async def get_registration(self, registration_id: str) -> Optional[dict]:
        row = await self.session.execute(
            text(
                "SELECT id::text, issuer, client_id, auth_login_url, auth_token_url, "
                "jwks_url, tool_private_key, tool_kid FROM lti_registration "
                "WHERE id = :id LIMIT 1"
            ),
            {"id": registration_id},
        )
        r = row.first()
        return dict(r._mapping) if r else None

    # ---- step 1: OIDC login init ---------------------------------------------
    async def start_login(
        self,
        *,
        issuer: str,
        login_hint: str,
        client_id: Optional[str],
        lti_message_hint: Optional[str],
        target_link_uri: Optional[str],
        tool_launch_url: str,
    ) -> str:
        """Persist state/nonce and return the platform authorize redirect URL."""
        reg = await self.get_registration_by_issuer(issuer, client_id)
        if not reg:
            raise LtiError(f"Unknown LTI issuer/client: {issuer}")

        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(seconds=LAUNCH_TTL_SECONDS)
        await self.session.execute(
            text(
                "INSERT INTO lti_launch_session (state, nonce, registration_id, "
                "target_link_uri, expires_at) VALUES (:s, :n, :rid, :t, :e)"
            ),
            {"s": state, "n": nonce, "rid": reg["id"],
             "t": target_link_uri, "e": expires},
        )
        await self.session.commit()

        params = {
            "scope": "openid",
            "response_type": "id_token",
            "response_mode": "form_post",
            "prompt": "none",
            "client_id": reg["client_id"],
            "redirect_uri": tool_launch_url,
            "login_hint": login_hint,
            "state": state,
            "nonce": nonce,
        }
        if lti_message_hint:
            params["lti_message_hint"] = lti_message_hint
        return f"{reg['auth_login_url']}?{urlencode(params)}"

    # ---- step 2: validate the id_token ---------------------------------------
    async def _consume_state(self, state: str) -> dict:
        row = await self.session.execute(
            text(
                "SELECT id::text, nonce, registration_id::text, consumed, expires_at "
                "FROM lti_launch_session WHERE state = :s LIMIT 1"
            ),
            {"s": state},
        )
        r = row.first()
        if not r:
            raise LtiError("Unknown launch state (possible replay or expired)")
        m = dict(r._mapping)
        if m["consumed"]:
            raise LtiError("Launch state already consumed (replay rejected)")
        if m["expires_at"] < datetime.now(timezone.utc):
            raise LtiError("Launch state expired")
        await self.session.execute(
            text("UPDATE lti_launch_session SET consumed = TRUE WHERE id = :id"),
            {"id": m["id"]},
        )
        await self.session.commit()
        return m

    def _verify_id_token(self, id_token: str, reg: dict, expected_nonce: str) -> dict:
        """Verify signature against platform JWKS + standard LTI claims."""
        signing_key = PyJWKClient(reg["jwks_url"]).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=reg["client_id"],
            issuer=reg["issuer"],
            leeway=CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
        if claims.get("nonce") != expected_nonce:
            raise LtiError("id_token nonce mismatch")
        mt = claims.get("https://purl.imsglobal.org/spec/lti/claim/message_type")
        if mt != LTI_MSG_RESOURCE_LINK:
            raise LtiError(f"Unsupported LTI message_type: {mt}")
        return claims

    async def validate_launch(self, id_token: str, state: str) -> tuple[dict, str]:
        """Returns (verified_claims, registration_id). Consumes the state."""
        sess = await self._consume_state(state)
        reg = await self.get_registration(sess["registration_id"])
        if not reg:
            raise LtiError("Launch registration no longer exists")
        try:
            claims = self._verify_id_token(id_token, reg, sess["nonce"])
        except jwt.PyJWTError as e:  # signature/claim failure
            raise LtiError(f"id_token validation failed: {e}") from e
        return claims, reg["id"]

    # ---- step 3: tenant + user provisioning ----------------------------------
    async def _resolve_school(self, registration_id: str, deployment_id: str) -> Optional[str]:
        row = await self.session.execute(
            text(
                "SELECT school_id::text FROM lti_deployment "
                "WHERE registration_id = :rid AND deployment_id = :did LIMIT 1"
            ),
            {"rid": registration_id, "did": deployment_id},
        )
        r = row.first()
        return r[0] if r and r[0] else None

    async def provision(self, registration_id: str, claims: dict) -> LaunchResult:
        sub = claims["sub"]
        deployment_id = claims.get(
            "https://purl.imsglobal.org/spec/lti/claim/deployment_id", ""
        )
        roles = claims.get("https://purl.imsglobal.org/spec/lti/claim/roles", [])
        context = claims.get("https://purl.imsglobal.org/spec/lti/claim/context", {})
        rlink = claims.get(
            "https://purl.imsglobal.org/spec/lti/claim/resource_link", {}
        )
        email = claims.get("email") or f"lti-{sub}@lti.local"
        name = claims.get("name") or claims.get("given_name") or email
        school_role = map_lti_roles(roles)
        school_id = await self._resolve_school(registration_id, deployment_id)

        # find or create the external identity -> auth user
        row = await self.session.execute(
            text(
                "SELECT user_id::text FROM lti_user_identity "
                "WHERE registration_id = :rid AND sub = :sub LIMIT 1"
            ),
            {"rid": registration_id, "sub": sub},
        )
        existing = row.first()
        if existing:
            user_id = existing[0]
        else:
            user_id = await self._create_auth_user(email, name)
            await self.session.execute(
                text(
                    "INSERT INTO lti_user_identity (registration_id, sub, user_id) "
                    "VALUES (:rid, :sub, :uid) ON CONFLICT DO NOTHING"
                ),
                {"rid": registration_id, "sub": sub, "uid": user_id},
            )

        # attach (or update) school membership
        if school_id:
            await self.session.execute(
                text(
                    "INSERT INTO user_schools (user_id, school_id, school_role, is_primary) "
                    "VALUES (:uid, :sid, :role, TRUE) "
                    "ON CONFLICT (user_id, school_id) "
                    "DO UPDATE SET school_role = EXCLUDED.school_role"
                ),
                {"uid": user_id, "sid": school_id, "role": school_role},
            )
        await self.session.commit()

        return LaunchResult(
            user_id=user_id, email=email, school_id=school_id,
            school_role=school_role, registration_id=registration_id,
            deployment_id=deployment_id,
            context_label=context.get("label") if isinstance(context, dict) else None,
            resource_link_id=rlink.get("id") if isinstance(rlink, dict) else None,
        )

    async def _create_auth_user(self, email: str, name: str) -> str:
        """Provision a confirmed Supabase auth user (the new-user trigger assigns
        the platform 'user' role + profile)."""
        row = await self.session.execute(
            text("SELECT id::text FROM auth.users WHERE email = :e LIMIT 1"),
            {"e": email},
        )
        existing = row.first()
        if existing:
            return existing[0]
        ins = await self.session.execute(
            text(
                """
                INSERT INTO auth.users (
                    id, instance_id, aud, role, email, email_confirmed_at,
                    raw_app_meta_data, raw_user_meta_data, created_at, updated_at)
                VALUES (
                    uuid_generate_v7(), '00000000-0000-0000-0000-000000000000',
                    'authenticated', 'authenticated', CAST(:email AS text), now(),
                    '{"provider":"lti","providers":["lti"]}'::jsonb,
                    jsonb_build_object('full_name', CAST(:name AS text)), now(), now())
                RETURNING id::text
                """
            ),
            {"email": email, "name": name},
        )
        return ins.first()[0]

    # ---- tool JWKS (outbound key publication) --------------------------------
    async def tool_jwks(self) -> dict:
        rows = await self.session.execute(
            text("SELECT tool_private_key, tool_kid FROM lti_registration WHERE is_active")
        )
        keys = []
        seen = set()
        for r in rows.all():
            m = dict(r._mapping)
            if m["tool_kid"] in seen:
                continue
            seen.add(m["tool_kid"])
            keys.append(_public_jwk_from_pem(m["tool_private_key"], m["tool_kid"]))
        return {"keys": keys}


def _public_jwk_from_pem(private_pem: str, kid: str) -> dict:
    """Derive the public RSA JWK from a PEM private key."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    key = load_pem_private_key(private_pem.encode(), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)
    nums = key.public_key().public_numbers()

    def b64(n: int) -> str:
        import base64
        b = n.to_bytes((n.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    return {
        "kty": "RSA", "use": "sig", "alg": "RS256", "kid": kid,
        "n": b64(nums.n), "e": b64(nums.e),
    }


def now_ts() -> int:
    return int(time.time())
