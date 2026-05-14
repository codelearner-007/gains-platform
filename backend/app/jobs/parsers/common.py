"""Shared utilities for CSV parsing.

* BOM-aware UTF-8 reading (notebook uses ISO-8859-1 for pre-landing — but the scraper
  writes UTF-8 with BOM, so we use utf-8-sig).
* Numeric/text/datetime/interval coercion with NULL-tolerance.
* 7500-character truncation for `Question` and `Answer Submission` (notebook lines 482-488).
* Duplicate-header disambiguation (Question-Data has "Answer Breakdown" twice and
  may have "Standards" up to 4 times).
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime, timedelta, timezone


logger = logging.getLogger("ingest_schoology.parsers")


# Notebook lines 482-488 — truncate Question + Answer_Submission to 7500 chars
QUESTION_TRUNCATE_LEN = 7500


def disambiguate_headers(raw_headers: list[str]) -> list[str]:
    """Append `__N` (N starts at 1) to the 2nd, 3rd, ... occurrences of duplicate header names.

    Examples:
        ['A', 'B', 'A']           -> ['A', 'B', 'A__1']
        ['Standards','Standards'] -> ['Standards', 'Standards__1']

    The first occurrence keeps its plain name. Mirrors the pilot's _build_pilot.py logic.
    """
    seen: dict[str, int] = {}
    cleaned: list[str] = []
    for h in raw_headers:
        if h in seen:
            seen[h] += 1
            cleaned.append(f"{h}__{seen[h]}")
        else:
            seen[h] = 0
            cleaned.append(h)
    return cleaned


def read_csv_bytes(
    data: bytes, *, source_name: str | None = None
) -> tuple[list[str], list[dict[str, str]]]:
    """Read CSV bytes (utf-8 with optional BOM) and return (clean_headers, rows-as-dicts).

    Rows shorter than the header row are padded with empty strings;
    extra cells are dropped (with a WARNING). Empty trailing lines are skipped.

    Args:
        data: raw CSV bytes.
        source_name: optional file name / path to include in truncation warnings.
    """
    text = data.decode("utf-8-sig")
    return read_csv_text(text, source_name=source_name)


def read_csv_text(
    text: str, *, source_name: str | None = None
) -> tuple[list[str], list[dict[str, str]]]:
    """Read CSV text (no BOM expected — caller already decoded) and return (headers, rows-as-dicts).

    Args:
        text: decoded CSV text.
        source_name: optional file name / path to include in truncation warnings.
    """
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        raw_headers = next(reader)
    except StopIteration:
        return [], []
    headers = disambiguate_headers([h.strip("﻿") for h in raw_headers])
    rows: list[dict[str, str]] = []
    n = len(headers)
    src = source_name or "<csv>"
    for row_idx, r in enumerate(reader, start=2):  # data rows start at line 2 (header is 1)
        if not r or all(c == "" for c in r):
            continue
        # pad / truncate
        if len(r) < n:
            r = list(r) + [""] * (n - len(r))
        elif len(r) > n:
            extra = len(r) - n
            logger.warning(
                "%s: row %d has %d extra cell(s) beyond %d headers; truncating",
                src, row_idx, extra, n,
            )
            r = r[:n]
        rows.append({headers[i]: r[i] for i in range(n)})
    return headers, rows


def coerce_int(s: str | None) -> int | None:
    """Empty / blank / 'n/a' / non-numeric → None. Otherwise int(s).

    Falls back to int(float(s)) for decimals like "5.0" — emits a WARNING
    so callers can audit unexpected formats. Logs a WARNING and returns None
    when neither parse succeeds on a non-empty value.
    """
    if s is None:
        return None
    original = s
    s = s.strip()
    if s == "" or s.lower() in ("n/a", "na", "null"):
        return None
    try:
        return int(s)
    except ValueError:
        # Try the float fallback for decimal-encoded ints like "5.0"
        try:
            result = int(float(s))
            logger.warning(
                "coerce_int: value %r is not a plain int; using int(float(...)) -> %d",
                original, result,
            )
            return result
        except ValueError:
            logger.warning("coerce_int: could not parse %r as int; returning None", original)
            return None


def coerce_decimal(s: str | None) -> float | None:
    """Empty / blank / 'n/a' / non-numeric → None. Otherwise float(s).

    The DB column is NUMERIC(10,4); sending a Python float is fine, asyncpg
    converts it appropriately.
    """
    if s is None:
        return None
    s = s.strip()
    if s == "" or s.lower() in ("n/a", "na", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def coerce_str(s: str | None) -> str | None:
    """Empty string → None; otherwise return the string as-is (no trim)."""
    if s is None:
        return None
    if s == "":
        return None
    return s


def truncate_question(s: str | None) -> str | None:
    """Apply the 7500-char truncation per notebook line 482-488. None passes through."""
    if s is None:
        return None
    if len(s) > QUESTION_TRUNCATE_LEN:
        return s[:QUESTION_TRUNCATE_LEN]
    return s


# ─────────────────────────────────────────────────────────────────────────
# Date / interval coercion
# ─────────────────────────────────────────────────────────────────────────

# Schoology timestamps are like "2026-04-30 12:50:41" — naive, assumed UTC.
_TS_PATTERNS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
]


def coerce_timestamp(s: str | None) -> datetime | None:
    """Parse Schoology timestamps. Empty → None. Naive timestamps are assumed UTC.

    Returns a timezone-aware datetime. Raises ValueError on truly malformed input
    (we WANT to fail loudly here rather than silently dropping data).
    """
    if s is None:
        return None
    s = s.strip()
    if s == "":
        return None
    for fmt in _TS_PATTERNS:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # last-ditch: try fromisoformat (handles offsets like +00:00)
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError as e:
        raise ValueError(f"could not parse timestamp: {s!r}") from e


_INTERVAL_RE = re.compile(r"^(\d+):(\d{1,2}):(\d{1,2})$")


def coerce_interval(s: str | None) -> timedelta | None:
    """Parse `HH:MM:SS` (or `HHH:MM:SS`) → timedelta. Empty → None.

    Schoology's Total_Time format. Postgres INTERVAL accepts a timedelta directly via asyncpg.
    """
    if s is None:
        return None
    s = s.strip()
    if s == "":
        return None
    m = _INTERVAL_RE.match(s)
    if not m:
        # Some rows might be empty/junk; be permissive and return None
        return None
    hours, minutes, seconds = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)
