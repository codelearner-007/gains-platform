"""FastAPI dependency injection functions."""

from __future__ import annotations

import base64
import json
from typing import AsyncGenerator, Callable, Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidTokenError, PermissionDeniedError
from app.core.security import extract_user_claims, verify_token
from app.db.session import get_session_manager
from app.schemas.auth import CurrentUser

# HTTP Bearer token security scheme (auto_error=False for fallback to cookies)
security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide database session for dependency injection.

    Yields:
        AsyncSession instance

    Example:
        @router.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            ...
    """
    session_manager = get_session_manager()
    async with session_manager.session() as session:
        yield session


def _reassemble_cookie_value(cookies: dict[str, str], base_name: str) -> Optional[str]:
    """
    Reassemble possibly-chunked cookie values.

    Supabase SSR may chunk large cookies into `name.0`, `name.1`, ...
    """
    if base_name in cookies:
        return cookies[base_name]

    chunks: list[str] = []
    i = 0
    while f"{base_name}.{i}" in cookies:
        chunks.append(cookies[f"{base_name}.{i}"])
        i += 1

    return "".join(chunks) if chunks else None


def _find_supabase_auth_cookie_base_name(cookies: dict[str, str]) -> Optional[str]:
    """
    Find the base cookie name used by @supabase/ssr for session storage.

    Common patterns include:
    - sb-<project-ref>-auth-token
    - sb-<project-ref>-auth-token.0 / .1 / ...
    """
    for name in cookies.keys():
        base = name.split(".", 1)[0]
        if base.startswith("sb-") and base.endswith("-auth-token"):
            return base
    return None


def _maybe_extract_access_token(value: str) -> Optional[str]:
    """
    Extract access_token from known Supabase SSR cookie payload formats.
    """
    raw = value.strip()

    # If it already looks like a JWT, return it directly.
    if raw.count(".") == 2 and raw.startswith("eyJ"):
        return raw

    # Format: "base64-<base64(json)>"
    if raw.startswith("base64-"):
        raw = raw[len("base64-") :]
        # Fix missing padding if present
        padding = "=" * (-len(raw) % 4)
        try:
            decoded = base64.b64decode(raw + padding).decode("utf-8")
            raw = decoded.strip()
        except Exception:
            return None

    # Try JSON parse
    try:
        data = json.loads(raw)
    except Exception:
        return None

    if isinstance(data, dict):
        token = data.get("access_token") or data.get("accessToken")
        if isinstance(token, str) and token:
            return token
        # Some shapes may nest the session
        session = data.get("session") or data.get("currentSession")
        if isinstance(session, dict):
            token = session.get("access_token") or session.get("accessToken")
            if isinstance(token, str) and token:
                return token
        return None

    # Unknown/unsupported format
    return None


def extract_token_from_cookies(request: Request) -> Optional[str]:
    """
    Extract JWT token from Supabase SSR cookies.

    Supports:
    - Direct access token cookie (legacy): sb-access-token(.0/.1/...)
    - Supabase SSR auth cookie: sb-<project-ref>-auth-token(.0/.1/...) containing session JSON

    Args:
        request: FastAPI request object

    Returns:
        JWT access token or None
    """
    cookies = request.cookies

    # 1) Legacy / custom direct token cookie
    direct = _reassemble_cookie_value(cookies, "sb-access-token")
    if direct:
        return direct

    # 2) Supabase SSR auth-token cookie (contains a session payload, not a raw JWT)
    base = _find_supabase_auth_cookie_base_name(cookies)
    if not base:
        return None

    payload = _reassemble_cookie_value(cookies, base)
    if not payload:
        return None

    return _maybe_extract_access_token(payload)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> CurrentUser:
    """
    Extract and validate current user from JWT token.

    Supports token from:
    1. Authorization: Bearer <token> header (if present)
    2. Supabase SSR cookies (fallback for Next.js/Vercel rewrite flows)

    Args:
        request: FastAPI request object
        credentials: HTTP Authorization header with Bearer token (optional)

    Returns:
        CurrentUser instance with user_id, email, role, permissions

    Raises:
        HTTPException: 401 if token is invalid or expired

    Example:
        @router.get("/profile")
        async def get_profile(current_user: CurrentUser = Depends(get_current_user)):
            print(current_user.user_id, current_user.permissions)
    """
    # Priority 1: Authorization header
    token = credentials.credentials if credentials else None

    # Priority 2: Supabase SSR cookies (for Next.js/Vercel rewrite flows)
    if not token:
        token = extract_token_from_cookies(request)

    if not token:
        raise InvalidTokenError("Missing authentication token (header or Supabase SSR cookie)")

    # Always verify JWT, never blindly decode
    payload = await verify_token(token)
    claims = extract_user_claims(payload)
    return CurrentUser(**claims)


def require_permission(required_permission: str) -> Callable:
    """
    Factory function to create permission guard dependency.

    Args:
        required_permission: Permission string (e.g., "users:read_all")

    Returns:
        Dependency function that checks permission

    Raises:
        HTTPException: 403 if user lacks required permission

    Example:
        @router.post(
            "/roles",
            dependencies=[Depends(require_permission("roles:create"))]
        )
        async def create_role(...):
            ...
    """

    async def permission_checker(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if not current_user.has_permission(required_permission):
            raise PermissionDeniedError(required_permission)
        return current_user

    return permission_checker
