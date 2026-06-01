"""JWT validation and security utilities."""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import httpx
from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import InvalidTokenError

logger = logging.getLogger(__name__)

# Cache for JWKS keys with TTL.
_jwks_cache: Dict[str, Any] = {}
_jwks_cache_timestamp: Optional[float] = None
_jwks_cache_ttl: int = 3600  # 1 hour
_jwks_lock = asyncio.Lock()


async def _refresh_jwks() -> Dict[str, Any]:
    """Force-fetch JWKS from Supabase, bypassing the cache."""
    global _jwks_cache, _jwks_cache_timestamp

    jwks_url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(jwks_url)
            response.raise_for_status()
            _jwks_cache = response.json()
            _jwks_cache_timestamp = time.time()
            return _jwks_cache
    except httpx.TimeoutException as exc:
        raise InvalidTokenError("JWKS fetch timeout (10s)") from exc
    except Exception as exc:
        raise InvalidTokenError(f"Failed to fetch JWKS: {exc}") from exc


async def fetch_jwks(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Fetch JWKS with TTL caching. Concurrent callers share a single in-flight fetch.

    Args:
        force_refresh: when True, bypass the cache (e.g. on suspected key rotation).
    """
    if not force_refresh and _jwks_cache and _jwks_cache_timestamp:
        if time.time() - _jwks_cache_timestamp < _jwks_cache_ttl:
            return _jwks_cache

    async with _jwks_lock:
        # Re-check inside lock to avoid duplicate fetches under contention.
        if not force_refresh and _jwks_cache and _jwks_cache_timestamp:
            if time.time() - _jwks_cache_timestamp < _jwks_cache_ttl:
                return _jwks_cache
        return await _refresh_jwks()


def verify_token_hs256(token: str) -> Dict[str, Any]:
    """Verify JWT token using HS256 algorithm (legacy fallback)."""
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            audience=settings.JWT_AUDIENCE,
        )
    except JWTError as exc:
        raise InvalidTokenError(f"HS256 validation failed: {exc}") from exc


def _decode_with_jwks(token: str, jwks_data: Dict[str, Any], kid: str) -> Dict[str, Any]:
    signing_key = next(
        (key for key in jwks_data.get("keys", []) if key.get("kid") == kid),
        None,
    )
    if not signing_key:
        raise InvalidTokenError(f"No matching key found for kid: {kid}")
    return jwt.decode(
        token,
        signing_key,
        algorithms=["ES256", "RS256"],
        audience=settings.JWT_AUDIENCE,
    )


async def verify_token_jwks(token: str) -> Dict[str, Any]:
    """
    Verify JWT token using JWKS (ES256/RS256). On signature failure, refresh
    JWKS once (handles key rotation mid-cache-TTL) before giving up.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise InvalidTokenError(f"JWKS validation failed: {exc}") from exc

    kid = unverified_header.get("kid")
    if not kid:
        raise InvalidTokenError("No 'kid' found in token header")

    jwks_data = await fetch_jwks()
    try:
        return _decode_with_jwks(token, jwks_data, kid)
    except JWTError as first_error:
        # Likely key rotation. Force refresh and retry once.
        logger.warning("JWT verification failed, refreshing JWKS once: %s", first_error)
        jwks_data = await fetch_jwks(force_refresh=True)
        try:
            return _decode_with_jwks(token, jwks_data, kid)
        except JWTError as exc:
            raise InvalidTokenError(f"JWKS validation failed: {exc}") from exc
    except InvalidTokenError as first_error:
        # No matching kid — refresh once in case keys rotated.
        logger.warning("JWT kid not found, refreshing JWKS once: %s", first_error)
        jwks_data = await fetch_jwks(force_refresh=True)
        return _decode_with_jwks(token, jwks_data, kid)


async def verify_token(token: str) -> Dict[str, Any]:
    """Verify JWT token using the configured method (JWKS or HS256, no silent fallback)."""
    if settings.USE_JWKS:
        return await verify_token_jwks(token)
    return verify_token_hs256(token)


def extract_user_claims(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract user claims from JWT payload."""
    return {
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "user_role": payload.get("user_role", "user"),
        "hierarchy_level": payload.get("hierarchy_level", 100),
        "permissions": payload.get("permissions", []),
        "school_ids": payload.get("school_ids", []),
        "primary_school_id": payload.get("primary_school_id"),
        "is_super_admin": payload.get("is_super_admin", False),
    }
