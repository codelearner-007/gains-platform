"""Async SQL-file orchestrator for the warehouse transform pipeline.

The orchestrator is dumb on purpose: it reads `.sql` files in a hardcoded
topological order and executes each one. Each file is the unit of replay;
each must be idempotent (TRUNCATE+INSERT for staging, ON CONFLICT DO UPDATE
for dimensions). Per-row dependencies are encoded by ordering — never by
implicit Python.

SCOPED MODE (incremental rebuild of only the freshly-ingested assessments)
──────────────────────────────────────────────────────────────────────────
`run_all(..., scope_run_ids=[...])` rebuilds ONLY the assessments a batch
(re)ingested instead of a full destructive rebuild. It is driven by three
session-local TEMP tables (`_scope_run_ids` / `_scope_assessments` /
`_scope_items`, all ON COMMIT DROP) that the SQL files read. When those tables
are EMPTY (the full-rebuild path) every scope predicate is an uncorrelated
`NOT EXISTS` InitPlan that is TRUE once, so a full rebuild is byte-identical to
before this feature existed.

Prod correction constraints (read before operating on prod):
  * Correcting an EXISTING assessment on prod REQUIRES a FULL-assessment
    re-scrape. A partial/truncated re-scrape is rejected by the roster gate
    (its group is pruned) — the run is marked failed and its raw retained.
  * Archived / renamed-Schoology-section assessments cannot be corrected via
    the scoped path (the old section's raw can never reappear). Route those to
    the Method-A/B resync in docs/audit/fixes/03_prod_data_sync_runbook.md.

CLI entry points:

    cd backend && python -m app.transformations.runner
    cd backend && python -m app.transformations.runner --tag dimensions
    cd backend && python -m app.transformations.runner --scope-run-id <uuid> [--scope-run-id <uuid> ...]
    cd backend && python -m app.transformations.runner --scope-landed
    # also runs from repo root:
    python -m backend.app.transformations.runner --tag staging

A manual psql replay of any single touched .sql file must first create the
three `_scope_*` temp tables EMPTY (see each file's header note), else the
scope predicates error on the missing relation.
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
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.db import dispose_engine, session_scope
from app.transformations.standard_alias_resolver import (
    _CODE_SHAPE,
    _COPY_COLS,
    AliasResolver,
    _cpalms_from_alias,
)


logger = logging.getLogger("transformations")


# Global transform mutex key — the SINGLE source of truth; the ingestion worker
# imports this exact constant (``from app.transformations.runner import
# _TRANSFORM_LOCK_KEY``). The worker acquires it on its transform session BEFORE
# calling run_all, so run_all re-acquiring it is a same-session re-entrant no-op
# there. On the CLI paths (this module, ingest_schoology, gains_data) run_all is
# the FIRST acquirer, which closes the "two concurrent CLI rebuilds" hole.
# Advisory xact locks release at commit.
_TRANSFORM_LOCK_KEY = 0x1A9E571A5F0

# Staging files that carry no data feeding the fact/cube chain, so a scoped run
# skips them entirely (Phase-0 verified 0 consumers): stg_user (dim_teacher/
# dim_parent are empty; dim_student's real rows come from the student-submission
# arm which IS rebuilt) and stg_submission_summary (feeds nothing downstream).
_SCOPED_SKIP: frozenset[str] = frozenset({"stg_user", "stg_submission_summary"})


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

    # Cross-band mis-file guard (F-C2 durable prevention): assert every item_id
    # maps to exactly one (grade, subject_id) label-set. FAILS the build naming
    # offenders so a new mis-file is caught before cubes build on phantom rows.
    # Runs AFTER exclusions + reconcile settle labels. Read-only; no data moves.
    ("07_facts/validate_no_cross_band.sql",    "facts"),

    # Scoped orphan sweep: DELETE dim_item/dim_unit_lesson/dim_question_data
    # rows in _scope_items with no fact left (item_id churn on re-ingest), plus
    # dead dim_section rows. Guarded on EXISTS(_scope_items) → NO-OP in a full
    # rebuild (every dim is truncated/rebuilt from scratch anyway).
    ("07_facts/scope_prune_orphans.sql",       "facts"),

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
    # Per-item twin of cube_question_summary_overall. NO LONGER SERVED — merge-
    # section-reports reversed the R3 per-item read, so serving now uses base
    # cqso (the twin's old readers get_strand/standard_rollup_for_item were
    # rewritten). Retained as a LOCAL verification artifact only: the twin-
    # invariant test (tests/reports::test_twin_invariant_holds) re-aggregates it
    # over item_id to prove base cqso's section-merged totals match a section-
    # scoped re-agg. DROPPED on prod (serving-only, no tests run there) — same
    # local(build/test)/prod(serving-only) asymmetry as the hash tables.
    ("09_cubes/cube_question_summary_overall_by_item.sql", "cubes"),
    ("09_cubes/cube_user_summary.sql",                   "cubes"),
]


def _base_dir() -> Path:
    """Resolve the directory containing the SQL subfolders (this module's dir)."""
    return Path(__file__).resolve().parent


# ─── Scope carrier: three session-local TEMP tables ────────────────────────
# Created (empty) at the top of EVERY run_all so the SQL files' scope predicates
# always resolve. In full mode they stay empty ⇒ predicates are no-ops. See the
# module docstring for the state machine.
_SCOPE_TEMP_DDL: tuple[str, ...] = (
    """
    CREATE TEMP TABLE IF NOT EXISTS _scope_run_ids (
        run_id uuid PRIMARY KEY
    ) ON COMMIT DROP
    """,
    """
    CREATE TEMP TABLE IF NOT EXISTS _scope_assessments (
        subject_id      text PRIMARY KEY,
        school_id       uuid NOT NULL,
        session         text,
        subject         text,
        assessment_type text,
        grade           text,
        item_name       text,
        -- Connected-component (rename-linked) group this subject belongs to.
        -- Runner-INTERNAL only (the roster gate keys coverage to it); the SQL
        -- transform files MUST NOT reference group_id (DO-NOT #19). Populated by
        -- _prepare_scope after _connected_components; the stable id is the
        -- lexicographically-smallest subject_id in the component.
        group_id        text
    ) ON COMMIT DROP
    """,
    """
    CREATE TEMP TABLE IF NOT EXISTS _scope_items (
        school_id uuid NOT NULL,
        item_id   text NOT NULL,
        PRIMARY KEY (school_id, item_id)
    ) ON COMMIT DROP
    """,
)


async def _create_scope_temp_tables(session: AsyncSession) -> None:
    for ddl in _SCOPE_TEMP_DDL:
        await session.execute(text(ddl))


# ─── §HISTORIC: unconditional protection of un-reproducible years ──────────
#
# THE RULE, IN ONE LINE: a (school, session, subject_id) slice that is NOT part
# of the run's declared scope must come out of a transform run byte-identical,
# or the whole run rolls back.
#
# WHY IT IS A DATA CHECK AND NOT A FLAG
# This replaced an `ENVIRONMENT == "production"` check plus an
# INGESTION_ALLOW_PROD_TRANSFORMS override. Both were the wrong shape: they
# protected a *label*, not the data. If ENVIRONMENT were unset, misspelled, or
# copied from a dev template onto a serving box, the guard silently did nothing —
# and the failure mode it was guarding is unrecoverable. A flag that must be right
# for your data to survive is not a safeguard; it is a second thing to get wrong.
#
# The invariant below needs no configuration, is identical in every environment,
# and cannot be turned off without editing this file (which is reviewable, unlike
# an env var). It takes NO settings/ENVIRONMENT lookup by design (the
# test_no_env_var_can_disable_the_invariant tripwire depends on that).
#
# WHAT "IN SCOPE" MEANS
#   * Full rebuild: in_scope = every subject_id present in the FRESHLY-BUILT
#     fact (read right before the after-fingerprint). A subject that the rebuild
#     legitimately reproduces is exempt; a subject a staging/fact bug silently
#     DROPPED is NOT in the fresh fact ⇒ not exempt ⇒ its vanished rows RAISE.
#   * Scoped rebuild: in_scope = the roster-gate SURVIVORS (the subjects this
#     batch is allowed to rewrite). A pruned / rename-swept-then-pruned / purely
#     historic subject is NOT in scope ⇒ must be byte-identical or the run rolls
#     back. On prod (empty raw) this freezes every historic subject.
#
# SCOPE: fact_student_submission only. Cubes are pure derivations of fact, so a
# preserved fact means a reproducible cube; the cube-trash assertion
# (_assert_no_cube_trash) is the separate backstop for stale scoped cube rows.
# NOT COVERED: SQL typed straight into psql, which never enters this process. The
# DB-level backstop for that is the trigger pair in
# 20260723100000_historic_lock.sql, deliberately inert until a lock row exists.

_HISTORIC_FINGERPRINT_SQL = text(
    """
    SELECT school_id::text                       AS school_id,
           coalesce(session, '(null)')           AS session,
           coalesce(subject_id, '(null)')        AS subject_id,
           count(*)                              AS n,
           coalesce(sum(hashtext(user_id_ques_id_stand)::bigint), 0) AS fp
    FROM fact_student_submission
    GROUP BY 1, 2, 3
    """
)

# Resolve raw the way stg_student_submission.sql does — via the CSV's own
# "User School ID", never the stamped raw.school_id. Kept ONLY for the "N frozen
# slices" informational log; the guard decision itself is driven by in_scope.
_RAW_COVERAGE_SQL = text(
    """
    SELECT DISTINCT s.school_id::text AS school_id,
           coalesce(r.session, '(null)') AS session
    FROM raw_student_submission r
    JOIN schools s
      ON s.schoology_school_id = NULLIF(TRIM(r.user_school_id), '')
    """
)


async def _fact_session_fingerprints(
    session: AsyncSession,
) -> dict[tuple[str, str, str], tuple[int, int]]:
    """(school_id, session, subject_id) -> (row_count, order-independent fingerprint).

    `sum(hashtext(pk))` is used rather than an ordered `md5(string_agg(...))`
    because it is order-independent and cheap enough to run on every build
    (twice per run).
    """
    rows = (await session.execute(_HISTORIC_FINGERPRINT_SQL)).all()
    return {(r.school_id, r.session, r.subject_id): (int(r.n), int(r.fp)) for r in rows}


async def _raw_session_coverage(session: AsyncSession) -> set[tuple[str, str]]:
    """(school_id, session) pairs the raw layer can rebuild (log only)."""
    rows = (await session.execute(_RAW_COVERAGE_SQL)).all()
    return {(r.school_id, r.session) for r in rows}


def _slice_totals(
    fp: dict[tuple[str, str, str], tuple[int, int]],
) -> dict[tuple[str, str], tuple[int, int]]:
    """Aggregate a per-(school, session, subject) fingerprint map to
    (school, session) → (Σcount, Σfingerprint). Both are additive across the
    subjects in a slice, and the fingerprint pk (user_id_ques_id_stand) excludes
    subject/grade — so a pure relabel that MOVES rows between subject_ids inside
    one (school, session) leaves this slice-level pair unchanged, while a genuine
    row DROP shrinks it."""
    out: dict[tuple[str, str], tuple[int, int]] = {}
    for (school, sess, _subject), (n, f) in fp.items():
        cn, cf = out.get((school, sess), (0, 0))
        out[(school, sess)] = (cn + n, cf + f)
    return out


def _assert_historic_slices_intact(
    before: dict[tuple[str, str, str], tuple[int, int]],
    after: dict[tuple[str, str, str], tuple[int, int]],
    in_scope: frozenset[str],
    *,
    full_mode_raw_coverage: set[tuple[str, str]] | None = None,
) -> None:
    """Raise if any out-of-scope (school, session, subject) slice was altered.

    A slice is in scope iff its subject_id ∈ ``in_scope``. In-scope slices may
    change freely (logged). Out-of-scope slices must be (count, fingerprint)
    byte-identical before→after, else RAISE. Raising propagates out of
    ``run_all``; every caller runs it inside a transaction it commits afterwards,
    so the rollback takes the writes with it.

    ``full_mode_raw_coverage`` opts into the (f) #15 FULL-MODE-ONLY downgrade: an
    out-of-scope slice that changed is downgraded from a violation to a logged
    warning IFF (i) its (school, session) is in this raw-covered set AND (ii) the
    slice-level (Σcount, Σfingerprint) over (school, session) is identical
    before→after — i.e. a legitimate relabel/removal moved rows between
    subject_ids without losing any. A genuine slice SHRINK still RAISES. Scoped
    mode passes ``None`` (strict — prod stays fail-closed). This takes no
    configuration lookup by design (the env tripwire depends on that).
    """
    violations: list[str] = []
    drifted: list[str] = []
    relabeled: list[str] = []

    slice_before = _slice_totals(before) if full_mode_raw_coverage is not None else {}
    slice_after = _slice_totals(after) if full_mode_raw_coverage is not None else {}

    for key, (n_before, fp_before) in sorted(before.items()):
        school, sess, subject = key
        n_after, fp_after = after.get(key, (0, 0))
        unchanged = (n_after == n_before) and (fp_after == fp_before)
        if unchanged:
            continue
        detail = (
            f"school={school} session={sess} subject={subject}: "
            f"{n_before} rows -> {n_after} (fingerprint "
            f"{'unchanged' if fp_after == fp_before else 'CHANGED'})"
        )
        if subject in in_scope:
            # In the run's declared scope: permitted, but never silent — an
            # unexpected move here is the drift that would otherwise reach prod
            # on the next sync.
            drifted.append(detail)
            continue
        # Out-of-scope change. Full-mode relabel downgrade: rows moved within a
        # raw-covered slice whose slice-level totals are preserved → not a loss.
        if (
            full_mode_raw_coverage is not None
            and (school, sess) in full_mode_raw_coverage
            and slice_before.get((school, sess), (0, 0))
            == slice_after.get((school, sess), (0, 0))
        ):
            relabeled.append(detail)
            continue
        violations.append(detail)

    for d in drifted:
        logger.warning("in-scope slice changed (expected for this run) — %s", d)
    for d in relabeled:
        logger.warning(
            "full-rebuild relabel within a raw-covered slice (rows moved between "
            "subjects; slice count+fingerprint preserved) — %s", d
        )

    if violations:
        raise RuntimeError(
            "TRANSFORM ROLLED BACK — it altered "
            f"{len(violations)} (school, session, subject) slice(s) that were NOT "
            "in this run's declared scope:\n  "
            + "\n  ".join(violations)
            + "\n\nThis is the unconditional §HISTORIC invariant in "
            "app/transformations/runner.py: a subject outside the run's scope "
            "(a full rebuild's fresh-fact set, or a scoped run's roster-gate "
            "survivors) must never be modified. There is no flag to bypass it. If "
            "this fired on the production database, that is the guard doing its "
            "job — prod carries a serving fact/cube layer over an empty raw "
            "layer, and new data reaches it via the gated scoped transform or the "
            "sync in docs/audit/fixes/03_prod_data_sync_runbook.md, never an "
            "unscoped in-place rebuild."
        )


# ─── Cube anti-trash: cubes are unguarded by §HISTORIC ─────────────────────
# A scoped cube rebuild that leaves stale rows (item_id churn, dropped subject)
# is caught by NO other guard. This runs at the end of EVERY run_all (both
# modes) and RAISES if any cube carries a leaf row with no backing fact/dim.
# Baseline is 0 on a consistent warehouse (verified in Phase 5). Each check is
# skipped when its cube table is absent (prod drops the twin + some cubes).
_CUBE_TRASH_CHECKS: tuple[tuple[str, str, str], ...] = (
    # (a) leaf item_id ∉ dim_item — cqs / cus / css
    (
        "cqs_item_not_in_dim_item", "cube_question_summary",
        "SELECT count(*) FROM cube_question_summary c WHERE c.item_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM dim_item di "
        "WHERE di.school_id = c.school_id AND di.item_id = c.item_id)",
    ),
    (
        "cus_item_not_in_dim_item", "cube_user_summary",
        "SELECT count(*) FROM cube_user_summary c WHERE c.item_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM dim_item di "
        "WHERE di.school_id = c.school_id AND di.item_id = c.item_id)",
    ),
    (
        "css_item_not_in_dim_item", "cube_school_summary",
        "SELECT count(*) FROM cube_school_summary c WHERE c.item_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM dim_item di "
        "WHERE di.school_id = c.school_id AND di.item_id = c.item_id)",
    ),
    # (b) subject_id with 0 fact — cqs / cqso / twin
    (
        "cqs_subject_zero_fact", "cube_question_summary",
        "SELECT count(*) FROM cube_question_summary c WHERE c.subject_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM fact_student_submission f "
        "WHERE f.subject_id = c.subject_id)",
    ),
    (
        "cqso_subject_zero_fact", "cube_question_summary_overall",
        "SELECT count(*) FROM cube_question_summary_overall c WHERE c.subject_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM fact_student_submission f "
        "WHERE f.subject_id = c.subject_id)",
    ),
    (
        "twin_subject_zero_fact", "cube_question_summary_overall_by_item",
        "SELECT count(*) FROM cube_question_summary_overall_by_item c "
        "WHERE c.subject_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM fact_student_submission f "
        "WHERE f.subject_id = c.subject_id)",
    ),
    # (c) cus (school, session, item_id) not in fact
    (
        "cus_triple_not_in_fact", "cube_user_summary",
        "SELECT count(*) FROM cube_user_summary c WHERE c.item_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM fact_student_submission f "
        "WHERE f.school_id = c.school_id AND f.item_id = c.item_id "
        "AND f.session IS NOT DISTINCT FROM c.session)",
    ),
    # (d) cube_standard leaf item_id / qic leaf question_id not in fact
    (
        "cstd_item_not_in_fact", "cube_standard_summary",
        "SELECT count(*) FROM cube_standard_summary c WHERE c.item_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM fact_student_submission f "
        "WHERE f.school_id = c.school_id AND f.item_id = c.item_id)",
    ),
    (
        "qic_question_not_in_fact", "cube_questionincorrectchoice_summary",
        "SELECT count(*) FROM cube_questionincorrectchoice_summary c "
        "WHERE c.question_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM fact_student_submission f "
        "WHERE f.school_id = c.school_id AND f.question_id = c.question_id)",
    ),
)


async def _assert_no_cube_trash(session: AsyncSession, *, scoped: bool = False) -> None:
    """RAISE if any cube carries a leaf row with no backing fact/dim.

    Baseline 0 on a consistent warehouse. Absent cube tables are skipped so the
    check is safe on prod (twin + some cubes dropped there).

    (e)2 In scoped mode each anti-join is restricted to the touched school(s)
    (``c.school_id IN (SELECT DISTINCT school_id FROM _scope_assessments)``) — a
    scoped build can only have dirtied those schools' cubes, and the bound keeps
    the whole-fact scan proportional to the batch. Full mode stays global.
    """
    school_scope = (
        " AND c.school_id IN (SELECT DISTINCT school_id FROM _scope_assessments)"
        if scoped
        else ""
    )
    problems: list[str] = []
    for label, table, sql in _CUBE_TRASH_CHECKS:
        present = (
            await session.execute(text("SELECT to_regclass(:t)"), {"t": table})
        ).scalar()
        if present is None:
            continue
        count = (await session.execute(text(sql + school_scope))).scalar() or 0
        if count:
            problems.append(f"{label}={count}")
    if problems:
        raise RuntimeError(
            "CUBE TRASH detected — a cube carries leaf row(s) with no backing "
            "fact/dim after this build: "
            + ", ".join(problems)
            + ". A scoped cube rebuild left orphaned rows; the run is rolled back "
            "so the previous consistent cubes survive."
        )


# ─── §LOCK layer 2: SQL guard (unscoped-TRUNCATE refusal) ──────────────────
# Session-bearing tables whose rows belong to a specific (school, session)
# slice. A TOP-LEVEL (unscoped) `TRUNCATE` of any of these erases EVERY year at
# once — the "someone re-runs the old full rebuild" footgun. While ANY lock
# exists we refuse to execute a file that would do that.
#
# The scoped DO-block idiom emits `TRUNCATE ...` only inside a dollar-quoted
# DO body's full-mode ELSE branch; the scan is statement-aware and SKIPS DO
# statements, so those never trip the guard. The two staging files keep a bare
# top-level `TRUNCATE` (per-run scratch) — that is the surviving tripwire: a
# legacy full rebuild is still refused via them, while a scoped run permits
# exactly those two.
_SESSION_BEARING_TABLES: tuple[str, ...] = (
    "stg_student_submission",
    "stg_question_data",
    "fact_student_submission",
    "dim_subject",
    "dim_question_data",
)

# Per-run scratch staging tables whose top-level TRUNCATE is PERMITTED in scoped
# mode (they are rebuilt every run regardless). fact/dim_subject/
# dim_question_data/cube_* stay refused even when scoped.
_STAGING_SCRATCH_TABLES: frozenset[str] = frozenset(
    {"stg_student_submission", "stg_question_data"}
)

# `TRUNCATE [TABLE] [ONLY] [public.]<name>` — the bare/unscoped form the legacy
# full rebuild emits. We only flag TRUNCATE (a scoped `DELETE ... WHERE` is the
# §SCOPE path and is allowed); a TRUNCATE cannot be row-scoped.
_TRUNCATE_RE = re.compile(
    r"\btruncate\b(?:\s+table\b)?(?:\s+only\b)?\s+(?:public\.)?"
    r"(?P<name>[a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)

# A statement whose first keyword is DO — its body is a dollar-quoted PL/pgSQL
# block; any TRUNCATE inside is the scoped idiom's full-mode ELSE branch.
_DO_BLOCK_RE = re.compile(r"^\s*DO\b", re.IGNORECASE)


def _truncated_session_tables(sql: str) -> list[str]:
    """Session-bearing table names a TOP-LEVEL TRUNCATE in ``sql`` would erase.

    Statement-aware: the file is split on top-level semicolons and any `DO ...`
    statement is skipped (its dollar-quoted TRUNCATEs are the scoped idiom's
    full-mode ELSE branch, not an unscoped erase). Empty list => file is safe.
    """
    hits: list[str] = []
    for stmt in _split_sql_statements(sql):
        if _DO_BLOCK_RE.match(stmt):
            continue
        for m in _TRUNCATE_RE.finditer(stmt):
            name = m.group("name").lower()
            if name in _SESSION_BEARING_TABLES or name.startswith("cube_"):
                hits.append(name)
    return hits


async def _assert_no_locked_truncate(
    session: AsyncSession, base: Path, only_tag: str | None, scoped: bool
) -> None:
    """Refuse an unscoped-TRUNCATE build while any historic session is locked.

    Consults ``locked_sessions`` via ``any_locked()``. When empty (the common
    case) this returns immediately — the normal path is untouched. When at least
    one lock exists, scan the files that WOULD run; if any contains a top-level
    TRUNCATE of a session-bearing table, raise a clear error naming the locked
    session(s) and the offending file(s).

    In scoped mode the two per-run scratch staging tables are permitted (they
    are rebuilt every run); fact/dim_subject/dim_question_data/cube_* stay
    refused. Net: lock+scoped → allowed; lock+legacy-full → still refused
    (staging files' top-level TRUNCATE is the tripwire).
    """
    from app.repositories.locked_sessions_repository import LockedSessionsRepository

    repo = LockedSessionsRepository(session)
    if not await repo.any_locked():
        return  # inert: no locks → normal path, no scan

    offenders: list[str] = []
    for relpath, tag in TRANSFORMATIONS_ORDER:
        if only_tag is not None and tag != only_tag:
            continue
        sql = (base / relpath).read_text(encoding="utf-8")
        tables = _truncated_session_tables(sql)
        if scoped:
            tables = [t for t in tables if t not in _STAGING_SCRATCH_TABLES]
        if tables:
            offenders.append(f"{relpath} (TRUNCATE {', '.join(sorted(set(tables)))})")

    if not offenders:
        return  # locks exist but this build has no refused TRUNCATE → allowed

    locks = await repo.list_all()
    locked_labels = ", ".join(
        f"{row['school_id']}:{row['session']}" for row in locks
    ) or "(unknown)"
    raise RuntimeError(
        "transform run REFUSED (historic-lock §LOCK): "
        f"{len(locks)} locked session(s) exist [{locked_labels}] and this build "
        f"would unscoped-TRUNCATE session-bearing table(s). Offending file(s): "
        + "; ".join(offenders)
    )


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
      * dollar-quoted strings ($$...$$ and $tag$...$tag$) — a whole `DO $tag$
        ... $tag$` block is therefore returned as ONE statement.

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


# ─── Scoped-run result plumbing ────────────────────────────────────────────
@dataclass(frozen=True)
class ScopeReport:
    """Scoped-run metadata the worker consumes to map run → succeeded/failed.

    A run succeeded iff none of the subjects it produced is in ``failed_subjects``
    (i.e. run_subjects[run] ⊆ survivors). Otherwise it contributed a pruned
    group → mark failed, retain its raw for retry.

    ``noop_reason`` is the empty-scope sentinel: on a scoped run that built
    NOTHING it names WHY so the worker marks the folded runs failed and RETAINS
    their raw (purge skips — the change is recoverable via a full rebuild) rather
    than promoting them succeeded+applied and purging (which would silently drop
    the correction). Values:

      * ``None``        — a real transform (subjects survived + were applied).
      * ``"qd_only"``   — landed ZERO student-submission rows (question-data-only
        / empty ingest); nothing is buildable from question-data alone.
      * ``"all_pruned"``— subjects were discovered but the roster gate pruned
        EVERY group (partial / truncated re-scrape).
      * ``"no_subjects"``— real student raw landed but ZERO in-scope subjects were
        discovered (an anomaly: wrong ``schools.student_role_id`` or a tenant
        override dropping every row).
    """

    run_subjects: dict[str, frozenset[str]]
    groups: tuple[frozenset[str], ...]
    survivors: frozenset[str]
    failed_subjects: frozenset[str]
    noop_reason: str | None = None


@dataclass(frozen=True)
class _ScopePrep:
    """Internal: everything scope discovery produced before pass B / roster gate."""

    groups: list[frozenset[str]]
    run_subjects: dict[str, frozenset[str]]
    landed_student: int
    subjects: frozenset[str]
    # #18: whole groups pruned up-front because they touch a locked
    # (school, session). Fed to the roster gate so they get the same clean prune
    # (staging + _scope_items + failed marking) as roster-incomplete groups.
    locked_pruned: frozenset[str] = frozenset()


class TransformResult(dict):
    """`dict[model_name -> last-statement rowcount]`, with an optional `.scope`
    (``ScopeReport``) attached on scoped runs. Behaves as a plain dict for every
    existing caller (``sum(x.values())`` / ``len(x)`` / ``x[k]``)."""

    scope: ScopeReport | None = None


def _connected_components(
    subjects: frozenset[str], item_owner_rows: Sequence[tuple[str, str, str]]
) -> list[frozenset[str]]:
    """Union-find over subjects linked by a shared (school_id, item_id).

    ``item_owner_rows`` = (school_id, item_id, subject_id) from both pass-A
    staging (fresh owners) and pre-delete fact (swept owners). Subjects that own
    the SAME batch item land in one component (the rename linkage). Every subject
    in ``subjects`` appears — isolated ones are their own singleton group.
    """
    key_subjects: dict[tuple[str, str], set[str]] = defaultdict(set)
    for school_id, item_id, subject_id in item_owner_rows:
        key_subjects[(school_id, item_id)].add(subject_id)

    parent: dict[str, str] = {s: s for s in subjects}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for subs in key_subjects.values():
        it = iter(subs)
        try:
            first = next(it)
        except StopIteration:  # pragma: no cover - defensive
            continue
        for other in it:
            union(first, other)

    comps: dict[str, set[str]] = defaultdict(set)
    for s in list(parent):
        comps[find(s)].add(s)
    return [frozenset(c) for c in comps.values()]


# Scope-derivation SQL (all restricted to student rows the way fact does).
#
# The synthetic subject_id built over staging's OWN post-override columns — the
# same expression the scoped fact DELETE/INSERT keys on. Single source so the
# staging copies below cannot drift. NOTE: the .sql transform files build
# subject_id differently (via raw-column override COALESCE arms); do NOT unify
# with those — a different expression on purpose.
_SUBJECT_ID_SQL = "uuid_6(s.school_id::text, s.subject, s.assessment_type, s.grade, s.session, s.item_name)"
_S_FRESH_ROWS_SQL = text(
    f"""
    SELECT DISTINCT
      {_SUBJECT_ID_SQL} AS subject_id,
      s.school_id::text AS school_id,
      s.session, s.subject, s.assessment_type, s.grade, s.item_name
    FROM stg_student_submission s
    JOIN schools sch ON sch.school_id = s.school_id
    WHERE s.user_role_id = sch.student_role_id
    """
)
_FRESH_EDGES_SQL = text(
    f"""
    SELECT DISTINCT s.school_id::text AS school_id, s.item_id,
      {_SUBJECT_ID_SQL} AS subject_id
    FROM stg_student_submission s
    JOIN schools sch ON sch.school_id = s.school_id
    WHERE s.user_role_id = sch.student_role_id AND s.item_id IS NOT NULL
    """
)
_PER_RUN_SUBJECTS_SQL = text(
    f"""
    SELECT DISTINCT
      {_SUBJECT_ID_SQL} AS subject_id
    FROM stg_student_submission s
    JOIN schools sch ON sch.school_id = s.school_id
    WHERE s.user_role_id = sch.student_role_id
    """
)
_PASS_A_ITEMS_STUDENT_SQL = text(
    """
    INSERT INTO _scope_items (school_id, item_id)
    SELECT DISTINCT s.school_id, s.item_id
    FROM stg_student_submission s
    JOIN schools sch ON sch.school_id = s.school_id
    WHERE s.user_role_id = sch.student_role_id AND s.item_id IS NOT NULL
    ON CONFLICT DO NOTHING
    """
)
_PASS_A_ITEMS_QD_SQL = text(
    """
    INSERT INTO _scope_items (school_id, item_id)
    SELECT DISTINCT q.school_id, q.item_id
    FROM stg_question_data q
    WHERE q.item_id IS NOT NULL AND q.school_id IS NOT NULL
    ON CONFLICT DO NOTHING
    """
)
_INSERT_ASSESS_SQL = text(
    """
    INSERT INTO _scope_assessments
      (subject_id, school_id, session, subject, assessment_type, grade, item_name)
    VALUES
      (:subject_id, CAST(:school_id AS uuid), :session, :subject, :assessment_type, :grade, :item_name)
    ON CONFLICT (subject_id) DO NOTHING
    """
)
_RENAME_HOP_SQL = text(
    """
    INSERT INTO _scope_assessments
      (subject_id, school_id, session, subject, assessment_type, grade, item_name)
    SELECT DISTINCT f.subject_id, f.school_id, f.session, f.subject,
           f.assessment_type, f.grade, f.item_name
    FROM fact_student_submission f
    WHERE (f.school_id, f.item_id) IN (SELECT school_id, item_id FROM _scope_items)
    ON CONFLICT (subject_id) DO NOTHING
    """
)
_SWEPT_EDGES_SQL = text(
    """
    SELECT DISTINCT f.school_id::text AS school_id, f.item_id, f.subject_id
    FROM fact_student_submission f
    WHERE (f.school_id, f.item_id) IN (SELECT school_id, item_id FROM _scope_items)
      AND f.item_id IS NOT NULL AND f.subject_id IS NOT NULL
    """
)
_FINALIZE_ITEMS_SQL = text(
    """
    INSERT INTO _scope_items (school_id, item_id)
    SELECT DISTINCT f.school_id, f.item_id
    FROM fact_student_submission f
    WHERE f.subject_id IN (SELECT subject_id FROM _scope_assessments)
      AND f.item_id IS NOT NULL
    ON CONFLICT DO NOTHING
    """
)
# #13 GROUP-grain roster coverage. Coverage is matched per (group_id, user_uid),
# NOT (school_id, user_uid): a partial re-scrape of one subject can no longer be
# vouched for by a co-ingested SIBLING subject in a DIFFERENT rename-group. Within
# ONE rename-linked group sibling vouching IS intended (the subjects are the same
# assessment under churned item_ids). ``need`` = every (group, student) in the
# pre-delete fact; ``have`` = every (group, student) in pass-B staging (staged
# uuid_6 → group via _scope_assessments). A ``need`` (group, student) absent from
# ``have`` marks the WHOLE group uncovered; we return every subject in an
# uncovered group so the Python gate prunes it atomically.
_ROSTER_UNCOVERED_SQL = text(
    """
    WITH need AS (
      SELECT DISTINCT sa.group_id, f.user_uid
      FROM fact_student_submission f
      JOIN _scope_assessments sa ON sa.subject_id = f.subject_id
      WHERE f.user_uid IS NOT NULL
    ),
    have AS (
      SELECT DISTINCT sa.group_id, s.user_uid
      FROM stg_student_submission s
      JOIN schools sch ON sch.school_id = s.school_id
      JOIN _scope_assessments sa
        ON sa.subject_id = uuid_6(
             s.school_id::text, s.subject, s.assessment_type,
             s.grade, s.session, s.item_name)
      WHERE s.user_role_id = sch.student_role_id AND s.user_uid IS NOT NULL
    ),
    uncovered_groups AS (
      SELECT DISTINCT n.group_id
      FROM need n
      LEFT JOIN have h ON h.group_id = n.group_id AND h.user_uid = n.user_uid
      WHERE h.group_id IS NULL
    )
    SELECT DISTINCT sa.subject_id
    FROM _scope_assessments sa
    JOIN uncovered_groups ug ON ug.group_id = sa.group_id
    """
)
# #3 staging prune (issued from Python by _apply_roster_gate AFTER pass B, BEFORE
# the temp-table prune): delete a pruned group's rows from staging so the upsert
# dims (dim_item / dim_unit_lesson / dim_section) never see them and cannot leave
# orphan rows. uuid_6 over staging's OWN post-override columns == the fact
# subject_id build. :ids is the pruned (failed) subject_id set.
_STAGING_PRUNE_SS_SQL = text(
    """
    DELETE FROM stg_student_submission s
    WHERE uuid_6(s.school_id::text, s.subject, s.assessment_type,
                 s.grade, s.session, s.item_name) = ANY(CAST(:ids AS text[]))
    """
)
# Delete pruned-ONLY items from stg_question_data: (school_id, item_id) owned by a
# pruned subject and NOT shared with any SURVIVING subject. MUST run BEFORE the
# stg_student_submission prune above (it needs the pruned rows present to map
# item → subject). Items shared with a survivor stay (dim_question_data still
# builds them).
_STAGING_PRUNE_QD_SQL = text(
    """
    DELETE FROM stg_question_data q
    WHERE (q.school_id, q.item_id) IN (
        SELECT s.school_id, s.item_id
        FROM stg_student_submission s
        WHERE s.item_id IS NOT NULL
          AND uuid_6(s.school_id::text, s.subject, s.assessment_type,
                     s.grade, s.session, s.item_name) = ANY(CAST(:ids AS text[]))
        EXCEPT
        SELECT s.school_id, s.item_id
        FROM stg_student_submission s
        WHERE s.item_id IS NOT NULL
          AND NOT (uuid_6(s.school_id::text, s.subject, s.assessment_type,
                          s.grade, s.session, s.item_name) = ANY(CAST(:ids AS text[])))
    )
    """
)
_RECOMPUTE_ITEMS_SURVIVORS_SQL = text(
    f"""
    INSERT INTO _scope_items (school_id, item_id)
    SELECT DISTINCT f.school_id, f.item_id
    FROM fact_student_submission f
    WHERE f.subject_id IN (SELECT subject_id FROM _scope_assessments)
      AND f.item_id IS NOT NULL
    UNION
    SELECT DISTINCT s.school_id, s.item_id
    FROM stg_student_submission s
    JOIN schools sch ON sch.school_id = s.school_id
    WHERE s.user_role_id = sch.student_role_id
      AND s.item_id IS NOT NULL
      AND {_SUBJECT_ID_SQL}
          IN (SELECT subject_id FROM _scope_assessments)
    ON CONFLICT DO NOTHING
    """
)


async def _exec_sql_file(session: AsyncSession, base: Path, relpath: str) -> int:
    """Read + split + execute one .sql file; return last meaningful rowcount."""
    sql = (base / relpath).read_text(encoding="utf-8")
    return await _exec_statements(session, _split_sql_statements(sql))


def _scoped_staging_files() -> list[str]:
    """Staging files run in scoped mode (both passes), _SCOPED_SKIP excluded,
    in TRANSFORMATIONS_ORDER order (stg_question_data then stg_student_submission)."""
    return [
        rp
        for rp, tag in TRANSFORMATIONS_ORDER
        if tag == "staging" and Path(rp).stem not in _SCOPED_SKIP
    ]


async def _prepare_scope(
    session: AsyncSession, base: Path, scope_run_ids: Sequence[str]
) -> _ScopePrep:
    """Discovery (pass A): populate the scope carrier from the batch's raw.

    Steps (all with _scope_assessments EMPTY so staging takes the pass-A arm):
      1. _scope_run_ids ← batch runs; run pass-A staging (full batch).
      2. Read S_fresh natural keys + fresh item→subject edges + pass-A items.
      3. Per-run attribution loop (run_subjects) — needed for worker run→status.
      4. Populate _scope_assessments = S_fresh, then rename-hop swept subjects
         (fact owners of pass-A items) so an item re-ingested under a new name
         sweeps its OLD subject.
      5. Build GROUPS (connected components) from fresh + swept edges; persist
         group_id per subject (5b) and pre-prune locked-session groups (5c).
      6. Finalize _scope_items = pass-A items ∪ fact items of S (pre-delete).
      7. Clear _scope_run_ids so pass B (later) takes the subject-scoped arm.
    """
    run_id_list = [str(r) for r in scope_run_ids]
    ss_file = "01_staging/stg_student_submission.sql"

    # 1. run_ids ← batch; pass-A staging (full batch)
    await session.execute(text("TRUNCATE _scope_run_ids"))
    if run_id_list:
        await session.execute(
            text(
                "INSERT INTO _scope_run_ids (run_id) "
                "SELECT CAST(x AS uuid) FROM unnest(CAST(:ids AS text[])) AS x "
                "ON CONFLICT DO NOTHING"
            ),
            {"ids": run_id_list},
        )
    for relpath in _scoped_staging_files():
        await _exec_sql_file(session, base, relpath)

    # 2. capture fresh subjects, edges, pass-A items
    s_fresh_rows = [dict(r._mapping) for r in (await session.execute(_S_FRESH_ROWS_SQL)).all()]
    fresh_edges = [
        (r.school_id, r.item_id, r.subject_id)
        for r in (await session.execute(_FRESH_EDGES_SQL)).all()
    ]
    await session.execute(_PASS_A_ITEMS_STUDENT_SQL)
    await session.execute(_PASS_A_ITEMS_QD_SQL)

    landed_student = int(
        (
            await session.execute(
                text(
                    "SELECT count(*) FROM raw_student_submission "
                    "WHERE ingestion_run_id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"ids": run_id_list or [None]},
            )
        ).scalar()
        or 0
    )

    # 3. per-run attribution (S still empty → pure pass-A arm per run)
    run_subjects: dict[str, frozenset[str]] = {}
    for run in run_id_list:
        await session.execute(text("TRUNCATE _scope_run_ids"))
        await session.execute(
            text("INSERT INTO _scope_run_ids (run_id) VALUES (CAST(:r AS uuid))"),
            {"r": run},
        )
        await _exec_sql_file(session, base, ss_file)
        subs = {r.subject_id for r in (await session.execute(_PER_RUN_SUBJECTS_SQL)).all()}
        run_subjects[run] = frozenset(subs)

    # 4. populate _scope_assessments (fresh, then rename-hop swept)
    if s_fresh_rows:
        await session.execute(_INSERT_ASSESS_SQL, s_fresh_rows)
    await session.execute(_RENAME_HOP_SQL)

    # 5. GROUPS from fresh + swept edges
    swept_edges = [
        (r.school_id, r.item_id, r.subject_id)
        for r in (await session.execute(_SWEPT_EDGES_SQL)).all()
    ]
    subjects = frozenset(
        r[0] for r in (await session.execute(text("SELECT subject_id FROM _scope_assessments"))).all()
    )
    groups = _connected_components(subjects, fresh_edges + swept_edges)

    # 5b. Persist group_id per subject (#13 group-grain roster reads it). The id
    # is the lexicographically-smallest subject_id in the component — stable and
    # deterministic.
    group_of: dict[str, str] = {}
    for comp in groups:
        gid = min(comp)
        for s in comp:
            group_of[s] = gid
    if group_of:
        sids = list(group_of.keys())
        await session.execute(
            text(
                "UPDATE _scope_assessments sa SET group_id = v.group_id "
                "FROM unnest(CAST(:sids AS text[]), CAST(:gids AS text[])) "
                "AS v(subject_id, group_id) WHERE sa.subject_id = v.subject_id"
            ),
            {"sids": sids, "gids": [group_of[s] for s in sids]},
        )

    # 5c. #18 locked-group pre-prune. If any group touches a locked
    # (school, session), fail the WHOLE group up-front (fail-closed at group
    # grain) so the scoped fact DELETE below never fires the BEFORE-DELETE-
    # FOR-EACH-ROW historic-lock trigger on a locked row — a single such row
    # would roll back the ENTIRE co-ingested batch (the full path pays only the
    # cheaper statement-level TRUNCATE trigger). Locked subjects are handed to
    # the roster gate as pre_pruned so they get the same clean prune (staging +
    # _scope_items + failed marking); the fact DELETE at
    # 07_facts/fact_student_submission.sql keys on subject_id ∈ _scope_assessments,
    # so removing them there is exactly what avoids the per-row trigger cost.
    # locked_sessions is permanently empty on prod → inert there.
    locked_pruned = await _locked_group_prune(session, groups)

    # 6. finalize _scope_items (pass-A items already present) + fact items of S
    await session.execute(_FINALIZE_ITEMS_SQL)

    # 7. clear run_ids → pass B (run later) takes the subject-scoped arm
    await session.execute(text("TRUNCATE _scope_run_ids"))

    return _ScopePrep(
        groups=groups,
        run_subjects=run_subjects,
        landed_student=landed_student,
        subjects=subjects,
        locked_pruned=locked_pruned,
    )


async def _locked_group_prune(
    session: AsyncSession,
    groups: list[frozenset[str]],
) -> frozenset[str]:
    """#18: return every subject in a group that touches a locked (school,session).

    Whole groups fail atomically (fail-closed at group grain); co-ingested groups
    that touch no lock are preserved. Inert when nothing is locked (the prod
    invariant), so the normal path is untouched.
    """
    from app.repositories.locked_sessions_repository import LockedSessionsRepository

    repo = LockedSessionsRepository(session)
    if not await repo.any_locked():
        return frozenset()

    locked_pairs = {(row["school_id"], row["session"]) for row in await repo.list_all()}
    sa_pair: dict[str, tuple[str, str | None]] = {
        r.subject_id: (r.school_id, r.session)
        for r in (
            await session.execute(
                text("SELECT subject_id, school_id::text AS school_id, session "
                     "FROM _scope_assessments")
            )
        ).all()
    }
    pruned: set[str] = set()
    for comp in groups:
        if any(sa_pair.get(s) in locked_pairs for s in comp):
            pruned |= set(comp)
    if pruned:
        logger.error(
            "§LOCK pre-prune: %d subject(s) across group(s) touch a locked "
            "(school,session) and are pruned up-front (whole group, fail-closed) "
            "so the scoped fact DELETE never trips the per-row historic-lock "
            "trigger. Contributing run(s) will be marked failed; raw retained. "
            "Pruned subjects: %s",
            len(pruned), sorted(pruned),
        )
    return frozenset(pruned)


async def _apply_roster_gate(
    session: AsyncSession,
    groups: list[frozenset[str]],
    *,
    pre_pruned: frozenset[str] = frozenset(),
) -> tuple[frozenset[str], frozenset[str]]:
    """Roster completeness gate — run AFTER pass B, BEFORE any dim/fact write.

    Coverage is matched at GROUP grain (#13): for every subject_id ∈ S with
    pre-delete fact, each (group_id, user_uid) in that fact MUST reappear in
    pass-B staging, else the WHOLE group FAILS (a partial/truncated re-scrape).
    ``pre_pruned`` folds in the #18 locked-session groups already selected in
    _prepare_scope so they get the same clean prune. Failing groups are pruned
    atomically from _scope_assessments (never split — DO-NOT #16); their rows are
    also removed from staging (#3) so the upsert dims never see them, and
    _scope_items is recomputed from the survivors. LOCAL (full raw ancestry)
    never trips; prod complete re-scrape passes; prod partial re-scrape fails.

    Returns (survivors, failed_subjects).
    """
    uncovered = {
        r.subject_id for r in (await session.execute(_ROSTER_UNCOVERED_SQL)).all()
    }
    failed_subjects: set[str] = set(pre_pruned)
    n_failed_groups = 0
    for g in groups:
        if (g & uncovered) or (g & pre_pruned):
            failed_subjects |= g
            n_failed_groups += 1

    if failed_subjects:
        ids = list(failed_subjects)
        # #3 staging prune (BEFORE the temp-table prune). QD prune first: it needs
        # the pruned student rows still present to map item → subject. Then drop
        # the pruned student rows so the upsert dims (dim_item / dim_unit_lesson /
        # dim_section) build only from survivors and cannot orphan.
        await session.execute(_STAGING_PRUNE_QD_SQL, {"ids": ids})
        await session.execute(_STAGING_PRUNE_SS_SQL, {"ids": ids})
        await session.execute(
            text(
                "DELETE FROM _scope_assessments "
                "WHERE subject_id = ANY(CAST(:ids AS text[]))"
            ),
            {"ids": ids},
        )
        await session.execute(text("TRUNCATE _scope_items"))
        await session.execute(_RECOMPUTE_ITEMS_SURVIVORS_SQL)
        logger.error(
            "§ROSTER-GATE: pruned %d group(s) / %d subject(s) — incomplete "
            "re-scrape (students in the pre-delete fact absent from fresh staging) "
            "or a locked-session group (#18). Contributing run(s) will be marked "
            "failed; their raw is retained for a full-assessment re-scrape. Pruned "
            "subjects: %s",
            n_failed_groups,
            len(failed_subjects),
            sorted(failed_subjects),
        )

    survivors = frozenset(
        r[0] for r in (await session.execute(text("SELECT subject_id FROM _scope_assessments"))).all()
    )
    return survivors, frozenset(failed_subjects)


async def _handle_empty_scope(
    landed_student: int,
    results: TransformResult,
    *,
    all_pruned: bool,
    run_subjects: dict[str, frozenset[str]] | None = None,
    subjects: frozenset[str] = frozenset(),
) -> TransformResult:
    """No survivors: NEVER raise. Always attach a no-op sentinel and return so the
    worker marks the folded run(s) FAILED and RETAINS their raw (purge skips) —
    NOT succeeded+applied+purged, which would silently drop the correction.

    Raising here would propagate out of the transform gate, roll the worker's txn
    back (leaving the warehouse dirty flag set and the runs ``landed``), and the
    dirty-drain re-drive would re-process the same batch forever (an infinite
    retry loop). Returning a terminal sentinel instead lets the worker fail the
    runs, clear the dirty flag, and move on.

    ``noop_reason`` distinguishes the three cases (see ``ScopeReport``):
      * ``"qd_only"``    — landed 0 student rows (question-data-only / empty).
      * ``"all_pruned"`` — subjects discovered, roster gate pruned every group.
      * ``"no_subjects"``— real student raw landed but 0 subjects discovered
        (a genuine anomaly — logged at ERROR).
    """
    reason = (
        "qd_only"
        if landed_student == 0
        else ("all_pruned" if all_pruned else "no_subjects")
    )
    if reason == "qd_only":
        logger.warning(
            "scoped transform no-op: batch landed 0 student-submission row(s) "
            "(question-data-only or empty ingest) — nothing to build. The scoped "
            "path cannot apply question-data alone; the folded run(s) are marked "
            "FAILED and their raw is RETAINED (not purged). Re-scrape with "
            "submissions or run a full rebuild to apply the change."
        )
    elif reason == "all_pruned":
        logger.warning(
            "scoped transform no-op: %d student-submission row(s) landed but the "
            "roster gate pruned EVERY assessment group (partial/truncated "
            "re-scrape) — nothing to build. The folded run(s) are marked FAILED "
            "and their raw is RETAINED (not purged). Re-scrape the full "
            "assessment(s) to apply the change.",
            landed_student,
        )
    else:  # no_subjects — a real anomaly
        logger.error(
            "scoped transform no-op: %d student-submission row(s) landed but the "
            "batch produced ZERO in-scope subjects — nothing to build. This is an "
            "anomaly: check schools.student_role_id and the tenant overrides "
            "(subject/grade/item_label), or run a full-assessment re-scrape. The "
            "folded run(s) are marked FAILED and their raw is RETAINED (not "
            "purged).",
            landed_student,
        )
    results.scope = ScopeReport(
        run_subjects=run_subjects or {},
        groups=(),
        survivors=frozenset(),
        failed_subjects=subjects,
        noop_reason=reason,
    )
    return results


async def run_all(
    session: AsyncSession,
    only_tag: str | None = None,
    isolate_cubes: bool = False,
    scope_run_ids: Sequence[str] | None = None,
) -> TransformResult:
    """Execute every SQL file in TRANSFORMATIONS_ORDER (or only the tagged subset).

    Returns:
        ``TransformResult`` — a dict mapping each `model_name` (the .sql stem) to
        the rowcount of the LAST executed statement in that file (Postgres `-1`
        coerced to 0). On a scoped run it also carries a ``.scope``
        (``ScopeReport``) the worker uses to map each run to succeeded/failed.

    Scoped mode (``scope_run_ids`` is not None) rebuilds ONLY the batch's
    assessments; see the module docstring for the full flow. ``only_tag`` cannot
    be combined with a scope (scoped mode inherently runs the whole chain).

    Transactionality:
        We do NOT begin a nested transaction here by default. The caller's
        session is the unit of atomicity: if the caller commits at the end,
        the entire pipeline succeeds-or-fails atomically.

        Pass ``isolate_cubes=True`` to wrap each cube file in a per-file
        SAVEPOINT — a single cube failure is logged + skipped without rolling
        back earlier work (production partial-refresh preference).
    """
    scoped = scope_run_ids is not None
    if scoped and only_tag is not None:
        raise ValueError(
            "--tag cannot be combined with --scope-run-id/--scope-landed: a "
            "scoped run must execute the full pipeline (staging → cubes)."
        )

    base = _base_dir()
    results = TransformResult()
    failed_cubes: list[str] = []  # track isolate_cubes failures to fail loudly

    # Global transform mutex. Re-entrant no-op on the worker path (it already
    # holds this key); the first acquirer on any CLI path. Closes the concurrent
    # -rebuild hole. MUST run inside the caller's transaction (advisory xact
    # locks release at commit).
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:k)"), {"k": _TRANSFORM_LOCK_KEY}
    )

    # Disable intra-query parallelism for this transaction. The full-fact scans
    # here (the §HISTORIC fingerprint, the cube anti-trash checks, dim_reconcile,
    # and the GROUPING-SETS cube recomputes) otherwise spawn parallel workers that
    # allocate shared-memory segments; on a container with a small /dev/shm those
    # fail with "could not resize shared memory segment ... No space left on
    # device". These checks are cheap enough serially and this keeps the build
    # portable across shm sizes. SET LOCAL is scoped to the caller's transaction.
    await session.execute(text("SET LOCAL max_parallel_workers_per_gather = 0"))

    # Scope carrier: always created (empty in full mode → predicates no-op).
    await _create_scope_temp_tables(session)

    # §HISTORIC: fingerprint every (school, session, subject) slice BEFORE any
    # write. Verified again at the end; a violation raises and the caller's
    # transaction rolls the whole build back. This sits at the chokepoint every
    # transform path funnels through. The guard fingerprint stays GLOBAL (never
    # scoped to a subset of schools). Parallelism is already disabled txn-wide
    # above (the single SET LOCAL) for /dev/shm portability.
    historic_before = await _fact_session_fingerprints(session)
    raw_coverage = await _raw_session_coverage(session)  # log only
    present_slices = {(sch, sess) for (sch, sess, _subj) in historic_before}
    frozen = sorted(s for s in present_slices if s not in raw_coverage)
    logger.info(
        "§HISTORIC: %d subject-slice(s) present across %d (school,session) "
        "slice(s), %d frozen (no raw ancestry)",
        len(historic_before), len(present_slices), len(frozen),
    )
    for school, sess in frozen:
        logger.info("§HISTORIC: frozen school=%s session=%s", school, sess)

    # §LOCK layer 2: refuse an unscoped-TRUNCATE build while any session is
    # locked. Inert (no scan) when nothing is locked. Scoped runs permit the two
    # scratch staging TRUNCATEs; a legacy full rebuild is still refused via them.
    await _assert_no_locked_truncate(session, base, only_tag, scoped)

    scope_report: ScopeReport | None = None
    in_scope: frozenset[str] | None = None

    if scoped:
        assert scope_run_ids is not None  # narrow for type-checkers
        if not list(scope_run_ids):
            # Empty scope (e.g. --scope-landed found no runs). NOT a full rebuild:
            # running pass A with an empty _scope_run_ids would hit the FULL arm
            # and stage all raw. Legitimate no-op.
            logger.info("scoped transform no-op: no run_ids in scope — nothing to build.")
            return results
        prep = await _prepare_scope(session, base, scope_run_ids)
        if not prep.subjects:
            # No subjects discovered at all (|S| = 0).
            return await _handle_empty_scope(
                prep.landed_student,
                results,
                all_pruned=False,
                run_subjects=prep.run_subjects,
                subjects=prep.subjects,
            )

        # pass B: re-run staging scoped to S (subject-scoped arm).
        for relpath in _scoped_staging_files():
            rc = await _exec_sql_file(session, base, relpath)
            results[Path(relpath).stem] = rc

        # Roster gate → prune failed groups (roster-incomplete #13 + locked #18),
        # before any dim/fact write.
        survivors, failed_subjects = await _apply_roster_gate(
            session, prep.groups, pre_pruned=prep.locked_pruned
        )
        if not survivors:
            # Every group pruned → nothing to build. No-op sentinel (no raise).
            return await _handle_empty_scope(
                prep.landed_student,
                results,
                all_pruned=True,
                run_subjects=prep.run_subjects,
                subjects=prep.subjects,
            )

        scope_report = ScopeReport(
            run_subjects=prep.run_subjects,
            groups=tuple(prep.groups),
            survivors=survivors,
            failed_subjects=failed_subjects,
        )
        in_scope = survivors

    # Main loop. Scoped mode skips the staging tag (already run as pass B above).
    for relpath, tag in TRANSFORMATIONS_ORDER:
        if only_tag is not None and tag != only_tag:
            continue
        if scoped and tag == "staging":
            continue

        sql_path = base / relpath
        sql = sql_path.read_text(encoding="utf-8")

        statements = _split_sql_statements(sql)
        model_name = Path(relpath).stem

        # Per-file SAVEPOINT only for cubes when isolate_cubes is requested.
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
                failed_cubes.append(model_name)
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
    # but the seed CSV never covered. Must run AFTER dim_question_data exists;
    # the cube files above join dim_standard, so re-run the cube tag when new
    # aliases land to refresh their labels.
    if only_tag is None or only_tag == "cubes":
        added = await _augment_standard_aliases(session)
        if added:
            logger.info("transformations.alias_augment added=%d; refreshing cubes", added)
            for relpath, tag in TRANSFORMATIONS_ORDER:
                if tag != "cubes":
                    continue
                await _exec_sql_file(session, base, relpath)

    # A skipped cube leaves stale report data — never let the run look green.
    if failed_cubes:
        banner = " !! ".join(failed_cubes)
        logger.error(
            "transformations.STALE_CUBES the following cubes FAILED and are STALE: %s",
            banner,
        )
        raise RuntimeError(f"STALE CUBES (not rebuilt): {banner}")

    # Cube anti-trash: cubes are unguarded by §HISTORIC — RAISE on any stale
    # leaf row with no backing fact/dim (both modes; baseline 0). In scoped mode
    # the anti-joins are restricted to the touched school(s) — the only cubes the
    # build could have dirtied (full mode stays global).
    await _assert_no_cube_trash(session, scoped=scoped)

    # §HISTORIC verification. Runs LAST, on the same session, so a violation
    # raises before the caller commits and the rollback undoes every write in
    # this build. Full mode derives in_scope from the FRESHLY-BUILT fact (the
    # after-fingerprint just read, which coalesces subject_id identically) so a
    # staging/fact bug that silently drops a subject is caught.
    historic_after = await _fact_session_fingerprints(session)
    if in_scope is None:
        in_scope = frozenset(subject for (_school, _session, subject) in historic_after)
    # (f) #15: full-mode only, permit a legitimate relabel/removal that MOVED rows
    # between subject_ids within a raw-covered (school, session) slice whose
    # slice-level (count, fingerprint) is preserved — downgrade the would-be
    # out-of-scope violation to a logged warning. A genuine slice SHRINK still
    # RAISES. Scoped mode passes None → strict (prod stays fail-closed). No
    # configuration lookup here (the env tripwire depends on that).
    _assert_historic_slices_intact(
        historic_before,
        historic_after,
        in_scope,
        full_mode_raw_coverage=(None if scoped else raw_coverage),
    )
    logger.info(
        "§HISTORIC: verified — %d frozen (school,session) slice(s), "
        "%d in-scope subject(s)",
        len(frozen), len(in_scope),
    )

    results.scope = scope_report
    return results


async def _augment_standard_aliases(session: AsyncSession) -> int:
    """Insert missing Schoology-alias rows into dim_standard (idempotent).

    Uses the resolver in ``app.transformations.standard_alias_resolver`` — the
    single source of truth for alias→base resolution (the seed CLI re-imports
    the identical module) — driven over the live async session. Returns the
    number of rows inserted.
    """
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


async def _discover_landed_runs(session: AsyncSession) -> list[str]:
    """--scope-landed: run_ids whose raw landed but transforms are not applied.

    A run's raw survives (was never purged) exactly while transforms_applied is
    false; the self-healing purge deletes raw only for succeeded+applied runs. So
    "landed, not yet transformed" = status='landed' AND transforms_applied false
    AND ≥1 raw student row still present. One idempotent pass — safe to re-run.

    The ``status = 'landed'`` filter (#16) matches the worker's ``_scope_run_ids``
    fold semantics and stops a full-raw box (where legacy 'succeeded' runs never
    set the real transforms_applied COLUMN) from re-scoping the whole history.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT r.run_id::text AS run_id
                FROM ingestion_runs r
                WHERE r.status = 'landed'
                  AND COALESCE(r.transforms_applied, false) = false
                  AND EXISTS (
                      SELECT 1 FROM raw_student_submission x
                      WHERE x.ingestion_run_id = r.run_id
                  )
                ORDER BY 1
                """
            )
        )
    ).all()
    return [r.run_id for r in rows]


