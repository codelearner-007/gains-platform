"""Composed report builder package (facade over per-family mixins).

The former 1851-line ``app.services.report_service`` module is split here into
one mixin per report router family — mirroring the ``app.api.v1.reports``
router package (per_assessment / yearly / dashboard) — plus a shared
``_ReportServiceBase`` holding ``__init__`` and the private helper methods.
The move is VERBATIM: method bodies, SQL strings, float-coercion helpers, and
band-threshold logic are byte-for-byte identical to the pre-split monolith, so
``ReportService`` remains a drop-in facade with unchanged behaviour.
"""

from ._helpers import _decode_html, _strip_html  # re-exported for report_export_service
from .base import _ReportServiceBase
from .dashboard import _DashboardMixin
from .per_assessment import _PerAssessmentMixin
from .yearly import _YearlyMixin


class ReportService(_PerAssessmentMixin, _YearlyMixin, _DashboardMixin, _ReportServiceBase):
    """Composed report builder (facade over the per-family mixins)."""


__all__ = ["ReportService", "_decode_html", "_strip_html"]
