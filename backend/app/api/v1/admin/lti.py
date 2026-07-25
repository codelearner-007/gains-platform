"""Admin endpoints for admin-dynamic LTI 1.3 binding management.

Onboard a school's LTI binding from the dashboard: paste client_id +
deployment_id, copy three tool URLs back to the district, flip per-school
enable. Every route is gated by schools:manage_lti and audit-logged (mirrors
admin/schools.py).

This admin surface is ALWAYS registered — it is NOT behind LTI_ENABLED. An admin
must be able to configure bindings before the global protocol flag flips on;
LTI_ENABLED only gates the public /api/v1/lti/* protocol routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, require_permission
from app.schemas.auth import CurrentUser
from app.schemas.lti import (
    LtiBindingUpsertRequest,
    LtiSchoolBindingResponse,
    LtiToolUrlsResponse,
)
from app.services.audit_service import AuditService
from app.services.lti_admin_service import LtiAdminService
from app.services.school_service import SchoolService

router = APIRouter(prefix="/lti", tags=["Admin / LTI"])


@router.get(
    "/tool-urls",
    response_model=LtiToolUrlsResponse,
    dependencies=[Depends(require_permission("schools:manage_lti"))],
)
async def get_tool_urls(
    db: AsyncSession = Depends(get_db),
) -> LtiToolUrlsResponse:
    """The three tool URLs to hand the district. Requires: schools:manage_lti"""
    service = LtiAdminService(db)
    return LtiToolUrlsResponse(**service.tool_urls())


@router.get(
    "/schools/{school_id}",
    response_model=LtiSchoolBindingResponse,
    dependencies=[Depends(require_permission("schools:manage_lti"))],
)
async def get_school_lti(
    school_id: str,
    db: AsyncSession = Depends(get_db),
) -> LtiSchoolBindingResponse:
    """Current LTI binding for a school (or empty). Requires: schools:manage_lti"""
    # Validate the school exists first (404 on unknown, mirrors admin/schools).
    await SchoolService(db).get_school(school_id)
    service = LtiAdminService(db)
    return LtiSchoolBindingResponse(**await service.get_school_lti(school_id))


@router.put(
    "/schools/{school_id}",
    response_model=LtiSchoolBindingResponse,
    dependencies=[Depends(require_permission("schools:manage_lti"))],
)
async def save_school_lti(
    school_id: str,
    payload: LtiBindingUpsertRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> LtiSchoolBindingResponse:
    """Create/reuse the registration and (re)bind the deployment.

    Requires: schools:manage_lti
    """
    await SchoolService(db).get_school(school_id)
    service = LtiAdminService(db)
    result = await service.save_school_lti(
        school_id=school_id,
        client_id=payload.client_id,
        deployment_id=payload.deployment_id,
        issuer=payload.issuer,
        platform_name=payload.platform_name,
        is_active=payload.is_active,
    )

    audit = AuditService(db)
    await audit.log_action(
        user_id=current_user.user_id,
        action="lti_binding_saved",
        module="schools",
        resource_id=school_id,
        details={
            "client_id": payload.client_id,
            "deployment_id": payload.deployment_id,
            "is_active": payload.is_active,
        },
    )
    await db.commit()
    return LtiSchoolBindingResponse(**result)


@router.delete(
    "/schools/{school_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("schools:manage_lti"))],
)
async def delete_school_lti(
    school_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    """Unbind a school (delete its deployment). Requires: schools:manage_lti"""
    await SchoolService(db).get_school(school_id)
    service = LtiAdminService(db)
    await service.delete_school_lti(school_id)

    audit = AuditService(db)
    await audit.log_action(
        user_id=current_user.user_id,
        action="lti_binding_deleted",
        module="schools",
        resource_id=school_id,
        details={},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
