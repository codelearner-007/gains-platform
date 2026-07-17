"""Data-quality report routes (standards-alignment coverage audit)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.middleware.rls import get_db_with_rls
from app.schemas.reports import AlignmentDataQualityReport
from app.services.reports import ReportService

router = APIRouter()


@router.get(
    "/data-quality/standards-alignment",
    response_model=AlignmentDataQualityReport,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def standards_alignment_data_quality(
    db: AsyncSession = Depends(get_db_with_rls),
) -> AlignmentDataQualityReport:
    """Tenant-scoped audit of standards-alignment coverage per assessment.

    Surfaces assessments whose Schoology CSV shipped no ``Standards`` columns
    (because the underlying questions weren't aligned to learning objectives
    in Schoology), so admins know which items to flag back to teachers for
    alignment before SDD / Strand / Standard reports can populate.
    Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_alignment_data_quality()
