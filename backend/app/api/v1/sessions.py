"""Session management endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.schemas.auth import CurrentUser
from app.schemas.response.session import SessionListResponse
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["Sessions"])


def _extract_session_id(request: Request) -> Optional[str]:
    """Extract session_id from the JWT payload if available.

    Supabase JWTs include a 'session_id' claim that identifies
    the current auth session.
    """
    import base64
    import json

    # Try Authorization header first
    auth_header = request.headers.get("authorization", "")
    token: Optional[str] = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]

    # Fallback to cookie extraction
    if not token:
        from app.core.dependencies import extract_token_from_cookies

        token = extract_token_from_cookies(request)

    if not token:
        return None

    try:
        # Decode JWT payload without verification (already verified by get_current_user)
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        # Fix padding
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("session_id")
    except Exception:
        return None


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SessionListResponse:
    """List active sessions for the current user."""
    current_session_id = _extract_session_id(request)
    service = SessionService(db)
    return await service.list_sessions(current_user.user_id, current_session_id)


@router.delete("/{session_id}")
async def revoke_session(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Revoke a specific session. Cannot revoke the current session."""
    current_session_id = _extract_session_id(request)
    if current_session_id and session_id == current_session_id:
        raise HTTPException(status_code=400, detail="Cannot revoke current session")

    service = SessionService(db)
    await service.revoke_session(session_id, current_user.user_id)
    return {"message": "Session revoked"}
