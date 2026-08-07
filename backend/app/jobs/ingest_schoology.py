"""Phase 1 ingestion orchestrator — read scraper CSVs → raw_* tables.

Mirrors the lifecycle in `tasks/backlog/01-gains-pipeline-finalized-plan.md` §5.1:

    1. Open ingestion_runs row, status='running'
    2. List active schools (or one if --school filter)
    3. For each school:
        a. List blobs under <school_root> via the configured BlobClient
        b. For each blob:
            - Compute SHA-256 over the bytes
            - Skip if (school_id, file_hash) is already in `ingested_files` (idempotency)
            - Parse → list of typed Pydantic models
            - INSERT batched into the matching raw_* table
            - INSERT into `ingested_files`
    4. Update ingestion_runs status='succeeded' (or 'failed' on any unhandled error)

CLI usage:
    cd backend && python -m app.jobs.ingest_schoology
    cd backend && python -m app.jobs.ingest_schoology --school Athenian
    # Also works from repo root via the `backend.` prefix:
    python -m backend.app.jobs.ingest_schoology --school 186370968
"""

# ruff: noqa: E402  -- intentional sys.path bootstrap below requires deferred imports

from __future__ import annotations

# ─── sys.path bootstrap ────────────────────────────────────────────────────
# Support running both:
#   cd backend && python -m app.jobs.ingest_schoology
#   python -m backend.app.jobs.ingest_schoology           # from repo root
# In the second form, the imports `from app.x` would fail without this fix:
# Python sees the package root as `backend.app...`, but the existing app code
# uses `from app.x` (consistent with `pyproject.toml` pythonpath = ["."]).
# Prepend `<repo>/backend` to sys.path so `from app.x` always resolves.
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
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

from app.jobs.blob_client import BlobClient, BlobInfo, make_blob_client
from app.jobs.db import dispose_engine, session_scope
from app.jobs.file_path_parser import (
    PathParseError,
    parse_relative_path,
)
from app.jobs.parsers import question_data as parse_question_data
from app.jobs.parsers import student_submission as parse_student_submission
from app.jobs.parsers import submission_summary as parse_submission_summary
from app.transformations import run_all as run_transformations


logger = logging.getLogger("ingest_schoology")


# ───────────────────────────────────────────────────────────────────────────
# Insert batch size — picked low enough for asyncpg's protocol.
# Tested at 500 rows × ~40 cols.
# ───────────────────────────────────────────────────────────────────────────
BATCH_SIZE = 500


@dataclass
class SchoolRow:
    """Subset of `schools` columns we need at runtime."""

    school_id: UUID
    name: str
    short_name: str
    schoology_building_id: str
    is_active: bool


@dataclass
class IngestSummary:
    """Aggregated counters for an ingestion run; returned + logged.

    Counter semantics:
        * `files_seen`: every blob touched (incl. skipped ones).
        * `files_skipped`: blobs already in `ingested_files` (idempotent skip).
        * `files_processed`: blobs that landed (rows actually committed).
        * `rows_inserted`: total raw_* rows that landed (committed).
        * `error_count`: per-file failures (advances even when SAVEPOINT rolls back).
        * `errors`: human-readable error strings, capped at 50 in error_details.

    On an OUTER-transaction rollback (phase 2 raises), `files_processed` and
    `rows_inserted` are reset to 0 by the caller — see `run_ingestion`.
    """

    files_seen: int = 0
    files_skipped: int = 0
    files_processed: int = 0
    rows_inserted: int = 0
    error_count: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def hash_school_lock_key(school_id: UUID) -> int:
    """Deterministic int64 advisory-lock key for a school.

    Uses the first 8 bytes of the school_id as a signed int64 so the key fits
    in `pg_try_advisory_xact_lock(bigint)`.
    """
    return int.from_bytes(school_id.bytes[:8], "big", signed=True)


# ───────────────────────────────────────────────────────────────────────────
# DB helpers — kept here (not in db.py) because they're orchestrator-specific.
# ───────────────────────────────────────────────────────────────────────────


_ALLOWED_DB_USERS = {"postgres", "service_role"}


