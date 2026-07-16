"""Dashboard report builders (subject overview + strand rows).

Mirrors the ``app.api.v1.reports.dashboard`` router family. Verbatim
extraction from the former ``app.services.report_service`` monolith (pre-B2);
``self.<helper>`` / ``self.session`` resolve via MRO from ``_ReportServiceBase``.
"""

from __future__ import annotations

from typing import Optional

from app.schemas.reports import (
    DashboardOverviewPayload,
    DashboardStrandRow,
    DashboardStrandRowsPage,
    DashboardSubjectCard,
)
from app.utils.coercion import safe_str, to_int

from ._helpers import _format_pct_opt, _round_opt


class _DashboardMixin:
    """Dashboard builders composed onto :class:`ReportService`."""

    async def build_dashboard_overview(
        self,
        session: Optional[str] = None,
        category: Optional[str] = None,
        grade: Optional[str] = None,
    ) -> DashboardOverviewPayload:
        """Subject KPI cards (per-subject grade-average) + dataset-refresh
        timestamp for the dashboard front filters. Subject %s come from the same
        canonical ``AVG(cqso.grade_average)`` source as the KPI strip, scoped by
        academic year / assessment type / grade (school-wide; no section grain).
        """
        rows = await self.cube.get_subject_overview(
            session_filter=session,
            grade=grade,
            category=category,
        )
        subjects = [
            DashboardSubjectCard(
                subject=safe_str(r.get("subject")),
                grade_average=_round_opt(r.get("grade_average")),
                grade_average_pct=_format_pct_opt(r.get("grade_average")) or "—",
            )
            for r in rows
            if safe_str(r.get("subject"))
        ]
        refreshed_at = await self.cube.get_school_data_refreshed_at()
        return DashboardOverviewPayload(subjects=subjects, refreshed_at=refreshed_at)

    # Whitelist: sort key -> SQL expression for the Performance-by-Strand grid.
    # Interpolated (not bound), so the value MUST come from this dict.
    _STRAND_ROWS_SORT_SQL = {
        "date": "assessment_date",
        "strand": "strand",
        "grade": "grade",
        "standards": "total_standards",
        "questions": "total_questions",
        "average": "grade_average",
    }

    async def build_dashboard_strand_rows(
        self,
        session: Optional[str] = None,
        category: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        instructor: Optional[str] = None,
        q: Optional[str] = None,
        sort: str = "date",
        direction: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> DashboardStrandRowsPage:
        """One server-paginated page of the legacy Performance-by-Strand grid
        (one row per assessment × strand)."""
        sort_sql = self._STRAND_ROWS_SORT_SQL.get(sort, "assessment_date")
        dir_sql = "ASC" if direction.lower() == "asc" else "DESC"
        rows_raw, total = await self.cube.get_strand_rows_page(
            session_filter=session,
            category=category,
            subject=subject,
            grade=grade,
            instructor=instructor,
            q=q,
            sort_sql=sort_sql,
            dir_sql=dir_sql,
            limit=limit,
            offset=offset,
        )
        rows = [
            DashboardStrandRow(
                item_id=safe_str(r.get("item_id")),
                grade=safe_str(r.get("grade")) or None,
                strand=safe_str(r.get("strand")),
                total_standards=to_int(r.get("total_standards")),
                total_questions=to_int(r.get("total_questions")),
                grade_average=_round_opt(r.get("grade_average")),
                grade_average_pct=_format_pct_opt(r.get("grade_average")) or "—",
                assessment_date=r.get("assessment_date"),
                assessment=safe_str(r.get("assessment")) or None,
            )
            for r in rows_raw
        ]
        return DashboardStrandRowsPage(
            rows=rows, total=total, limit=limit, offset=offset
        )
