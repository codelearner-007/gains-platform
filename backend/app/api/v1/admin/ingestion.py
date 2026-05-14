"""Admin endpoints for the ingestion run history."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, require_permission
from app.schemas.admin import (
    IngestionRunResponse,
    TriggerIngestionRequest,
    TriggerIngestionResponse,
)
from app.schemas.auth import CurrentUser
from app.services.audit_service import AuditService
from app.services.ingestion_admin_service import IngestionAdminService

router = APIRouter(prefix="/ingestion", tags=["Admin / Ingestion"])


@router.get(
    "/runs",
    response_model=List[IngestionRunResponse],
    dependencies=[Depends(require_permission("ingestion:read"))],
)
async def list_ingestion_runs(
    school_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> List[IngestionRunResponse]:
    """List ingestion runs. Requires: ingestion:read"""
    service = IngestionAdminService(db)
    return await service.list_runs(school_id=school_id, limit=limit)


@router.get(
    "/runs/{run_id}",
    response_model=IngestionRunResponse,
    dependencies=[Depends(require_permission("ingestion:read"))],
)
async def get_ingestion_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> IngestionRunResponse:
    """Get a single ingestion run. Requires: ingestion:read"""
    service = IngestionAdminService(db)
    return await service.get_run(run_id)


@router.post(
    "/trigger",
    response_model=TriggerIngestionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission("ingestion:trigger"))],
)
async def trigger_ingestion(
    payload: TriggerIngestionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    """Trigger an ingestion run.

    The endpoint returns 202 Accepted with a ``run_id``. The actual ingestion
    is dispatched out-of-band (orchestrator picks up the ``pending`` row and
    flips it through ``running`` → ``succeeded`` / ``failed``).
    """
    service = IngestionAdminService(db)
    response = await service.trigger_run(payload)

    audit = AuditService(db)
    await audit.log_action(
        user_id=current_user.user_id,
        action="ingestion_triggered",
        module="ingestion",
        resource_id=response.run_id,
        details=payload.model_dump(exclude_unset=True),
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "run_id": response.run_id,
            "status": response.status,
            "started_at": response.started_at.isoformat(),
        },
    )
