"""LTI 1.3 endpoints — OIDC login init, launch, and tool JWKS.

These are the LTI *protocol* surface (they need the DB + the tool keypair), so
they live in FastAPI, not Next.js. They are unauthenticated by design: the
platform (Schoology/Canvas) drives them and trust is established by the signed
id_token, not a session.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.services.lti_service import LtiError, LtiService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lti", tags=["LTI"])

# Where to send the browser after a verified launch. The selected-school cookie
# / Supabase session bridge is layered on by the app shell; for the launch we
# carry the resolved school_id so the report renders the right tenant.
LTI_REDIRECT_BASE = os.getenv("LTI_REDIRECT_BASE", "/app/reports/standard-summary")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:3000")


def _tool_launch_url(request: Request) -> str:
    # The redirect_uri we registered with the platform — our /lti/launch.
    return f"{PUBLIC_BASE_URL}/api/v1/lti/launch"


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

    # Hand off into the app, carrying the resolved tenant. A signed launch
    # ticket / Supabase session is set by the bridge; here we redirect with the
    # school_id so the report scopes correctly.
    params = []
    if result.school_id:
        params.append(f"school_id={result.school_id}")
    params.append(f"lti_uid={result.user_id}")
    target = f"{PUBLIC_BASE_URL}{LTI_REDIRECT_BASE}"
    if params:
        target += "?" + "&".join(params)
    resp = RedirectResponse(target, status_code=302)
    # Short-lived, cross-site-capable launch cookie for the app shell to pick up.
    resp.set_cookie(
        "gains_lti_launch", result.user_id, max_age=300, httponly=True,
        secure=True, samesite="none",
    )
    return resp


@router.get("/.well-known/jwks.json")
async def tool_jwks(db: AsyncSession = Depends(get_db)):
    """Publish the tool's public keys (for outbound Advantage service calls)."""
    service = LtiService(db)
    return await service.tool_jwks()
