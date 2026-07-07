"""Per-student reporting endpoints.

* ``GET /students/browse``       — dashboard "By Students" roster (paginated,
  same filter scope as the By-Assessment grid, but one summary row per student).
* ``GET /students/{uid}/report`` — one student's full multi-subject report.

Both are ``reports:read`` gated and RLS-scoped via ``get_db_with_rls``.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.middleware.rls import get_db_with_rls
from app.schemas.students import PerStudentReportPayload, StudentBrowsePage
from app.services.student_service import DEFAULT_BROWSE_PAGE_SIZE, StudentService

router = APIRouter(prefix="/students", tags=["Students"])


@router.get(
    "/browse",
    response_model=StudentBrowsePage,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def browse_students(
    session: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    subject: Optional[str] = Query(default=None),
    grade: Optional[str] = Query(default=None),
    section: Optional[str] = Query(default=None),
    instructor: Optional[str] = Query(default=None, max_length=200),
    q: Optional[str] = Query(default=None, max_length=200),
    sort: str = Query(default="name"),
    dir: str = Query(default="asc"),
    limit: int = Query(default=DEFAULT_BROWSE_PAGE_SIZE, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_with_rls),
) -> StudentBrowsePage:
    """One server-paginated page of the dashboard's By-Students roster.

    Shares the By-Assessment filter set (session/category/subject/grade/section/
    instructor) but pivots to one summary row per student: overall % (canonical
    grain-B), per-subject bands, assessment count, and standards mastery split.
    Supports name search (``q``), sort (name/overall/assessments/subjects +
    ``dir``) and ``limit``/``offset``. Requires: reports:read."""
    q_norm = q.strip() if q and q.strip() else None
    service = StudentService(db)
    return await service.browse_students(
        session_filter=session,
        category=category,
        subject=subject,
        grade=grade,
        section=section,
        instructor=instructor,
        q=q_norm,
        sort=sort,
        direction=dir,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{uid}/report",
    response_model=PerStudentReportPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def student_report(
    uid: str,
    session: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db_with_rls),
) -> PerStudentReportPayload:
    """Full multi-subject report for one student (canonical grain-B).

    ``session`` (optional) scopes to one academic year; omitted = all sessions
    the student has data for. Every figure reconciles with the assessment /
    dashboard reports. Requires: reports:read."""
    service = StudentService(db)
    return await service.build_student_report(uid, session)