async def _assert_privileged_db_user(session: AsyncSession) -> None:
    """Fail-fast if the ingestion job is connected as a non-privileged user.

    Phase 1 inserts cross-tenant rows into raw_* / ingestion_runs / ingested_files
    and must therefore bypass RLS. Locally that means `postgres`; in Supabase
    that means `service_role`. Anything else (e.g. `authenticated`, `anon`)
    would silently no-op INSERTs under RLS.
    """
    user = (await session.execute(text("SELECT current_user"))).scalar()
    if user not in _ALLOWED_DB_USERS:
        raise RuntimeError(
            f"Ingestion job requires postgres/service_role; got {user!r}. "
            "Check DATABASE_URL credentials."
        )


async def _list_schools(session: AsyncSession, school_filter: str | None) -> list[SchoolRow]:
    """Load active schools; optionally filter by short_name OR schoology_building_id."""
    sql = """
        SELECT school_id, name, short_name, schoology_building_id, is_active
        FROM schools
        WHERE is_active = TRUE
    """
    params: dict[str, str] = {}
    if school_filter:
        sql += " AND (short_name = :f OR schoology_building_id = :f OR name = :f)"
        params["f"] = school_filter
    sql += " ORDER BY short_name"

    result = await session.execute(text(sql), params)
    return [
        SchoolRow(
            school_id=row.school_id,
            name=row.name,
            short_name=row.short_name,
            schoology_building_id=row.schoology_building_id,
            is_active=row.is_active,
        )
        for row in result
    ]


async def _create_run(session: AsyncSession, school_id: UUID | None) -> UUID:
    """INSERT ingestion_runs row with status='running' and return its run_id.

    `school_id` semantics:
        * NULL → orchestrator run that targets >1 school (or all active schools).
          This includes the case where a `--school` filter happens to resolve
          to multiple schools.
        * non-NULL → run targets EXACTLY one school.

    Returns NULL school_id when the run targets >1 school. Per-school audit
    queries should match on `ingested_files.school_id` JOINed via
    `ingestion_run_id`, NOT on `ingestion_runs.school_id`.
    """
    result = await session.execute(
        text(
            """
            INSERT INTO ingestion_runs (school_id, status)
            VALUES (:school_id, 'running')
            RETURNING run_id
            """
        ),
        {"school_id": school_id},
    )
    run_id: UUID = result.scalar_one()
    return run_id


async def _adopt_run(
    session: AsyncSession, run_id: UUID, school_id: UUID | None
) -> None:
    """Adopt a caller-created ``pending`` run row (R1).

    When the endpoint pre-creates the ``ingestion_runs`` row (so the response can
    carry the id) and passes ``run_id`` in, phase 1 flips that row to
    ``running`` instead of INSERTing a new one. ``school_id`` is only filled if
    the row does not already carry one (the endpoint stamps it at create time).
    """
    await session.execute(
        text(
            """
            UPDATE ingestion_runs
            SET status = 'running',
                started_at = now(),
                school_id = COALESCE(school_id, :school_id)
            WHERE run_id = :run_id
            """
        ),
        {"run_id": run_id, "school_id": school_id},
    )


async def _finish_run(
    session: AsyncSession,
    run_id: UUID,
    status: str,
    summary: IngestSummary,
) -> None:
    """Update ingestion_runs with final status + counters.

    ``status`` is the caller-decided terminal/intermediate status. On a clean
    run this is ``landed_status`` (default ``"succeeded"`` for the CLI; the
    durable worker passes ``"landed"`` so the run is not marked ``succeeded``
    until transforms are applied). On failure it is always ``"failed"``.
    """
    error_details = (
        {"errors": summary.errors[:50]}  # cap to keep JSON sane
        if summary.errors
        else None
    )
    await session.execute(
        text(
            """
            UPDATE ingestion_runs
            SET status = :status,
                finished_at = now(),
                files_processed = :files_processed,
                rows_inserted = :rows_inserted,
                error_count = :error_count,
                error_details = CAST(:error_details AS jsonb)
            WHERE run_id = :run_id
            """
        ),
        {
            "status": status,
            "files_processed": summary.files_processed,
            "rows_inserted": summary.rows_inserted,
            "error_count": summary.error_count,
            "error_details": (
                None if error_details is None else json.dumps(error_details)
            ),
            "run_id": run_id,
        },
    )


