"""LTI 1.3 endpoints — OIDC login init, launch, and tool JWKS.

These are the LTI *protocol* surface (they need the DB + the tool keypair), so
they live in FastAPI, not Next.js. They are unauthenticated by design: the
platform (Schoology/Canvas) drives them and trust is established by the signed
id_token, not a session.
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Form, Header, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db
from app.core.exceptions import AppException
from app.core.rate_limit import limiter
from app.services.lti_service import LtiError, LtiService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lti", tags=["LTI"])

# Origin the browser is on. After a verified launch we hand off to the Next
# session bridge (/api/lti/bridge) here; the bridge owns the post-session
# redirect target (LTI_REDIRECT_BASE lives on the Next side now).
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:3000")


def _tool_launch_url(request: Request) -> str:
    # The redirect_uri we registered with the platform — our /lti/launch.
    return f"{PUBLIC_BASE_URL}/api/v1/lti/launch"


async def require_bridge_secret(
    x_lti_bridge_secret: str | None = Header(default=None),
) -> None:
    """Constant-time machine-auth check for the session bridge; fails CLOSED.

    Modeled on ingestion.py:require_ingestion_secret. When
    ``LTI_BRIDGE_SECRET`` is unset/empty, every caller is rejected BEFORE any
    compare (never ``compare_digest(x, "")``); a missing/wrong header is likewise
    rejected. The Next /api/lti/bridge route is the only intended caller.
    """
    configured = settings.LTI_BRIDGE_SECRET
    if (
        not configured
        or not x_lti_bridge_secret
        or not hmac.compare_digest(x_lti_bridge_secret, configured)
    ):
        raise AppException("unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)


class ConsumeTicketRequest(BaseModel):
    ticket: str


async def _login(request, db, *, iss, login_hint, client_id, lti_message_hint,
                 target_link_uri):
    service = LtiService(db)
    try:
        redirect = await service.start_login(
            issuer=iss,
            login_hint=login_hint or "",
            client_id=client_id,
            lti_message_hint=lti_message_hint,
            target_link_uri=target_link_uri,
            tool_launch_url=_tool_launch_url(request),
        )
    except LtiError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    return RedirectResponse(redirect, status_code=302)


@router.get("/login")
@limiter.limit(settings.RATE_LIMIT_LTI)
async def login_get(
    request: Request,
    iss: str,
    login_hint: Optional[str] = None,
    client_id: Optional[str] = None,
    lti_message_hint: Optional[str] = None,
    target_link_uri: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """OIDC third-party login init (GET form)."""
    return await _login(request, db, iss=iss, login_hint=login_hint,
                        client_id=client_id, lti_message_hint=lti_message_hint,
                        target_link_uri=target_link_uri)


@router.post("/login")
@limiter.limit(settings.RATE_LIMIT_LTI)
async def login_post(
    request: Request,
    iss: str = Form(...),
    login_hint: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    lti_message_hint: Optional[str] = Form(None),
    target_link_uri: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """OIDC third-party login init (POST form)."""
    return await _login(request, db, iss=iss, login_hint=login_hint,
                        client_id=client_id, lti_message_hint=lti_message_hint,
                        target_link_uri=target_link_uri)


@router.post("/launch")
@limiter.limit(settings.RATE_LIMIT_LTI)
async def launch(
    request: Request,
    id_token: str = Form(...),
    state: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Receive the platform's form-POSTed id_token, validate, provision, redirect."""
    service = LtiService(db)
    try:
        claims, registration_id = await service.validate_launch(id_token, state)
        result = await service.provision(registration_id, claims)
    except LtiError as e:
        logger.warning("LTI launch rejected: %s", e)
        return JSONResponse(status_code=400, content={"error": str(e)})

    # Hand off into the app via a single-use ticket. The tenant (school_id) and
    # the exact provisioned email travel in the ticket ROW (not query params /
    # cookies): the Next bridge consumes the ticket, mints a real Supabase
    # session for that email, and re-applies school_id on the final redirect.
    ticket = await service.mint_handoff_ticket(
        result.user_id, result.school_id, result.email
    )
    return RedirectResponse(
        f"{PUBLIC_BASE_URL}/api/lti/bridge?ticket={ticket}", status_code=302
    )


@router.post("/consume-ticket")
@limiter.limit(settings.RATE_LIMIT_LTI)
async def consume_ticket(
    request: Request,
    payload: ConsumeTicketRequest,
    _: None = Depends(require_bridge_secret),
    db: AsyncSession = Depends(get_db),
):
    """Machine-auth: exchange a single-use handoff ticket for the user identity.

    Called ONLY by the Next /api/lti/bridge route (X-LTI-Bridge-Secret). Uses the
    privileged ``get_db`` session (no user JWT — an RLS session would resolve to
    an empty tenant set), same as the ingestion machine path. Invalid / expired /
    already-consumed tickets all return 400 {"error":"invalid_ticket"} — the
    bridge never distinguishes them.
    """
    service = LtiService(db)
    row = await service.consume_handoff_ticket(payload.ticket)
    if row is None:
        return JSONResponse(status_code=400, content={"error": "invalid_ticket"})
    return {
        "user_id": row["user_id"],
        "email": row["email"],
        "school_id": row["school_id"],
    }


@router.get("/.well-known/jwks.json")
async def tool_jwks(db: AsyncSession = Depends(get_db)):
    """Publish the tool's public keys (for outbound Advantage service calls)."""
    service = LtiService(db)
    return await service.tool_jwks()
