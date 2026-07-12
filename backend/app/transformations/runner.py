"""Async SQL-file orchestrator for Phase 2 (staging + dimensions).

The orchestrator is dumb on purpose: it reads `.sql` files in a hardcoded
topological order and executes each one. Each file is the unit of replay;
each must be idempotent (TRUNCATE+INSERT for staging, ON CONFLICT DO UPDATE
for dimensions). Per-row dependencies are encoded by ordering — never by
implicit Python.

CLI entry points:

    cd backend && python -m app.transformations.runner
    cd backend && python -m app.transformations.runner --tag dimensions
    # also runs from repo root:
    python -m backend.app.transformations.runner --tag staging

Phase 3 will append fact/cube/hash tags to TRANSFORMATIONS_ORDER.
"""

# ruff: noqa: E402  -- intentional sys.path bootstrap below requires deferred imports

from __future__ import annotations

# ─── sys.path bootstrap ────────────────────────────────────────────────────
# Mirror app.jobs.ingest_schoology so this CLI works from both
#   cd backend && python -m app.transformations.runner
#   python -m backend.app.transformations.runner   (repo root)
import os as _os
import sys as _sys

_BACKEND_DIR = _os.path.dirname(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
)
if _BACKEND_DIR not in _sys.path:
    _sys.path.insert(0, _BACKEND_DIR)
# ──────────────────────────────────────────────────────────────────────────

import argparse
import asyncio
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.db import dispose_engine, session_scope


logger = logging.getLogger("transformations")


# Each tuple: (relpath_under_transformations_dir, tag).
# Tag is filterable via `only_tag=` or `--tag <tag>` from the CLI.
TRANSFORMATIONS_ORDER: list[tuple[str, str]] = [
    # phase 1 — staging (TRUNCATE + INSERT from raw_*; tenant overrides applied)
    ("01_staging/stg_user.sql",                "staging"),
    ("01_staging/stg_question_data.sql",       "staging"),
    ("01_staging/stg_student_submission.sql",  "staging"),
    ("01_staging/stg_submission_summary.sql",  "staging"),

    # phase 2 — independent dims (ON CONFLICT ... DO UPDATE)
    ("02_dimensions_a/dim_school.sql",         "dimensions"),
    ("02_dimensions_a/dim_student.sql",        "dimensions"),
    ("02_dimensions_a/dim_teacher.sql",        "dimensions"),
    ("02_dimensions_a/dim_parent.sql",         "dimensions"),
    ("02_dimensions_a/dim_course.sql",         "dimensions"),

    # phase 3 — dim_item (uses synthetic Subject_ID; first-occurrence dedupe)
    ("03_dimensions_b/dim_item.sql",           "dimensions"),

    # phase 4 — dim_question_data (substring join on standards + Grade remap)
    ("04_dimensions_c/dim_question_data.sql",  "dimensions"),

    # phase 5 — dim_strand (rebuilt from dim_question_data ⨝ dim_standard)
    # NOTE: dim_standard is NOT rebuilt here (D2 Path A — static seed). The
    # placeholder file documents that intentionally.
    ("05_dimensions_d/dim_standard.sql",       "dimensions"),
    ("05_dimensions_d/dim_strand.sql",         "dimensions"),

    # phase 6 — derived dims (DISTINCT projections of stg_student_submission)
    ("06_dimensions_e/dim_unit_lesson.sql",    "dimensions"),
    ("06_dimensions_e/dim_section.sql",        "dimensions"),
    ("06_dimensions_e/dim_session.sql",        "dimensions"),
    ("06_dimensions_e/dim_grade.sql",          "dimensions"),
    ("06_dimensions_e/dim_assessment_type.sql","dimensions"),
    ("06_dimensions_e/dim_subject.sql",        "dimensions"),

    # phase 7 — fact_student_submission (notebook §5 / §3).
    # Depends on stg_student_submission, dim_question_data, dim_standard,
    # dim_strand. INSERT ... ON CONFLICT (user_id_ques_id_stand) DO UPDATE.
    ("07_facts/fact_student_submission.sql",   "facts"),

    # Post-fact reconciliation (F-C1): point dim_item.subject_id at the bucket
    # fact settled on (dissolves orphan cards) and drop 0-fact dim_subject
    # phantoms. Must run AFTER fact, BEFORE hash/cubes.
    ("07_facts/dim_reconcile.sql",             "facts"),

    # phase 8 — pseudonymisation tables (notebook §7 build_pseudomyzed_tables,
    # lines 1295-1320). Each TRUNCATE+INSERT.
    # dim_section_hash depends on dim_section.
    # dim_student_hash depends on fact_student_submission.
    # fact_student_submissions_hash depends on dim_student_hash + fact.
    ("08_hash/dim_section_hash.sql",           "hash"),
    ("08_hash/dim_student_hash.sql",           "hash"),
    ("08_hash/fact_student_submissions_hash.sql", "hash"),

    # phase 9 — cubes (notebook §7). All depend on fact_student_submission;
    # cube_question_summary + cube_question_summary_overall + cube_user_summary
    # additionally depend on dim_*_hash + dim_question_data + dim_item +
    # dim_standard + dim_section. TRUNCATE+INSERT.
    ("09_cubes/cube_grade_summary.sql",                  "cubes"),
    ("09_cubes/cube_school_summary.sql",                 "cubes"),
    ("09_cubes/cube_standard_summary.sql",               "cubes"),
    ("09_cubes/cube_question_summary.sql",               "cubes"),
    ("09_cubes/cube_questionincorrectchoice_summary.sql","cubes"),
    ("09_cubes/cube_question_summary_overall.sql",       "cubes"),
    # Per-item twin of cube_question_summary_overall (adds item_id to the grain)
    # so per-assessment Strand/Standard rollups read a section-scoped grade
    # instead of the subject_id-pooled (cross-section) cqso value.
    ("09_cubes/cube_question_summary_overall_by_item.sql", "cubes"),
    ("09_cubes/cube_overallperformance_summary.sql",     "cubes"),
    ("09_cubes/cube_user_summary.sql",                   "cubes"),
]