async def _file_already_ingested(
    session: AsyncSession, school_id: UUID, file_hash: str
) -> bool:
    """Idempotency check — has this file (per school) already been ingested?"""
    result = await session.execute(
        text(
            """
            SELECT 1 FROM ingested_files
            WHERE school_id = :school_id AND file_hash = :file_hash
            LIMIT 1
            """
        ),
        {"school_id": school_id, "file_hash": file_hash},
    )
    return result.first() is not None


async def _record_ingested_file(
    session: AsyncSession,
    *,
    school_id: UUID,
    blob_path: str,
    file_hash: str,
    file_type: str,
    rows_ingested: int,
    ingestion_run_id: UUID,
) -> None:
    """Append to `ingested_files` so re-runs skip this blob."""
    await session.execute(
        text(
            """
            INSERT INTO ingested_files
                (school_id, blob_path, file_hash, file_type, rows_ingested, ingestion_run_id)
            VALUES (:school_id, :blob_path, :file_hash, :file_type, :rows_ingested, :run_id)
            ON CONFLICT (school_id, file_hash) DO NOTHING
            """
        ),
        {
            "school_id": school_id,
            "blob_path": blob_path,
            "file_hash": file_hash,
            "file_type": file_type,
            "rows_ingested": rows_ingested,
            "run_id": ingestion_run_id,
        },
    )


# ───────────────────────────────────────────────────────────────────────────
# INSERT helpers — one per raw_* table.
# Use ON CONFLICT DO NOTHING on (school_id, source_file_hash, md5(unique_key))
# so retries within a single failed run cannot fail-loud on duplicate rows.
# The dedup index is on md5(unique_key) (not the raw text) because some
# Schoology answer options embed multi-KB base64 image URIs that overflow the
# 8191-byte B-tree limit — see migration 20260611000100. The inference clause
# must match that expression index exactly.
# ───────────────────────────────────────────────────────────────────────────


_RAW_SUBMISSION_SUMMARY_SQL = text(
    """
    INSERT INTO raw_submission_summary (
      school_id, ingestion_run_id, source_file_path, source_file_hash, unique_key,
      schoology_id, first_name, last_name, unique_id_csv, job_title, gradebook_grade,
      submission_no, submission_score, question_label, question_score
    )
    VALUES (
      :school_id, :ingestion_run_id, :source_file_path, :source_file_hash, :unique_key,
      :schoology_id, :first_name, :last_name, :unique_id_csv, :job_title, :gradebook_grade,
      :submission_no, :submission_score, :question_label, :question_score
    )
    ON CONFLICT (school_id, source_file_hash, md5(unique_key)) DO NOTHING
    """
)


_RAW_STUDENT_SUBMISSION_SQL = text(
    """
    INSERT INTO raw_student_submission (
      school_id, ingestion_run_id, source_file_path, source_file_hash, unique_key,
      user_uid, username, last_name, first_name, user_role_id, user_school_id,
      user_school_name, course_nid, course_name, course_code, section_nid, section_name,
      section_code, section_instructors, item_type, item_id, item_name, first_access,
      latest_attempt, total_time, submission_grade, submission, question_id,
      associated_question_id, question_type, question, position_number, sub_question,
      answer_submission, correct_answer, points_received, points_possible,
      session, assessment_type, subject, grade, section, file_name
    )
    VALUES (
      :school_id, :ingestion_run_id, :source_file_path, :source_file_hash, :unique_key,
      :user_uid, :username, :last_name, :first_name, :user_role_id, :user_school_id,
      :user_school_name, :course_nid, :course_name, :course_code, :section_nid, :section_name,
      :section_code, :section_instructors, :item_type, :item_id, :item_name, :first_access,
      :latest_attempt, :total_time, :submission_grade, :submission, :question_id,
      :associated_question_id, :question_type, :question, :position_number, :sub_question,
      :answer_submission, :correct_answer, :points_received, :points_possible,
      :session, :assessment_type, :subject, :grade, :section, :file_name
    )
    ON CONFLICT (school_id, source_file_hash, md5(unique_key)) DO NOTHING
    """
)


