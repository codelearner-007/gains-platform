"""Dashboard front-filter aggregate routes.

Subject KPI cards + dataset-refresh timestamp, and the server-paginated
Performance-by-Strand grid that feed the ``/app`` analytics dashboard. Paths,
params and response models are byte-identical to the former ``reports.py``.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.middleware.rls import get_db_with_rls
from app.schemas.reports import DashboardOverviewPayload, DashboardStrandRowsPage
from app.services.report_service import ReportService

router = APIRouter()


@router.get(
    "/dashboard-overview",
    response_model=DashboardOverviewPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def dashboard_overview(
    session: Optional[str] = None,
    category: Optional[str] = None,
    grade: Optional[str] = None,
    db: AsyncSession = Depends(get_db_with_rls),
) -> DashboardOverviewPayload:
    """Subject KPI cards (per-subject grade-average) + dataset-refresh timestamp
    for the dashboard front filters. School-wide (no section/instructor grain,
    like the KPI strip), scoped by academic year / assessment type / grade.
    Requires: reports:read"""
    service = ReportService(db)
    return await service.build_dashboard_overview(
        session=session, category=category, grade=grade
    )


@router.get(
    "/strand-rows",
    response_model=DashboardStrandRowsPage,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def strand_rows(
    session: Optional[str] = None,
    category: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    instructor: Optional[str] = Query(default=None, max_length=200),
    q: Optional[str] = Query(default=None, max_length=200),
    sort: str = Query(default="date"),
    dir: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_with_rls),
) -> DashboardStrandRowsPage:
    """One server-paginated page of the legacy Performance-by-Strand grid (one
    row per assessment × strand): grade, strand, total standards/questions,
    grade average, assessment date + name. Same canonical strand grade-average
    as the SDD/QRA strand tables. Requires: reports:read"""
    q_norm = q.strip() if q and q.strip() else None
    service = ReportService(db)
    return await service.build_dashboard_strand_rows(
        session=session,
        category=category,
        subject=subject,
        grade=grade,
        instructor=instructor,
        q=q_norm,
        sort=sort,
        direction=dir,
        limit=limit,
        offset=offset,
    )
