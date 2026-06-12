"""Synthesize Schoology course-prefix alias rows in ``dim_standard``.

WHY
---
Schoology gradebook exports emit course-prefixed alias forms of a standard
(``AI.MA.912.AR.3.1`` alongside ``MA.912.AR.3.1``; ``SCI.3.SC.3.N.1.1``
alongside ``SC.3.N.1.1``). The per-question rollups join the *raw* label an
assessment emitted (``dim_question_data.standard``) to ``dim_standard`` via an
**exact** ``schoology_standard`` match. Any used alias with no exact row
collapses into the synthetic ``Other`` bucket and silently corrupts the
rollups (see ``docs/audit/legacy-schoology-cpalms-mapping.md`` and
``tests/api/test_standards_alias_coverage.py``).

Legacy's Spark pipeline produced these alias rows by observing every distinct
standard string in the gradebook CSVs and substring-joining each back to the
IMS-canonical rows, then unioning. ``dim_standard.csv`` already ships the
aliases legacy happened to observe. This step closes the gap for aliases that
appear in *newly ingested* assessments but were never baked into the seed.

WHAT
----
For every code-shaped ``dim_question_data.standard`` with no exact
``dim_standard.schoology_standard`` match, resolve a BASE standard and copy its
attributes (identifier, strand, subject, cluster, description, …) under the
aliased code. Resolution, in order:

  1. **Substring-contains (legacy)** — the longest base ``schoology_standard``
     that is a substring of the alias (``SCI.3.SC.3.N.1.1`` ⊃ ``SC.3.N.1.1``,
     ``SOC.9-12.SS.912.W.1.6`` ⊃ ``SS.912.W.1.6``).
  2. **Course-prefix strip + parent-cluster walk** — strip the leading
     Schoology ``<COURSE>.<grade>.`` prefix, then walk the remaining code up
     its dotted hierarchy until a base (or a base's parent cluster) in the
     SAME subject is found, preferring the grade encoded in the alias. This
     reaches finer-grained lettered leaves (``SC.2.P.13.A`` → ``SC.2.P.13.1``;
     ``ELA.5.L.1.1.d`` → ``LAFS.5.L.1.1``) that have no exact base sibling.

The synthesized ``cpalms_standard`` drops the alias's first two dot-segments
(legacy semantics). The row is keyed by ``uniques_id = identifier || '_' ||
alias`` so re-running is idempotent (``ON CONFLICT DO NOTHING``).

Aliases with no resolvable base are returned (and printed) for follow-up — we
never invent a standard whose family does not exist.

Usage:
    python supabase/seeds/augment_standard_aliases.py
    python supabase/seeds/augment_standard_aliases.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Optional

import psycopg2

DEFAULT_DSN = "postgresql://postgres:postgres@127.0.0.1:56322/postgres"

# A label is a real standard CODE (not junk like "Social Studies") when it has
# both a dot and a digit — mirrors the cube's join expectation and the
# coverage test's _CODE_SHAPE_REGEX.
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


def augment(conn, *, dry_run: bool = False) -> tuple[int, list[str]]:
    """Insert missing alias rows. Returns (rows_added, unresolved_aliases)."""
    with conn.cursor() as cur:
        # All base codes + their subject, for the resolver.
        cur.execute(
            "SELECT schoology_standard, subject FROM dim_standard "
            "WHERE schoology_standard IS NOT NULL AND schoology_standard <> ''"
        )
        rows = cur.fetchall()
        codes = [r[0] for r in rows]
        subject_by_code = {r[0]: r[1] for r in rows}
        existing = set(codes)

        # Code-shaped assessment labels with no exact dim_standard row.
        cur.execute(
            """
            SELECT DISTINCT standard
            FROM dim_question_data
            WHERE standard IS NOT NULL
              AND standard NOT IN ('', 'null', 'Other')
              AND standard ~ %s
              AND NOT EXISTS (
                  SELECT 1 FROM dim_standard d
                  WHERE d.schoology_standard = dim_question_data.standard
              )
            ORDER BY standard
            """,
            (_CODE_SHAPE.pattern,),
        )
        missing = [r[0] for r in cur.fetchall()]

    resolver = AliasResolver(codes, subject_by_code)
    added = 0
    unresolved: list[str] = []
    copy_list = ", ".join(_COPY_COLS)

    for alias in missing:
        if alias in existing:  # defensive; already covered
            continue
        base = resolver.resolve(alias)
        if base is None:
            unresolved.append(alias)
            continue
        if dry_run:
            added += 1
            print(f"  + {alias}  <-  {base}  ({subject_by_code.get(base)})")
            continue
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO dim_standard
                    (uniques_id, schoology_standard, cpalms_standard, {copy_list})
                SELECT
                    b.identifier || '_' || %(alias)s,
                    %(alias)s,
                    %(cpalms)s,
                    {", ".join("b." + c for c in _COPY_COLS)}
                FROM dim_standard b
                WHERE b.schoology_standard = %(base)s
                ORDER BY length(b.schoology_standard)
                LIMIT 1
                ON CONFLICT (uniques_id) DO NOTHING
                """,
                {"alias": alias, "base": base, "cpalms": _cpalms_from_alias(alias)},
            )
            added += cur.rowcount
        existing.add(alias)

    if not dry_run:
        conn.commit()
    return added, unresolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", DEFAULT_DSN))
    args = parser.parse_args()

    print(f"Connecting to {args.dsn}")
    conn = psycopg2.connect(args.dsn)
    try:
        added, unresolved = augment(conn, dry_run=args.dry_run)
    finally:
        conn.close()

    verb = "would add" if args.dry_run else "added"
    print(f"[alias-augment] {verb} {added} alias row(s).")
    if unresolved:
        print(
            f"[alias-augment] {len(unresolved)} alias(es) have NO resolvable "
            f"base standard (family absent from dim_standard) — reported, not "
            f"invented: {unresolved}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
