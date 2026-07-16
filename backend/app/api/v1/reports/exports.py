"""XLSX export routes (server-side openpyxl).

Each route reuses the SAME ``ReportService.build_*`` method as its JSON sibling,
enforces the SAME ``reports:read`` permission + RLS school scoping, is slowapi
rate-limited, and returns a StreamingResponse with a sanitized attachment
filename. Paths, params and behaviour are byte-identical to the former
``reports.py``.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import require_permission
from app.core.rate_limit import limiter
from app.middleware.rls import get_db_with_rls
from app.schemas.reports import (
    StandardSummaryFilters,
    StrandSummaryFilters,
    YTDFilters,
)
from app.services.reports import ReportService

from ._shared import _require_ytd_scope, _xlsx_response

router = APIRouter()


@router.get(
    "/question-response-analysis/{item_id}/export.xlsx",
    dependencies=[Depends(require_permission("reports:read"))],
)
@limiter.limit(settings.RATE_LIMIT_REPORTS_EXPORT)
async def qra_export_xlsx(
    request: Request,
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StreamingResponse:
    """XLSX export of the QRA interactive report. Requires: reports:read"""
    payload = await ReportService(db).build_question_response_analysis(item_id)
    return _xlsx_response("qra", payload.assessment.item_name, payload)


@router.get(
    "/standards-deep-dive/{item_id}/export.xlsx",
    dependencies=[Depends(require_permission("reports:read"))],
)
@limiter.limit(settings.RATE_LIMIT_REPORTS_EXPORT)
async def sdd_export_xlsx(
    request: Request,
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StreamingResponse:
    """XLSX export of the Standards Deep Dive report. Requires: reports:read"""
    payload = await ReportService(db).build_standards_deep_dive(item_id)
    return _xlsx_response("sdd", payload.assessment.item_name, payload)


@router.get(
    "/incorrect-answer-details/{item_id}/{question_id}/export.xlsx",
    dependencies=[Depends(require_permission("reports:read"))],
)
@limiter.limit(settings.RATE_LIMIT_REPORTS_EXPORT)
async def iad_export_xlsx(
    request: Request,
    item_id: str,
    question_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StreamingResponse:
    """XLSX export of the Incorrect Answer Details report. Requires: reports:read"""
    payload = await ReportService(db).build_incorrect_answer_details(
        item_id, question_id
    )
    return _xlsx_response("iad", payload.assessment.item_name, payload)


@router.get(
    "/year-to-date-performance/export.xlsx",
    dependencies=[Depends(require_permission("reports:read"))],
)
@limiter.limit(settings.RATE_LIMIT_REPORTS_EXPORT)
async def ytd_export_xlsx(
    request: Request,
    session: Optional[str] = None,
    category: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    section: Optional[str] = None,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StreamingResponse:
    """XLSX export of the YTD Longitudinal matrix. Requires: reports:read"""
    _require_ytd_scope(subject, grade)
    payload = await ReportService(db).build_year_to_date_performance(
        YTDFilters(
            session=session,
            category=category,
            subject=subject,
            grade=grade,
            section=section,
        )
    )
    label = f"{payload.subject}-{payload.grade}-{payload.assessment_type}".strip("-")
    return _xlsx_response("ytd", label, payload)


@router.get(
    "/standard-summary/export.xlsx",
    dependencies=[Depends(require_permission("reports:read"))],
)
@limiter.limit(settings.RATE_LIMIT_REPORTS_EXPORT)
async def standard_summary_export_xlsx(
    request: Request,
    session: Optional[str] = None,
    category: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StreamingResponse:
    """XLSX export of the school-wide Standard Summary. Requires: reports:read"""
    payload = await ReportService(db).build_standard_summary(
        StandardSummaryFilters(
            session=session,
            category=category,
            subject=subject,
            grade=grade,
        )
    )
    return _xlsx_response("standard-summary", payload.school.name, payload)


@router.get(
    "/strand-summary/export.xlsx",
    dependencies=[Depends(require_permission("reports:read"))],
)
@limiter.limit(settings.RATE_LIMIT_REPORTS_EXPORT)
async def strand_summary_export_xlsx(
    request: Request,
    session: Optional[str] = None,
    category: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    strand: Optional[str] = None,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StreamingResponse:
    """XLSX export of the school-wide Strand Summary. Requires: reports:read"""
    payload = await ReportService(db).build_strand_summary(
        StrandSummaryFilters(
            session=session,
            category=category,
            subject=subject,
            grade=grade,
            strand=strand,
        )
    )
    return _xlsx_response("strand-summary", payload.school.name, payload)


@router.get(
    "/question-summary-paginated/{item_id}/export.xlsx",
    dependencies=[Depends(require_permission("reports:read"))],
)
@limiter.limit(settings.RATE_LIMIT_REPORTS_EXPORT)
async def qsr_export_xlsx(
    request: Request,
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StreamingResponse:
    """XLSX export of the QSR paginated matrix. Requires: reports:read

    Uses the partial-credit point model (legacy SSRS .xlsx / PDF parity), which
    intentionally differs from the count-of-green model served to the web.
    """
    payload = await ReportService(db).build_question_summary_matrix_points(item_id)
    return _xlsx_response("qsr", payload.assessment.item_name, payload)


@router.get(
    "/question-response-analysis-paginated/{item_id}/export.xlsx",
    dependencies=[Depends(require_permission("reports:read"))],
)
@limiter.limit(settings.RATE_LIMIT_REPORTS_EXPORT)
async def qra_paginated_export_xlsx(
    request: Request,
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StreamingResponse:
    """XLSX export of the QRA paginated report. Requires: reports:read"""
    payload = await ReportService(db).build_qra_paginated(item_id)
    return _xlsx_response("qra-paginated", payload.assessment.item_name, payload)


@router.get(
    "/question-response-analysis-by-teacher/{item_id}/export.xlsx",
    dependencies=[Depends(require_permission("reports:read"))],
)
@limiter.limit(settings.RATE_LIMIT_REPORTS_EXPORT)
async def qra_by_teacher_export_xlsx(
    request: Request,
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StreamingResponse:
    """XLSX export of the QRA-by-Teacher report. Requires: reports:read"""
    payload = await ReportService(db).build_qra_by_teacher(item_id)
    return _xlsx_response("qra-by-teacher", payload.assessment.item_name, payload)


@router.get(
    "/question-response-analysis-by-standard-and-teacher/{item_id}/export.xlsx",
    dependencies=[Depends(require_permission("reports:read"))],
)
@limiter.limit(settings.RATE_LIMIT_REPORTS_EXPORT)
async def qra_by_standard_teacher_export_xlsx(
    request: Request,
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StreamingResponse:
    """XLSX export of the QRA-by-Standard-and-Teacher report. Requires: reports:read"""
    payload = await ReportService(db).build_qra_by_standard_teacher(item_id)
    return _xlsx_response(
        "qra-by-standard-teacher", payload.assessment.item_name, payload
    )
