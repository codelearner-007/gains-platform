"""Audit log endpoints."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_permission
from app.schemas.common import PaginatedResponse
from app.schemas.response.audit import AuditLogResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get(
    "/logs",
    response_model=PaginatedResponse[AuditLogResponse],
    dependencies=[Depends(require_permission("audit:read"))],
)
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    module: Optional[str] = None,
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[AuditLogResponse]:
    """List audit logs with pagination and filtering. Requires: audit:read"""
    service = AuditService(db)
    return await service.list_logs_paginated(
        page=page, page_size=page_size,
        module=module, action=action, user_id=user_id,
        start_date=start_date, end_date=end_date,
    )


@router.get(
    "/modules",
    response_model=List[str],
    dependencies=[Depends(require_permission("audit:read"))],
)
async def list_audit_modules(
    db: AsyncSession = Depends(get_db),
) -> List[str]:
    """List distinct module names from audit logs (for filter dropdown)."""
    service = AuditService(db)
    return await service.list_distinct_modules()