_RAW_QUESTION_DATA_SQL = text(
    """
    INSERT INTO raw_question_data (
      school_id, ingestion_run_id, source_file_path, source_file_hash, unique_key,
      item_id, item_name, question_id, associated_question_id, total_points,
      question_type, question, position_number, sub_question, answer_option,
      answer_breakdown_count, answer_breakdown_pct, correct_answer,
      correctly_answered, most_points_earned, least_points_earned, average_points_earned,
      standards_val, session, assessment_type, subject, grade, section, file_name, question_no
    )
    VALUES (
      :school_id, :ingestion_run_id, :source_file_path, :source_file_hash, :unique_key,
      :item_id, :item_name, :question_id, :associated_question_id, :total_points,
      :question_type, :question, :position_number, :sub_question, :answer_option,
      :answer_breakdown_count, :answer_breakdown_pct, :correct_answer,
      :correctly_answered, :most_points_earned, :least_points_earned, :average_points_earned,
      :standards_val, :session, :assessment_type, :subject, :grade, :section, :file_name, :question_no
    )
    ON CONFLICT (school_id, source_file_hash, md5(unique_key)) DO NOTHING
    """
)


async def _insert_rows(
    session: AsyncSession,
    sql: TextClause,
    rows: list,
) -> int:
    """Batch-insert Pydantic rows; return the count attempted (not necessarily inserted on conflicts)."""
    if not rows:
        return 0
    payloads = [r.model_dump() for r in rows]
    # Strip UUID objects → str — asyncpg handles UUID natively, but mixing types
    # in executemany sometimes confuses the dialect. Keep UUID as-is; SQLAlchemy maps fine.
    total = 0
    # batch
    for i in range(0, len(payloads), BATCH_SIZE):
        batch = payloads[i : i + BATCH_SIZE]
        await session.execute(sql, batch)
        total += len(batch)
    return total


# ───────────────────────────────────────────────────────────────────────────
# Per-file processing
# ───────────────────────────────────────────────────────────────────────────


async def _process_blob(
    session: AsyncSession,
    *,
    school: SchoolRow,
    blob: BlobInfo,
    blob_client: BlobClient,
    school_root: str,
    run_id: UUID,
    summary: IngestSummary,
) -> None:
    """Hash → idempotency check → parse → INSERT → record."""
    summary.files_seen += 1

    try:
        parsed_path = parse_relative_path(blob.path)
    except PathParseError as e:
        logger.warning("[%s] skipping %s: %s", school.short_name, blob.path, e)
        summary.error_count += 1
        summary.errors.append(f"{school.short_name}/{blob.path}: {e}")
        return

    file_type = parsed_path.file_type

    rows_inserted = 0
    try:
        # E1 (HARDENING_PLAN §1, fixes F4): download + the idempotency SELECT are
        # INSIDE the counted try so a Storage download error (or an idempotency
        # query failure) bumps `error_count` and re-raises — instead of escaping
        # uncounted, which used to leave `error_count == 0` and let a
        # never-ingested file get archived to `processed/` (silent data loss).
        raw_bytes = blob_client.download(blob.path, school_root)
        file_hash = hashlib.sha256(raw_bytes).hexdigest()

        if await _file_already_ingested(session, school.school_id, file_hash):
            logger.info(
                "[%s] skip (already ingested): %s", school.short_name, blob.path
            )
            summary.files_skipped += 1
            return

        if file_type == "submission_summary":
            ss_rows = parse_submission_summary.parse(
                csv_bytes=raw_bytes,
                school_id=school.school_id,
                ingestion_run_id=run_id,
                source_file_path=blob.path,
                source_file_hash=file_hash,
            )
            rows_inserted = await _insert_rows(
                session, _RAW_SUBMISSION_SUMMARY_SQL, ss_rows
            )
        elif file_type == "student_submissions":
            stu_rows = parse_student_submission.parse(
                csv_bytes=raw_bytes,
                school_id=school.school_id,
                ingestion_run_id=run_id,
                source_file_path=blob.path,
                source_file_hash=file_hash,
                parsed_path=parsed_path,
            )
            rows_inserted = await _insert_rows(
                session, _RAW_STUDENT_SUBMISSION_SQL, stu_rows
            )
        elif file_type == "question_data":
            qd_rows = parse_question_data.parse(
                csv_bytes=raw_bytes,
                school_id=school.school_id,
                ingestion_run_id=run_id,
                source_file_path=blob.path,
                source_file_hash=file_hash,
                parsed_path=parsed_path,
            )
            rows_inserted = await _insert_rows(
                session, _RAW_QUESTION_DATA_SQL, qd_rows
            )
        else:
            logger.warning(
                "[%s] skipping unknown file_type %s: %s",
                school.short_name, file_type, blob.path,
            )
            summary.error_count += 1
            return
    except Exception as e:
        # Per-file failure: log + count. Re-raise so the SAVEPOINT around the
        # invocation site rolls back ONLY this file's INSERTs (the outer txn
        # — and its prior committed-via-savepoint files — survives).
        logger.exception("[%s] FAILED parsing %s: %s", school.short_name, blob.path, e)
        summary.error_count += 1
        summary.errors.append(f"{school.short_name}/{blob.path}: {e}")
        raise

    await _record_ingested_file(
        session,
        school_id=school.school_id,
        blob_path=blob.path,
        file_hash=file_hash,
        file_type=file_type,
        rows_ingested=rows_inserted,
        ingestion_run_id=run_id,
    )

    summary.files_processed += 1
    summary.rows_inserted += rows_inserted
    logger.info(
        "[%s] %s: parsed %s, inserted %d rows",
        school.short_name, blob.path, file_type, rows_inserted,
    )


