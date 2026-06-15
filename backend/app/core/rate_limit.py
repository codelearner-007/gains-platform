"""Rate limiting configuration using slowapi."""

import base64
import binascii
import json
import logging

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import settings
from app.core.dependencies import extract_token_from_cookies

logger = logging.getLogger(__name__)


def _sub_from_unverified_jwt(token: str) -> str | None:
    """Read the `sub` claim from a JWT payload WITHOUT verifying the signature.

    This is used ONLY to derive a stable rate-limit bucket key, never for
    authorization (the endpoint dependencies still fully verify the token).
    Forging `sub` only changes which bucket the caller shares — the limit
    still applies — so an unverified read is acceptable here and keeps the
    key function synchronous (slowapi requires a sync key_func).
    """
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload_b64 = parts[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)  # restore base64 padding
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) and sub else None


def _user_or_remote_key(request: Request) -> str:
    """Rate-limit key: authenticated user id when available, else remote address.

    Keying on the user id prevents every authenticated caller behind the same
    proxy / NAT from sharing one bucket (the default ``get_remote_address``
    would collapse them all onto the proxy IP). Unauthenticated requests still
    fall back to the remote address. Same limits, per-identity buckets.
    """
    # Priority 1: Authorization: Bearer <token>
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    token: str | None = None
    if auth and auth.lower().startswith("bearer "):
        token = auth[len("bearer "):].strip()
    # Priority 2: Supabase SSR cookies (Next.js rewrite flows)
    if not token:
        token = extract_token_from_cookies(request)

    if token:
        sub = _sub_from_unverified_jwt(token)
        if sub:
            return f"user:{sub}"

    return f"ip:{get_remote_address(request)}"


def _build_limiter() -> Limiter:
    if settings.REDIS_ENABLE_RATE_LIMIT_STORAGE and settings.REDIS_URL:
        try:
            return Limiter(
                key_func=_user_or_remote_key,
                storage_uri=settings.REDIS_URL,
                storage_options={
                    "socket_connect_timeout": settings.REDIS_CONNECT_TIMEOUT_SECONDS,
                    "socket_timeout": settings.REDIS_SOCKET_TIMEOUT_SECONDS,
                },
            )
        except Exception:
            logger.warning(
                "Redis rate-limit storage unavailable; falling back to in-memory limiter",
                exc_info=True,
            )
    return Limiter(key_func=_user_or_remote_key)


limiter = _build_limiter()
