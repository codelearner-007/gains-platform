"""Composed report endpoints.

Each route here delegates to a single ``ReportService.build_*`` method.
The currently exposed reports are: Question Response Analysis Interactive,
Standards Deep Dive interactive, Incorrect Answer Details, Year To Date -
Longitudinal Report, Standard Summary, and Strand Summary.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import require_permission
from app.core.rate_limit import limiter
from app.middleware.rls import get_db_with_rls
from app.schemas.reports import (
    AlignmentDataQualityReport,
    DashboardOverviewPayload,
    DashboardStrandRowsPage,
    IncorrectAnswerDetailsPayload,
    QraByStandardTeacherPayload,
    QraByTeacherPayload,
    QraPaginatedPayload,
    QuestionResponseAnalysisPayload,
    QuestionSummaryPointsPayload,
    StandardSummaryFilters,
    StandardSummaryPayload,
    StandardsDeepDivePayload,
    StrandSummaryFilters,
    StrandSummaryPayload,
    YearToDatePerformancePayload,
    YTDFilters,
)
from app.services.report_export_service import (
    report_to_xlsx,
    sanitize_xlsx_filename,
    workbook_to_bytes,
)
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _xlsx_response(kind: str, item_name: Optional[str], payload: object) -> StreamingResponse:
    """Serialize ``payload`` to a workbook and stream it as an attachment.

    ``item_name`` is sanitized (CR/LF/quotes stripped) before going into the
    ``Content-Disposition`` header to prevent header injection.
    """
    wb = report_to_xlsx(kind, payload)
    data = workbook_to_bytes(wb)
    filename = sanitize_xlsx_filename(kind, item_name)
    headers = {"content-disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        iter((data,)),
        media_type=_XLSX_MEDIA_TYPE,
        headers=headers,
    )


@router.get(
    "/question-response-analysis/{item_id}",
    response_model=QuestionResponseAnalysisPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def question_response_analysis(
    item_id: str,
    instructor: Optional[str] = Query(None, max_length=2000),
    db: AsyncSession = Depends(get_db_with_rls),
) -> QuestionResponseAnalysisPayload:
    """Composed QRA payload matching frontend dataset.ts. Requires: reports:read

    ``instructor`` (OPTIONAL) is a single comma-separated string of section
    instructors (e.g. ``"Jane Doe,John Smith"``). When provided, the merged
    multi-section report is narrowed to the sections taught by ANY of the
    listed instructors. Empty/omitted = no filter (full merge, byte-identical).
    """
    instructor = instructor.strip() if instructor and instructor.strip() else None
    service = ReportService(db)
    return await service.build_question_response_analysis(item_id, instructor)


@router.get(
    "/standards-deep-dive/{item_id}",
    response_model=StandardsDeepDivePayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def standards_deep_dive(
    item_id: str,
    instructor: Optional[str] = Query(None, max_length=2000),
    db: AsyncSession = Depends(get_db_with_rls),
) -> StandardsDeepDivePayload:
    """Per-assessment SDD payload (mirrors PBIX page #16). Requires: reports:read

    ``instructor`` (OPTIONAL) is a single comma-separated string of section
    instructors (e.g. ``"Jane Doe,John Smith"``). When provided, the merged
    multi-section report is narrowed to the sections taught by ANY of the
    listed instructors. Empty/omitted = no filter (full merge, byte-identical).
    """
    instructor = instructor.strip() if instructor and instructor.strip() else None
    service = ReportService(db)
    return await service.build_standards_deep_dive(item_id, instructor)


@router.get(
    "/incorrect-answer-details/{item_id}/{question_id}",
    response_model=IncorrectAnswerDetailsPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def incorrect_answer_details(
    item_id: str,
    question_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> IncorrectAnswerDetailsPayload:
    """Drill-through deep dive for a single question (PBIX page #20).

    Returns the assessment header, the question context (text, correct answer,
    standards, description), KPI strip, full distractor breakdown, and every
    student × answer attempt. Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_incorrect_answer_details(item_id, question_id)


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
    assessment_type); ``category`` carries the assessment type. ``section`` is
    accepted for filter-bar compatibility but not applied at this grain.
    Requires: reports:read.
    """
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
    section: Optional[str] = None,
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
            section=section,
        ),
        cards_only=cards_only,
    )


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
    section: Optional[str] = None,
    strand: Optional[str] = None,
    strands_only: bool = False,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StrandSummaryPayload:
    """School-wide strand rollup (mirrors PBIX page #15).

    Aggregates cube_question_summary by strand across all assessments in
    the selected scope. All filter params optional; default = whole-school
    rollup. The ``strand`` filter narrows the per-standard drill list
    when the client cross-filters on a strand selection. ``strands_only=true``
    is the dashboard's lean path — returns just ``strands_rollup`` (+ bands),
    skipping the per-standard rollup and school-wide KPI queries it never reads.
    Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_strand_summary(
        StrandSummaryFilters(
            session=session,
            category=category,
            subject=subject,
            grade=grade,
            section=section,
            strand=strand,
        ),
        strands_only=strands_only,
    )


# ─── Dashboard front-filter aggregates ────────────────────────────────────


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


# ─── Paginated reports (PBIX ord 6/7/16, 11, 12, 13) ──────────────────────


@router.get(
    "/question-summary-paginated/{item_id}",
    response_model=QuestionSummaryPointsPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def question_summary_paginated(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> QuestionSummaryPointsPayload:
    """Per-(student × question) partial-credit matrix for the QSR paginated
    family (PBIX ord 6, 7, 16). Each cell is ``points_received`` (may be
    fractional); "# Correct Answers" is SUM(received) and every Score% is
    SUM(received)/SUM(possible) — matching the legacy SSRS PDFs, the xlsx
    export, and the grade-average KPI. Variants (base / teacher subtotal /
    redacted) are rendered from this same payload via query-string flags on
    the frontend. Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_question_summary_matrix_points(item_id)


@router.get(
    "/question-response-analysis-paginated/{item_id}",
    response_model=QraPaginatedPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def question_response_analysis_paginated(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> QraPaginatedPayload:
    """PBIX ord 11. Flat list of questions with per-question student-name
    list for every incorrect answer. Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_qra_paginated(item_id)


@router.get(
    "/question-response-analysis-by-teacher/{item_id}",
    response_model=QraByTeacherPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def question_response_analysis_by_teacher(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> QraByTeacherPayload:
    """PBIX ord 12. Questions grouped by classroom instructor with per-teacher
    average shown in the group header. Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_qra_by_teacher(item_id)


@router.get(
    "/question-response-analysis-by-standard-and-teacher/{item_id}",
    response_model=QraByStandardTeacherPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def question_response_analysis_by_standard_and_teacher(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> QraByStandardTeacherPayload:
    """PBIX ord 13. Questions grouped by CPALMS standard then by classroom
    instructor, with both standard-wide and teacher-within-standard averages.
    Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_qra_by_standard_teacher(item_id)


# ─── XLSX export routes (server-side openpyxl, Phase B / B2+B3) ────────────
#
# Each route reuses the SAME ``ReportService.build_*`` method as its JSON
# sibling, enforces the SAME ``reports:read`` permission + RLS school scoping,
# is slowapi rate-limited, and returns a StreamingResponse with a sanitized
# attachment filename.


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
    section: Optional[str] = None,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StreamingResponse:
    """XLSX export of the school-wide Standard Summary. Requires: reports:read"""
    payload = await ReportService(db).build_standard_summary(
        StandardSummaryFilters(
            session=session,
            category=category,
            subject=subject,
            grade=grade,
            section=section,
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
    section: Optional[str] = None,
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
            section=section,
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