def _school_root_for(school: SchoolRow) -> str:
    """Map a SchoolRow → relative blob path root.

    Phase 1 convention: the LocalBlobClient is rooted at <repo>/data, and each
    school's CSVs live at <school.short_name>/. Athenian's are at
    `data/Athenian/...`.
    """
    return school.short_name


# ───────────────────────────────────────────────────────────────────────────
# Main entry point
# ───────────────────────────────────────────────────────────────────────────


async def run_ingestion(
    *,
    school_filter: str | None = None,
    blob_client: BlobClient | None = None,
    whole_tree_root: str | None = None,
    skip_transforms: bool = False,
    scoped_transforms: bool = False,
    commit_every: int = 0,
    run_id: UUID | None = None,
    landed_status: str = "succeeded",
) -> IngestSummary:
    """Run a single ingestion pass.

    Args:
        school_filter: Optional short_name / schoology_building_id / name to limit to one school.
        blob_client: Override the default (env-derived) blob client. Used in tests.
        whole_tree_root: When set, the backup is a single MIXED tree (not split
            per-school folder). All schools' CSVs live under one root and each row
            carries its own "User School ID"; the staging layer resolves the real
            school per row. In that mode we make ONE pass over `whole_tree_root`
            (not one pass per school) to avoid ingesting every file 5×, then let
            staging distribute rows to all schools. `school_filter` then only
            restricts which schools' rows survive staging (None = all).
        scoped_transforms: OPT-IN incremental transform (default False → full
            rebuild, unchanged). When True (and ``skip_transforms`` is False),
            the transform pass is SCOPED to THIS run's raw: its ``run_id`` is
            passed as ``scope_run_ids`` so ``run_all`` rebuilds only the
            assessments this ingest touched (subject-scoped DELETE + insert +
            rollup recompute over preserved fact) instead of a destructive
            full-year rebuild. The default full rebuild is preserved for the
            local rebuild machine / ``gains_data`` paths.
        run_id: When set (R1), a caller has pre-created the ``ingestion_runs``
            row (status ``pending``) so it could return the id before the run
            executes. Phase 1 then ADOPTS that row (pending → running) instead of
            INSERTing a new one. When None, phase 1 creates the row itself.
        landed_status: The status phase 3 writes on a CLEAN run (E2,
            HARDENING_PLAN §1). Defaults to ``"succeeded"`` so the CLI is
            unchanged. The durable worker passes ``"landed"`` so a run that has
            only landed raw (``skip_transforms=True``) is not marked
            ``succeeded`` until the worker's transform gate applies transforms.
            A failed run always writes ``"failed"`` regardless of this value.

    Returns:
        IngestSummary with totals.

    Note on transaction strategy:
        Phase 1 (short txn): discover schools, assert DB user, open the run row.
        Phase 2 (long txn): process every blob, each wrapped in a SAVEPOINT so
            single-file failures don't abort the whole run. Per-school advisory
            lock prevents two concurrent runs from racing on UNIQUE constraints.
        Phase 3 (short txn): mark the run succeeded/failed.

        If the OUTER phase-2 transaction rolls back (rare — unhandled error
        outside the per-file SAVEPOINT scope), we reset `files_processed` and
        `rows_inserted` to 0 because none of the per-file work survived.
    """
    summary = IngestSummary()
    bc = blob_client or make_blob_client()

    # Phase 1: discover schools + open run (committed standalone so it's visible
    # even if the ingestion transaction fails).
    async with session_scope() as session:
        await _assert_privileged_db_user(session)
        schools = await _list_schools(session, school_filter)
        if not schools:
            logger.warning("No active schools matched filter=%r", school_filter)
            return summary
        # `school_id` semantics on `ingestion_runs`:
        #   * 1 school in scope → that school's UUID (per-school audit-friendly).
        #   * any other case (no filter, or filter resolved to >1 school) → NULL,
        #     denoting an orchestrator/multi-school run. Per-school audits should
        #     JOIN via `ingested_files.school_id` instead.
        run_school_id: UUID | None = schools[0].school_id if len(schools) == 1 else None
        if run_id is not None:
            # R1: caller pre-created the row (so the response could carry the id).
            # Adopt it (pending → running) instead of INSERTing a new row.
            await _adopt_run(session, run_id, run_school_id)
        else:
            run_id = await _create_run(session, run_school_id)

    # Phase 2: do the actual work in its own transaction.
    # E2: on a clean run phase 3 writes `landed_status` (default "succeeded" for
    # the CLI; the worker passes "landed"). A failure below overrides it.
    final_status = landed_status
    final_error: Exception | None = None
    try:
        async with session_scope() as session:
            # Whole-tree mode: the backup is one mixed tree, so we make a SINGLE
            # raw pass over it (stamping a representative school) instead of one
            # pass per school. Staging then resolves each row's real school from
            # the CSV "User School ID", distributing rows to every school.
            if whole_tree_root is not None:
                ingest_passes = [(schools[0], whole_tree_root)]
            else:
                ingest_passes = [(s, _school_root_for(s)) for s in schools]

            for school, school_root in ingest_passes:
                # Per-school advisory lock — prevents concurrent ingestion of
                # the same school from racing on UNIQUE (school_id, file_hash)
                # in `ingested_files`. Released automatically on txn end.
                lock_key = hash_school_lock_key(school.school_id)
                locked = await session.execute(
                    text("SELECT pg_try_advisory_xact_lock(:k)"),
                    {"k": lock_key},
                )
                if not locked.scalar():
                    logger.warning(
                        "skipping school %s — concurrent ingestion in progress",
                        school.short_name,
                    )
                    continue

                blobs: list[BlobInfo] = list(bc.list_files(school_root))
                logger.info(
                    "[%s] discovered %d blob(s) under %s",
                    school.short_name, len(blobs), school_root,
                )
                processed_since_commit = 0
                for blob in blobs:
                    # SAVEPOINT per blob: a parse failure rolls back only this
                    # file's INSERTs; prior files within this run keep their work.
                    try:
                        async with session.begin_nested():
                            await _process_blob(
                                session,
                                school=school,
                                blob=blob,
                                blob_client=bc,
                                school_root=school_root,
                                run_id=run_id,
                                summary=summary,
                            )
                    except Exception as e:
                        # _process_blob has already logged + bumped error counters.
                        logger.debug(
                            "[%s] SAVEPOINT rolled back for %s: %s",
                            school.short_name, blob.path, e,
                        )
                        # continue with next blob — single-file failure must not
                        # abort the entire run.

                    # Periodic commit for large/full ingests: bounds the open
                    # transaction so a multi-GB load does not accumulate ~150k
                    # subtransactions in ONE txn (the pg_subtrans cliff), and so
                    # progress is durable + resumable — a re-run skips
                    # already-recorded files via ingested_files + ON CONFLICT.
                    # Releases the per-school advisory lock between batches, which
                    # is acceptable for a single controlled bulk load. Opt-in
                    # (commit_every>0); the default single-transaction path is
                    # unchanged.
                    if commit_every and commit_every > 0:
                        processed_since_commit += 1
                        if processed_since_commit >= commit_every:
                            await session.commit()
                            processed_since_commit = 0
                            logger.info(
                                "[%s] committed batch — seen=%d processed=%d "
                                "skipped=%d rows=%d errors=%d",
                                school.short_name, summary.files_seen,
                                summary.files_processed, summary.files_skipped,
                                summary.rows_inserted, summary.error_count,
                            )

            # Phase 2 (continued): run staging + dimension transformations
            # against the raw rows we just landed. We share the same session
            # so raw INSERTs + transformation upserts commit atomically: if
            # transformations fail, the raw rows roll back too (plan §5.1
            # step 4). Phase 3 of the project will append fact/cube/hash
            # transformations to TRANSFORMATIONS_ORDER; this call picks them
            # up automatically.
            #
            # skip_transforms decouples the (huge, single-transaction) raw load
            # from the transform pipeline so a large/full ingest can commit raw
            # first, then run transforms STAGED per-tag with ANALYZE between
            # layers via `python -m app.transformations.runner --tag …`. The
            # inline all-in-one-transaction path is fine for small samples but
            # blows up on a full multi-GB build (stale planner stats →
            # catastrophic cube plan; managed Postgres cannot raise
            # max_locks_per_transaction).
            if skip_transforms:
                logger.info(
                    "transformations SKIPPED (raw-only ingest); run them staged "
                    "via `python -m app.transformations.runner --tag …`."
                )
            else:
                # Default (scoped_transforms=False) → scope_run_ids=None → full
                # rebuild, byte-identical to today. Opt-in scoped mode passes THIS
                # run's id so run_all rebuilds only the assessments it touched.
                scope_arg = [str(run_id)] if scoped_transforms else None
                xform_results = await run_transformations(
                    session, scope_run_ids=scope_arg
                )
                row_total = sum(xform_results.values())
                logger.info(
                    "transformations complete (%s): %d models, %d total rows touched",
                    "scoped" if scoped_transforms else "full",
                    len(xform_results),
                    row_total,
                )
    except Exception as e:
        # Outer phase-2 rollback. Phase 2 transaction is rolled back — none of
        # the per-file work survived. Counters describe what we attempted, not
        # what landed, so reset the "landed" counters to 0.
        final_status = "failed"
        final_error = e
        logger.exception("Ingestion run FAILED: %s", e)
        summary.rows_inserted = 0
        summary.files_processed = 0

    # Phase 3: persist the final status in its own transaction.
    async with session_scope() as session:
        await _finish_run(session, run_id, final_status, summary)

    if final_error is not None:
        raise final_error

    logger.info(
        "Ingestion complete: files_seen=%d processed=%d skipped=%d rows=%d errors=%d",
        summary.files_seen,
        summary.files_processed,
        summary.files_skipped,
        summary.rows_inserted,
        summary.error_count,
    )
    return summary


# ───────────────────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────────────────


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ingest_schoology")
    parser.add_argument(
        "--school",
        default=None,
        help="Only ingest one school (short_name | schoology_building_id | name).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level (DEBUG, INFO, WARNING).",
    )
    parser.add_argument(
        "--scoped-transforms",
        action="store_true",
        help=(
            "Incrementally rebuild ONLY the assessments this run ingests "
            "(subject-scoped) instead of a full destructive rebuild. Opt-in; "
            "the default remains a full rebuild."
        ),
    )
    args = parser.parse_args(argv)

    _setup_logging(args.log_level)

    try:
        summary = await run_ingestion(
            school_filter=args.school,
            scoped_transforms=args.scoped_transforms,
        )
    finally:
        await dispose_engine()

    return 0 if summary.error_count == 0 else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
