"""Yearly / school-wide summary report routes.

Year-to-Date Longitudinal, Standard Summary and Strand Summary — all
parameter-scoped (session/subject/grade/…) rather than item-scoped. Paths,
params, response models and permissions are byte-identical to the former
``reports.py``.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.middleware.rls import get_db_with_rls
from app.schemas.reports import (
    StandardSummaryFilters,
    StandardSummaryPayload,
    StrandSummaryFilters,
    StrandSummaryPayload,
    YearToDatePerformancePayload,
    YTDFilters,
)
from app.services.report_service import ReportService

from ._shared import _require_ytd_scope

router = APIRouter()


@router.get(
    "/year-to-date-performance",
    response_model=YearToDatePerformancePayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def year_to_date_performance(
    session: Optional[str] = None,
    category: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    section: Optional[str] = None,
    db: AsyncSession = Depends(get_db_with_rls),
) -> YearToDatePerformancePayload:
    """Legacy YTD Longitudinal paginated matrix (PBIX ord 8/9/10 rdlVisual).

    POINTS-based per-(Classroom Instructor → Student) matrix with one column
    per standard assessed YTD, per-teacher subtotals, and grand totals — a
    faithful clone of the three legacy "Longitudinal Report - Year To Date"
    reports (the variant differences are purely client-side rendering). The
    report is one longitudinal unit per (session, grade, subject,
    assessment_type); ``category`` carries the assessment type. ``section``
    narrows to a class roster (applied via dim_section). Requires subject +
    grade (parameter-scoped, like legacy). Requires: reports:read.
    """
    _require_ytd_scope(subject, grade)
    service = ReportService(db)
    return await service.build_year_to_date_performance(
        YTDFilters(
            session=session,
            category=category,
            subject=subject,
            grade=grade,
            section=section,
        )
    )


@router.get(
    "/standard-summary",
    response_model=StandardSummaryPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def standard_summary(
    session: Optional[str] = None,
    category: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    cards_only: bool = False,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StandardSummaryPayload:
    """Legacy Standard Summary (PBIX page #14): per-cPalms_Standard card grid.

    Per-standard correct% = AVERAGE(cube_question_summary_overall[Grade_Average]),
    # of questions = DISTINCTCOUNT(cqso[Question_No]), scoped via dim_subject.
    ``cards_only=true`` is the report page's lean path — it skips the KPI cube
    reads (incl. the total_students fact scan) that only the dashboard renders.
    All filter params optional; default = whole-school. Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_standard_summary(
        StandardSummaryFilters(
            session=session,
            category=category,
            subject=subject,
            grade=grade,
        ),
        cards_only=cards_only,
    )


@router.get(
    "/strand-summary",
    response_model=StrandSummaryPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def strand_summary(
    session: Optional[str] = None,
    category: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    strand: Optional[str] = None,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StrandSummaryPayload:
    """Legacy Strand Summary (PBIX page #15): per-strand card repeater.

    Per-strand grade_average = AVERAGE(cqso[Grade_Average]); # standards =
    DISTINCTCOUNT(cqso[Standards]) (by code); # questions =
    DISTINCTCOUNT(cqso[Question_No]); scoped via dim_subject. The ``strand``
    param narrows the within-strand per-standard breakdown. All filter params
    optional; default = whole-school. Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_strand_summary(
        StrandSummaryFilters(
            session=session,
            category=category,
            subject=subject,
            grade=grade,
            strand=strand,
        ),
    )
