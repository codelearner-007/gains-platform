"""Module-level helpers + constants shared across the report builders.

Verbatim extraction from the former ``app.services.report_service`` module
(pre-B2 monolith). ``_decode_html`` / ``_strip_html`` are re-exported from the
package ``__init__`` because ``report_export_service`` imports them.
"""

from __future__ import annotations

import html as _html
import logging
import re
from typing import Any, Optional

from app.core.constants import PERF_BAND_HIGH, PERF_BAND_MID
from app.utils.coercion import to_float


_ALIGNMENT_REMEDIATION = (
    "Open this assessment in Schoology, edit each question, and use "
    '"Align Learning Objective" to attach the relevant standards. '
    "Re-ingest after the next Export Stats download."
)


def _classify_alignment(
    questions_total: int, questions_with_alignment: int
) -> str:
    """Map question-level coverage onto the alignment_status enum."""
    if questions_total == 0:
        return "missing"
    if questions_with_alignment == 0:
        return "missing"
    if questions_with_alignment == questions_total:
        return "full"
    return "partial"


def _classify_alignment_cause(
    questions_total: int,
    questions_with_alignment: int,
    nonempty_standards_count: int,
    distinct_unmatched_label_count: int,
) -> Optional[str]:
    """Refine the alignment status into a specific cause for UI messaging.

    Distinguishes the two flavours of "missing" empty state surfaced in the
    2026-05-19 RCA (``.hermes/report-parity/missing-alignment-2026-05-19``):

    * ``no_standards_in_source`` (Category A): the Schoology "Export Stats"
      CSV had zero ``Standards{N}`` columns, so every
      ``dim_question_data.standard`` is NULL. The fix is for the teacher
      to use "Align Learning Objective" in Schoology.
    * ``labels_not_mapped`` (Category B): the CSV contains labels but the
      exact-match join against ``dim_standard.schoology_standard`` failed —
      typically because the label is something like ``"Social Studies"``
      rather than a real CPALMS code. The fix is to either correct the
      label in Schoology or extend the standards dictionary.

    Returns one of:
      * ``"no_questions"``               — item has no question rows
      * ``"full_alignment"``             — every question aligned
      * ``"partial_teacher_alignment"``  — some aligned, some not
      * ``"no_standards_in_source"``     — Category A
      * ``"labels_not_mapped"``          — Category B
      * ``None``                         — counts inconsistent; caller
        should treat this as "cannot determine" and fall back to the
        generic empty state rather than fabricating a cause.
    """
    if questions_total == 0:
        return "no_questions"
    if questions_with_alignment == questions_total:
        return "full_alignment"
    if questions_with_alignment > 0:
        return "partial_teacher_alignment"
    # questions_with_alignment == 0 from here — split A vs B.
    if nonempty_standards_count == 0:
        return "no_standards_in_source"
    if distinct_unmatched_label_count > 0:
        return "labels_not_mapped"
    # Pathological: counts say "no aligned questions, no empty labels,
    # no unmatched labels" simultaneously. Don't fabricate a cause.
    return None

logger = logging.getLogger(__name__)

# Match HTML tags while *preserving* Schoology's `<https://…>` image-URL
# placeholders. The negative lookahead skips `<` followed by a URL scheme so
# the frontend's formatQuestionHtml can still convert it into an <img>.
_HTML_TAG_RE = re.compile(r"<(?!https?://)[^>]+>")


def _strip_html(s: Optional[str]) -> str:
    if not s:
        return ""
    # Decode entities FIRST, then strip tags, so entity-escaped markup
    # (e.g. "&lt;b&gt;x&lt;/b&gt;") is resurrected to real tags and then
    # removed — never rendered live. Decoding after stripping would leave
    # those tags intact (a latent XSS/format landmine). Legacy's cleaned
    # descriptions are entity-free plain text; `<https://…>` image
    # placeholders carry no entities, so unescape leaves them untouched and
    # the tag regex's URL-scheme lookahead still preserves them.
    return _HTML_TAG_RE.sub("", _html.unescape(s)).strip()


def _format_pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _round_opt(v: Any) -> Optional[float]:
    """Round to 6 dp, preserving ``None`` (an unassessed/BLANK grade).

    Unlike ``to_float`` this does NOT coerce ``None`` → 0.0, so a missing
    grade stays blank end-to-end (MASTER_PLAN §6, Decision 3).
    """
    if v is None:
        return None
    return round(to_float(v), 6)


def _format_pct_opt(v: Any) -> str:
    """Percent string for an optional grade; empty string when ``None``."""
    if v is None:
        return ""
    return _format_pct(to_float(v))


# PBIX-mandated band thresholds (Performance Color* DAX measures): a strand
# or standard is "at target" at >=80%, "approaching" at 70–80%, and "needs
# attention" below 70%.
_BAND_HIGH_THRESHOLD = PERF_BAND_HIGH
_BAND_MID_THRESHOLD = PERF_BAND_MID


def _decode_html(s: str) -> str:
    """Decode HTML entities (e.g. ``&amp;`` → ``&``).

    Some dim_strand labels in the source data are pre-HTML-encoded (the
    PBIX tooling round-tripped them through HTML at some point). We render
    them as plain text in the React UI so we need to decode before
    serialising.
    """
    if not s:
        return ""
    return _html.unescape(s)


def _coerce_str_list(value: Any) -> list[str]:
    """Normalise a SQL string_agg / array_agg result into a clean str list.

    Postgres ``array_agg`` lands as a Python ``list``; legacy ``string_agg``
    lands as a comma-joined str. Both shapes appear across the codebase; this
    helper accepts either, drops empties, and preserves order.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v]
    return [s.strip() for s in str(value).split(",") if s.strip()]
