"""Pydantic models for the admin-dynamic LTI binding endpoints.

Back the admin-only surface:

    GET    /api/v1/admin/lti/tool-urls          → LtiToolUrlsResponse
    GET    /api/v1/admin/lti/schools/{id}       → LtiSchoolBindingResponse
    PUT    /api/v1/admin/lti/schools/{id}        → LtiBindingUpsertRequest → …
    DELETE /api/v1/admin/lti/schools/{id}       → 204

All gated by schools:manage_lti. Response shapes NEVER carry tool_private_key.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LtiToolUrlsResponse(BaseModel):
    """The three tool URLs an admin copies back to the district (+ tool kid)."""

    login_init: str
    launch: str
    jwks: str
    tool_kid: Optional[str] = None


class LtiBinding(BaseModel):
    """A school's resolved binding (deployment + its registration). No key."""

    registration_id: str
    issuer: str
    client_id: str
    platform_name: Optional[str] = None
    deployment_id: str
    is_active: bool
    tool_kid: str


class LtiSchoolBindingResponse(BaseModel):
    """Binding-or-empty shape for the dialog to render."""

    school_id: str
    bound: bool
    binding: Optional[LtiBinding] = None


class LtiBindingUpsertRequest(BaseModel):
    """Body for PUT /admin/lti/schools/{id}.

    ``issuer`` is optional — it defaults server-side to the Schoology issuer, so
    the admin only pastes the district's client_id + deployment_id.
    """

    client_id: str = Field(min_length=1)
    deployment_id: str = Field(min_length=1)
    platform_name: Optional[str] = None
    is_active: bool = True
    issuer: Optional[str] = None
