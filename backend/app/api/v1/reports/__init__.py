"""Composed report endpoints, split by report family into a package.

Each route delegates to a single ``ReportService.build_*`` method. This package
replaces the former single ``reports.py`` module; route paths, params, response
models, permissions and rate limits are byte-identical — only the file layout
changed (verified by an empty golden-master + OpenAPI diff).

Modules:
    per_assessment  QRA / SDD / IAD / QSR + 3 QRA paginated variants (item-scoped)
    yearly          YTD Longitudinal, Standard Summary, Strand Summary
    dashboard       dashboard-overview + strand-rows (front-filter aggregates)
    data_quality    standards-alignment coverage audit
    exports         the 10 ``*/export.xlsx`` routes
    _shared         _require_ytd_scope + _xlsx_response helpers
"""

from fastapi import APIRouter

from . import dashboard, data_quality, exports, per_assessment, yearly

router = APIRouter(prefix="/reports", tags=["Reports"])
router.include_router(per_assessment.router)
router.include_router(yearly.router)
router.include_router(dashboard.router)
router.include_router(data_quality.router)
router.include_router(exports.router)

__all__ = ["router"]
