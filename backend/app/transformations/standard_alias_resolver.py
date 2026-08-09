"""Schoology course-prefix alias resolution — the single source of truth.

Pure logic (``re`` + ``typing`` only, zero import-time side effects) for
resolving a Schoology gradebook alias code (e.g. ``AI.MA.912.AR.3.1``,
``SCI.3.SC.3.N.1.1``) back to its base ``schoology_standard``
(``MA.912.AR.3.1``, ``SC.3.N.1.1``). See
``supabase/seeds/augment_standard_aliases.py`` for the full WHY (legacy
Spark substring-join provenance) and the DB-driving ``augment()``/CLI.

This module lives IN the backend package so it is present in the backend
Docker image (build context = ``backend/`` only). Both consumers import
these symbols from here — there is exactly one copy:

  * ``app.transformations.runner._augment_standard_aliases`` — imports it as
    a normal package module and drives it over the live async session.
  * ``supabase/seeds/augment_standard_aliases.py`` — re-imports it by file
    path (``importlib``) so the seed CLI and ``load_standards.py`` run the
    identical logic off this one source file (a separate module instance,
    behaviorally identical) without dragging the backend's SQLAlchemy stack.

Do not fork this logic: divergence between two copies would silently
mis-label standards.
"""

from __future__ import annotations

import re
from typing import Optional

# A label is a real standard CODE (not junk like "Social Studies") when it has
# both a dot and a digit — mirrors the cube's join expectation.
_CODE_SHAPE = re.compile(r"\.[^.]*[0-9]|[0-9][^.]*\.")

# Leading Schoology course prefix: "<ALPHA>.<grade>." where grade is K, a
# 1-2 digit number, or a banded range like 9-12, and the remainder starts a
# base stem (an uppercase letter). E.g. "SCI.3.", "ELA.5.", "SOC.9-12.".
_COURSE_PREFIX = re.compile(r"^[A-Z]+\.(?:K|\d{1,2}|\d{1,2}-\d{1,2})\.(?=[A-Z])")
_GRADE_TOKEN = re.compile(r"^[A-Z]+\.(K|\d{1,2}|\d{1,2}-\d{1,2})\.")

# Base attribute columns copied verbatim onto the alias row.
_COPY_COLS = (
    "identifier",
    "standard_new",
    "strand",
    "subject",
    "cluster",
    "description",
    "custom_cleaned_description",
    "direct_link",
    "cognitive_complexity_rating",
    "language",
    "grader",
    "last_change_date_time",
    "rundate",
)


def _drop_leaf(code: str) -> str:
    return code.rsplit(".", 1)[0] if "." in code else code


def _cpalms_from_alias(alias: str) -> str:
    """Legacy: drop the first two dot-segments of the Schoology code."""
    return ".".join(alias.split(".")[2:])


class AliasResolver:
    """Resolves an assessment alias code to a base ``schoology_standard``."""

    def __init__(self, codes: list[str], subject_by_code: dict[str, str]):
        self._codes = [c for c in codes if c]
        self._subject = subject_by_code

    def resolve(self, alias: str) -> Optional[str]:
        # 1) longest base that is a substring of the alias (legacy primary).
        best: Optional[str] = None
        for code in self._codes:
            if code in alias and (best is None or len(code) > len(best)):
                best = code
        if best is not None:
            return best

        # 2) strip the Schoology course prefix, then walk the hierarchy.
        m = _COURSE_PREFIX.match(alias)
        core = alias[m.end():] if m else alias
        gm = _GRADE_TOKEN.match(alias)
        grade = gm.group(1) if gm else None

        cand = core
        while "." in cand:
            matches = [
                c
                for c in self._codes
                if c == cand
                or c.endswith("." + cand)
                or _drop_leaf(c) == cand
                or _drop_leaf(c).endswith("." + cand)
            ]
            if matches:
                if grade:
                    grade_re = re.compile(r"(^|\.)" + re.escape(grade) + r"\.")
                    graded = [c for c in matches if grade_re.search(c)]
                    if graded:
                        matches = graded
                matches.sort(key=len)
                return matches[0]
            cand = _drop_leaf(cand)
        return None