async def _main(
    only_tag: str | None,
    scope_run_ids: Sequence[str] | None,
    scope_landed: bool,
) -> int:
    async with session_scope() as session:
        if scope_landed:
            scope_run_ids = await _discover_landed_runs(session)
            logger.info(
                "scope: --scope-landed discovered %d landed-not-transformed run(s)",
                len(scope_run_ids),
            )
        results = await run_all(
            session, only_tag=only_tag, scope_run_ids=scope_run_ids
        )
    total = sum(results.values())
    logger.info("transformations.complete models=%d total_rows=%d", len(results), total)
    if results.scope is not None:
        rep = results.scope
        logger.info(
            "scope: %d survivor subject(s), %d failed/pruned, %d group(s) across "
            "%d run(s)",
            len(rep.survivors), len(rep.failed_subjects), len(rep.groups),
            len(rep.run_subjects),
        )
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
        help="Run only the SQL files tagged with this value (default: all). "
        "Cannot be combined with --scope-run-id/--scope-landed.",
    )
    parser.add_argument(
        "--scope-run-id",
        dest="scope_run_ids",
        action="append",
        default=None,
        metavar="UUID",
        help="Scoped incremental rebuild for this ingestion run_id (repeatable). "
        "Rebuilds ONLY the assessments the batch (re)ingested.",
    )
    parser.add_argument(
        "--scope-landed",
        action="store_true",
        help="Scoped incremental rebuild for ALL runs whose raw landed but has "
        "not yet been transformed (auto-discovered).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level.",
    )
    args = parser.parse_args(argv)
    _setup_logging(args.log_level)

    if args.scope_landed and args.scope_run_ids:
        parser.error("--scope-landed and --scope-run-id are mutually exclusive.")
    if args.tag is not None and (args.scope_landed or args.scope_run_ids):
        parser.error("--tag cannot be combined with --scope-run-id/--scope-landed.")

    try:
        return await _main(args.tag, args.scope_run_ids, args.scope_landed)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    _sys.exit(asyncio.run(main()))
