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

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import jwt
from jwt import PyJWKClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# STAFF-ONLY tool: a school membership (and therefore any RLS-scoped report
# access) is granted ONLY to these in-school roles. map_lti_roles collapses the
# IMS roles array to {admin, teacher, student} and defaults anything unknown to
# 'student' (least privilege), so a launch that is not clearly staff gets NO
# membership → empty school_ids in the JWT claims hook → RLS denies all report
# data. This is the student-privacy gate (Q5): GAINS surfaces per-student
# performance analytics, which students must never be able to read.
_STAFF_SCHOOL_ROLES = frozenset({"admin", "teacher"})

# Real Schoology LTI 1.3 platform endpoints. The org admin fills in client_id +
# deployment_id after installing the GAINS app in Schoology; these four URLs are
# fixed. SINGLE SOURCE OF TRUTH — both the admin service and seed_lti.py import
# this so the seeded template and the admin-created registration never diverge.
SCHOOLOGY_DEFAULTS = {
    "issuer": "https://schoology.schoology.com",
    "auth_login_url": "https://lti-service.svc.schoology.com/lti-service/authorize-redirect",
    "auth_token_url": "https://lti-service.svc.schoology.com/lti-service/access-token",
    "jwks_url": "https://lti-service.svc.schoology.com/lti-service/.well-known/jwks",
}

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
HANDOFF_TTL_SECONDS = 60
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


