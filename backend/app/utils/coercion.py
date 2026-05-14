"""Type coercion helpers used across services + repositories.

These helpers return numeric/string defaults rather than ``None`` so they can
be chained into arithmetic (``round(to_float(v), 6)``) and string formatters
without per-callsite null guards. Every callsite in the reporting + assessment
services relies on this contract.
"""

from __future__ import annotations

from typing import Any


def to_float(value: Any) -> float:
    """Coerce to ``float``. Returns ``0.0`` for ``None`` or unparseable input."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def to_int(value: Any) -> int:
    """Coerce to ``int``. Returns ``0`` for ``None`` or unparseable input."""
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def safe_str(value: Any) -> str:
    """Coerce to ``str``. Returns ``""`` for ``None``; passes ``str`` through."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)
