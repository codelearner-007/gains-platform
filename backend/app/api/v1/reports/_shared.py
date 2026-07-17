"""Shared helpers for the reports router package.

These were module-level helpers in the former single ``reports.py`` module;
behaviour is unchanged (verbatim move). Split out so the per-family route
modules (``yearly``, ``exports``) can share them without a circular import.
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.services.report_export_service import (
    report_to_xlsx,
    sanitize_xlsx_filename,
    workbook_to_bytes,
)

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _require_ytd_scope(subject: Optional[str], grade: Optional[str]) -> None:
    """Legacy YTD is parameter-scoped (Subject × Grade). Reject an unscoped
    request server-side: a whole-school matrix spans every standard column
    (900+) for every student and would exhaust memory / crash the client. The
    UI already gates on subject+grade; this enforces the same contract for
    direct API callers."""
    if not subject or not grade:
        raise HTTPException(
            status_code=422,
            detail="Year-to-Date Longitudinal requires both 'subject' and 'grade'.",
        )


def _xlsx_response(
    kind: str, item_name: Optional[str], payload: object
) -> StreamingResponse:
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
