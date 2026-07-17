"""Admin overview statistics endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_permission
from app.schemas.response.admin_stats import AdminOverviewResponse
from app.services.admin_stats_service import AdminStatsService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/stats",
    response_model=AdminOverviewResponse,
    dependencies=[Depends(require_permission("users:read_all"))],
)
async def get_admin_overview(
    db: AsyncSession = Depends(get_db),
) -> AdminOverviewResponse:
    """Owner-grade admin overview: people activity, access distribution,
    per-school data coverage/freshness, recent activity, ingestion health.

    Uses the plain (RLS-exempt) DB session for cross-school aggregates.
    Requires: users:read_all
    """
    service = AdminStatsService(db)
    return await service.get_overview()