def _base_dir() -> Path:
    """Resolve the directory containing the SQL subfolders (this module's dir)."""
    return Path(__file__).resolve().parent


def _strip_sql_comments(sql: str) -> str:
    """Strip `--` line comments. We DO NOT strip `/* ... */` block comments
    because none of our files use them and the splitter below is simpler
    without that case to worry about. If/when we add block comments, swap in
    sqlparse.format(..., strip_comments=True).
    """
    out_lines: list[str] = []
    for line in sql.splitlines():
        # Find the first `--` that is NOT inside a string literal. Our SQL is
        # generated by us; we do not have `--` inside any string literal, so a
        # naive split is safe.
        idx = line.find("--")
        if idx >= 0:
            line = line[:idx]
        out_lines.append(line)
    return "\n".join(out_lines)


def _split_sql_statements(sql: str) -> list[str]:
    """Split a multi-statement SQL string on top-level semicolons.

    asyncpg cannot execute multiple statements per `execute()` call (it errors
    "cannot insert multiple commands into a prepared statement"). We split at
    statement boundaries, respecting:
      * single-quoted string literals (incl. doubled '' escapes)
      * dollar-quoted strings ($$...$$ and $tag$...$tag$)

    Empty / whitespace-only fragments are dropped.
    """
    sql = _strip_sql_comments(sql)
    statements: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(sql)
    in_squote = False
    dollar_tag: str | None = None  # e.g. "$$" or "$abc$" if inside dollar-quote

    while i < n:
        ch = sql[i]

        if dollar_tag is not None:
            buf.append(ch)
            # Look for the closing dollar tag.
            if ch == "$" and sql[i : i + len(dollar_tag)] == dollar_tag:
                # Append the rest of the closing tag and skip past.
                buf.append(sql[i + 1 : i + len(dollar_tag)])
                i += len(dollar_tag)
                dollar_tag = None
                continue
            i += 1
            continue

        if in_squote:
            buf.append(ch)
            if ch == "'":
                # Doubled '' escape stays inside the string.
                if i + 1 < n and sql[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                in_squote = False
            i += 1
            continue

        if ch == "'":
            in_squote = True
            buf.append(ch)
            i += 1
            continue

        if ch == "$":
            # Try to parse a dollar-quoted opening tag: $tag$
            j = i + 1
            while j < n and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            if j < n and sql[j] == "$":
                tag = sql[i : j + 1]  # includes both leading and trailing $
                dollar_tag = tag
                buf.append(tag)
                i = j + 1
                continue
            # Bare $ — treat as ordinary char.
            buf.append(ch)
            i += 1
            continue

        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf.clear()
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


async def run_all(
    session: AsyncSession,
    only_tag: str | None = None,
    isolate_cubes: bool = False,
) -> dict[str, int]:
    """Execute every SQL file in TRANSFORMATIONS_ORDER (or only the tagged subset).

    Returns:
        dict mapping each `model_name` (the .sql stem, e.g. "dim_school") to
        the rowcount of the LAST executed statement in that file. Postgres
        reports `-1` for statements (CREATE/TRUNCATE/etc.) that have no
        meaningful affected-row count; we coerce those to 0.

    Idempotency:
        Every file in TRANSFORMATIONS_ORDER must be idempotent on its own.
        Staging files use `TRUNCATE + INSERT FROM raw_*`. Dim builds use
        `INSERT ... ON CONFLICT (pk) DO UPDATE`. dim_strand uses TRUNCATE +
        INSERT (legacy parity — see notebook line 1102). Phase 3 cubes use
        TRUNCATE + INSERT.

    Multi-statement files:
        SQL files may contain multiple statements separated by `;`. We split
        them and execute each statement individually (asyncpg restriction).
        See `_split_sql_statements` for quoting rules handled.

    Transactionality:
        We do NOT begin a nested transaction here by default. The caller's
        session is the unit of atomicity: if the caller commits at the end,
        the entire pipeline succeeds-or-fails atomically.

        Pass `isolate_cubes=True` to wrap each cube file in a per-file
        SAVEPOINT — a single cube failure (e.g. an OOM on cube_user_summary)
        is then logged + skipped without rolling back the dimensions, fact,
        or earlier cubes. This is intended for production runs where partial
        cube refresh is preferable to a total rollback.
    """
    base = _base_dir()
    results: dict[str, int] = {}
    failed_cubes: list[str] = []  # G4: track isolate_cubes failures to fail loudly

    for relpath, tag in TRANSFORMATIONS_ORDER:
        if only_tag is not None and tag != only_tag:
            continue

        sql_path = base / relpath
        sql = sql_path.read_text(encoding="utf-8")

        statements = _split_sql_statements(sql)
        model_name = Path(relpath).stem

        # Per-file SAVEPOINT only for cubes when isolate_cubes is requested.
        # Other phases (staging/dim/fact/hash) feed each other and must not be
        # partially applied — failing fast is the right behaviour there.
        if isolate_cubes and tag == "cubes":
            try:
                async with session.begin_nested():
                    last_rowcount = await _exec_statements(session, statements)
            except Exception as e:
                logger.exception(
                    "transformations.cube_failed model=%s tag=%s error=%s",
                    model_name, tag, e,
                )
                results[model_name] = 0
                failed_cubes.append(model_name)  # G4: do not exit clean on a stale cube
                continue
        else:
            last_rowcount = await _exec_statements(session, statements)

        results[model_name] = last_rowcount
        logger.info(
            "transformations.executed model=%s tag=%s rows=%s",
            model_name, tag, last_rowcount,
        )

    # Standard-alias augmentation: synthesize dim_standard rows for any
    # Schoology course-prefix aliases the freshly built dim_question_data uses
    # but the seed CSV never covered (see augment_standard_aliases.py). Must run
    # AFTER dim_question_data exists; the cube files above join dim_standard, so
    # re-run the cube tag when new aliases land to refresh their labels.
    if only_tag is None or only_tag == "cubes":
        added = await _augment_standard_aliases(session)
        if added:
            logger.info("transformations.alias_augment added=%d; refreshing cubes", added)
            for relpath, tag in TRANSFORMATIONS_ORDER:
                if tag != "cubes":
                    continue
                sql = (base / relpath).read_text(encoding="utf-8")
                await _exec_statements(session, _split_sql_statements(sql))

    # G4: a skipped cube leaves stale report data — never let the run look green.
    if failed_cubes:
        banner = " !! ".join(failed_cubes)
        logger.error(
            "transformations.STALE_CUBES the following cubes FAILED and are STALE: %s",
            banner,
        )
        raise RuntimeError(f"STALE CUBES (not rebuilt): {banner}")

    return results


async def _augment_standard_aliases(session: AsyncSession) -> int:
    """Insert missing Schoology-alias rows into dim_standard (idempotent).

    Reuses the resolver in supabase/seeds/augment_standard_aliases.py — the
    single source of truth for alias→base resolution — driven over the live
    async session. Returns the number of rows inserted.
    """
    seeds_dir = _os.path.abspath(
        _os.path.join(_BACKEND_DIR, "..", "supabase", "seeds")
    )
    if seeds_dir not in _sys.path:
        _sys.path.insert(0, seeds_dir)
    from augment_standard_aliases import (  # type: ignore
        _CODE_SHAPE,
        _COPY_COLS,
        AliasResolver,
        _cpalms_from_alias,
    )

    base_rows = (
        await session.execute(
            text(
                "SELECT schoology_standard, subject FROM dim_standard "
                "WHERE schoology_standard IS NOT NULL AND schoology_standard <> ''"
            )
        )
    ).all()
    codes = [r[0] for r in base_rows]
    subject_by_code = {r[0]: r[1] for r in base_rows}
    existing = set(codes)

    missing = (
        await session.execute(
            text(
                """
                SELECT DISTINCT standard
                FROM dim_question_data
                WHERE standard IS NOT NULL
                  AND standard NOT IN ('', 'null', 'Other')
                  AND standard ~ :code_shape
                  AND NOT EXISTS (
                      SELECT 1 FROM dim_standard d
                      WHERE d.schoology_standard = dim_question_data.standard
                  )
                ORDER BY standard
                """
            ),
            {"code_shape": _CODE_SHAPE.pattern},
        )
    ).scalars().all()

    resolver = AliasResolver(codes, subject_by_code)
    copy_list = ", ".join(_COPY_COLS)
    select_cols = ", ".join("b." + c for c in _COPY_COLS)
    added = 0
    unresolved: list[str] = []

    for alias in missing:
        if alias in existing:
            continue
        base_code = resolver.resolve(alias)
        if base_code is None:
            unresolved.append(alias)
            continue
        result = await session.execute(
            text(
                f"""
                INSERT INTO dim_standard
                    (uniques_id, schoology_standard, cpalms_standard, {copy_list})
                SELECT
                    b.identifier || '_' || :alias,
                    :alias,
                    :cpalms,
                    {select_cols}
                FROM dim_standard b
                WHERE b.schoology_standard = :base
                ORDER BY length(b.schoology_standard)
                LIMIT 1
                ON CONFLICT (uniques_id) DO NOTHING
                """
            ),
            {"alias": alias, "base": base_code, "cpalms": _cpalms_from_alias(alias)},
        )
        added += result.rowcount or 0
        existing.add(alias)

    if unresolved:
        logger.warning(
            "transformations.alias_augment unresolved=%d (no base family in "
            "dim_standard, reported not invented): %s",
            len(unresolved), unresolved,
        )
    return added


async def _exec_statements(session: AsyncSession, statements: list[str]) -> int:
    """Execute each statement; return rowcount of the last meaningful one."""
    last_rowcount = 0
    for stmt in statements:
        result = await session.execute(text(stmt))
        # Postgres returns -1 for `rowcount` when the statement does not affect
        # rows in the conventional sense (e.g. CREATE TABLE, TRUNCATE).
        if result.rowcount is not None and result.rowcount >= 0:
            last_rowcount = result.rowcount
    return last_rowcount


async def _main(only_tag: str | None) -> int:
    async with session_scope() as session:
        results = await run_all(session, only_tag=only_tag)
    total = sum(results.values())
    logger.info("transformations.complete models=%d total_rows=%d", len(results), total)
    return 0


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="transformations.runner")
    parser.add_argument(
        "--tag",
        default=None,
        choices=("staging", "dimensions", "facts", "hash", "cubes"),
        help="Run only the SQL files tagged with this value (default: all).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level.",
    )
    args = parser.parse_args(argv)
    _setup_logging(args.log_level)

    try:
        return await _main(args.tag)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    _sys.exit(asyncio.run(main()))