def synthetic_lti_email(registration_id: str, sub: str) -> str:
    """Derive the AUTH-account email for an LTI identity from (registration_id, sub).

    ACCOUNT-TAKEOVER GUARD (H1): the auth email MUST NOT be the platform's claim
    email. ``_create_auth_user`` looks up / creates the Supabase account by a BARE
    ``WHERE email =`` match (not scoped by registration_id), so if we used the real
    claim email an LTI launch whose signed email happened to equal a pre-existing
    password/staff/invited account would MERGE onto that account and the bridge
    would mint a session for it — a takeover. The auth email is therefore a
    synthetic, registration-namespaced identity derived ONLY from (registration_id,
    sub); the real claim email never keys anything auth-bearing (it survives only as
    display metadata).

    Scheme: ``lti-{sha256("{registration_id}:{sub}")[:40hex]}@lti.local``.
      * Namespaced by registration_id → collision-free across registrations even if
        the same ``sub`` value recurs under two platforms (the bare email SELECT
        can then only ever match the LTI account for THIS exact (reg, sub)).
      * Deterministic → same (reg, sub) yields the same email on every launch, so
        re-launch is idempotent (finds the existing account, never forks a new one).
      * Length-safe → local part is ``lti-`` (4) + 40 hex = 44 chars, under the
        64-char RFC 5321 local-part limit (a raw ``lti-{reg_uuid}-{sub}`` could
        overflow).
    """
    digest = hashlib.sha256(f"{registration_id}:{sub}".encode()).hexdigest()[:40]
    return f"lti-{digest}@lti.local"


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
                "WHERE id = :id AND is_active LIMIT 1"
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
        # `AND is_active` is the per-school admin off-switch: a disabled binding
        # resolves to NO school → the caller provisions no membership and the
        # RLS-scoped app returns zero rows (fail-closed).
        row = await self.session.execute(
            text(
                "SELECT school_id::text FROM lti_deployment "
                "WHERE registration_id = :rid AND deployment_id = :did "
                "AND is_active LIMIT 1"
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
        # AUTH email is SYNTHETIC + registration-namespaced (never the claim email)
        # — see synthetic_lti_email / H1. The real claim email is display-only.
        auth_email = synthetic_lti_email(registration_id, sub)
        claim_email = claims.get("email")
        name = claims.get("name") or claims.get("given_name") or claim_email or sub
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
            user_id = await self._create_auth_user(auth_email, name, claim_email)
            await self.session.execute(
                text(
                    "INSERT INTO lti_user_identity (registration_id, sub, user_id) "
                    "VALUES (:rid, :sub, :uid) ON CONFLICT DO NOTHING"
                ),
                {"rid": registration_id, "sub": sub, "uid": user_id},
            )

        # attach (or update) school membership — STAFF ONLY (Q5 privacy gate).
        # A membership is what grants school-scoped RLS access to reports, so we
        # create it iff the resolved role is staff (admin/teacher). A 'student'
        # (or any unknown role, which map_lti_roles floors to 'student') is still
        # provisioned as an account + lti_user_identity and still gets a session,
        # but with NO membership → empty school_ids → RLS denies every report.
        if school_id and school_role in _STAFF_SCHOOL_ROLES:
            await self.session.execute(
                text(
                    "INSERT INTO user_schools (user_id, school_id, school_role, is_primary) "
                    "VALUES (:uid, :sid, :role, TRUE) "
                    "ON CONFLICT (user_id, school_id) "
                    "DO UPDATE SET school_role = EXCLUDED.school_role"
                ),
                {"uid": user_id, "sid": school_id, "role": school_role},
            )
        elif school_id:
            logger.info(
                "LTI launch for sub=%s resolved school_role=%s -> no membership "
                "granted (staff-only tool)",
                sub,
                school_role,
            )
        await self.session.commit()

        return LaunchResult(
            user_id=user_id, email=auth_email, school_id=school_id,
            school_role=school_role, registration_id=registration_id,
            deployment_id=deployment_id,
            context_label=context.get("label") if isinstance(context, dict) else None,
            resource_link_id=rlink.get("id") if isinstance(rlink, dict) else None,
        )

    # ---- session handoff ticket (bridge into a real Supabase session) --------
    async def mint_handoff_ticket(
        self, user_id: str, school_id: Optional[str], email: str
    ) -> str:
        """Mint a single-use, 60s handoff ticket for the provisioned user.

        The bridge exchanges this (via /lti/consume-ticket) for a magic-link
        session. school_id + the exact provisioned email travel in the row so
        the bridge scopes the final redirect and mints the session for the same
        identity the service computed.
        """
        ticket = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(seconds=HANDOFF_TTL_SECONDS)
        await self.session.execute(
            text(
                "INSERT INTO lti_handoff_ticket "
                "(ticket, user_id, school_id, email, expires_at) "
                "VALUES (:t, :u, :s, :e, :exp)"
            ),
            {"t": ticket, "u": user_id, "s": school_id, "e": email, "exp": expires},
        )
        await self.session.commit()
        return ticket

    async def consume_handoff_ticket(self, ticket: str) -> Optional[dict]:
        """Atomically consume a handoff ticket (single-use).

        Returns {user_id, email, school_id} on success, or None when the ticket
        is invalid / expired / already used — the bridge rejects all identically.
        Mirrors the _consume_state single-statement guard (no read-then-write
        race: the UPDATE ... WHERE consumed=FALSE AND expires_at>now() is atomic).
        """
        row = await self.session.execute(
            text(
                "UPDATE lti_handoff_ticket SET consumed = TRUE "
                "WHERE ticket = :t AND consumed = FALSE AND expires_at > now() "
                "RETURNING user_id::text, email, school_id::text"
            ),
            {"t": ticket},
        )
        r = row.first()
        await self.session.commit()
        return dict(r._mapping) if r else None

    async def _create_auth_user(
        self, email: str, name: str, claim_email: Optional[str] = None
    ) -> str:
        """Provision a confirmed Supabase auth user (the new-user trigger assigns
        the platform 'user' role + profile).

        ``email`` is the SYNTHETIC, registration-namespaced auth identity (see
        synthetic_lti_email / H1) — it is what the ``WHERE email =`` lookup and the
        INSERT key on, so it can only ever match / create the LTI account for its
        exact (registration_id, sub). ``claim_email`` is the real platform email; it
        is stored in ``raw_user_meta_data`` as DISPLAY metadata only and never keys
        the lookup, the insert, or any auth-bearing row.
        """
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
                    raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
                    -- GoTrue scans these as NOT NULL strings; '' avoids the
                    -- "Database error querying schema" 500 on later auth queries.
                    confirmation_token, recovery_token, email_change,
                    email_change_token_new, email_change_token_current,
                    phone_change, phone_change_token, reauthentication_token)
                VALUES (
                    uuid_generate_v7(), '00000000-0000-0000-0000-000000000000',
                    'authenticated', 'authenticated', CAST(:email AS text), now(),
                    '{"provider":"lti","providers":["lti"]}'::jsonb,
                    jsonb_strip_nulls(jsonb_build_object(
                        'full_name', CAST(:name AS text),
                        -- display only; NEVER used for auth lookup/creation.
                        'lti_email', CAST(:claim_email AS text))), now(), now(),
                    '', '', '', '', '', '', '', '')
                RETURNING id::text
                """
            ),
            {"email": email, "name": name, "claim_email": claim_email},
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


def generate_tool_keypair(kid_prefix: str = "gains-tool") -> tuple[str, str]:
    """Generate a fresh RSA-2048 tool keypair, returning (private_pem, tool_kid).

    SINGLE source of the tool RSA keypair generation — both seed_lti.py and the
    admin LTI service call this so there is exactly one keygen path (no
    copy-pasted `rsa.generate_private_key(...)`). The kid is unique per
    registration so the tool JWKS can publish several keys side by side.
    """
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat,
    )

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()
    ).decode()
    kid = f"{kid_prefix}-{secrets.token_hex(4)}"
    return private_pem, kid


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
