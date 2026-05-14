"""End-to-end ingestion test against the real `data/Athenian/` corpus.

Requires:
    * Postgres at $DATABASE_URL (default localhost:56322 / supabase local).
    * Athenian schools row seeded (`supabase/seeds/schools_athenian.sql`).
    * Migrations applied (raw_*, ingestion_runs, ingested_files exist).

This test:
    1. TRUNCATEs raw_* + ingested_files + ingestion_runs.
    2. Runs the full ingestion against `data/Athenian/`.
    3. Asserts row counts.
    4. Re-runs ingestion → all counts unchanged (idempotent).

DATA NOTE — duplicate-content CSVs:
    The Athenian corpus contains 105 CSV files but only 99 distinct content hashes:
    6 pairs of files (Sec 1 ↔ Sec 2 in Grade 6 Science Unit-7 and Social Studies
    World-History-Quiz-2) are byte-identical. The scraper exports the same file
    for both sections of a shared course. Per the schema's
    UNIQUE (school_id, file_hash) constraint on `ingested_files`, only the
    first file of each duplicate pair is recorded; the others are correctly
    skipped on idempotency. This is a real data quirk, not a defect.

    Effect: first-run files_processed = 99 (not 105); files_skipped = 6.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.blob_client import LocalBlobClient
from app.jobs.db import session_scope
from app.jobs.ingest_schoology import run_ingestion


DATA_ROOT = Path(__file__).resolve().parents[3] / "data"
ATHENIAN_DIR = DATA_ROOT / "Athenian"


pytestmark = pytest.mark.skipif(
    not ATHENIAN_DIR.exists(), reason="data/Athenian not present"
)


async def _counts() -> dict[str, int]:
    """Snapshot key table row counts."""
    async with session_scope() as session:
        out: dict[str, int] = {}
        for tbl in (
            "raw_submission_summary",
            "raw_student_submission",
            "raw_question_data",
            "ingested_files",
        ):
            r = await session.execute(text(f"SELECT count(*) FROM {tbl}"))
            out[tbl] = r.scalar_one()
        r = await session.execute(
            text("SELECT count(*) FROM ingestion_runs WHERE status='succeeded'")
        )
        out["ingestion_runs_succeeded"] = r.scalar_one()
    return out


@pytest.mark.asyncio
async def test_full_ingestion_and_idempotency(
    reset_raw_tables: None, athenian_school_id: UUID
) -> None:
    """Run the ingestion twice and verify counts + idempotency."""
    # Use an explicit LocalBlobClient pointing at <repo>/data so we don't
    # depend on the env var being set in CI.
    bc = LocalBlobClient(data_root=DATA_ROOT)

    summary = await run_ingestion(school_filter="Athenian", blob_client=bc)
    assert summary.error_count == 0
    # 105 files seen on disk; 6 are content-duplicate pairs (see module docstring).
    assert summary.files_seen == 105
    assert summary.files_processed == 99
    assert summary.files_skipped == 6

    snap1 = await _counts()
    # Each unique file content gets one ingested_files row → 99 rows.
    assert snap1["ingested_files"] == 99
    # raw_student_submission: 99 unique CSVs × their row counts.
    # We don't drop the 6 dup CSVs' worth of data — they share a hash with
    # Sec 1 of the same content, and Sec 1's section column is what's recorded.
    # Validate against the > 5,000 floor from the task brief.
    assert snap1["raw_student_submission"] > 5000
    assert snap1["raw_submission_summary"] > 0
    assert snap1["raw_question_data"] > 2000
    assert snap1["ingestion_runs_succeeded"] >= 1

    # Re-run — every file's content-hash is now in ingested_files, so all 105
    # are skipped (yes, the 6 duplicates skip a SECOND time).
    summary2 = await run_ingestion(school_filter="Athenian", blob_client=bc)
    assert summary2.error_count == 0
    assert summary2.files_skipped == 105
    assert summary2.files_processed == 0
    assert summary2.rows_inserted == 0

    snap2 = await _counts()
    assert snap2["raw_submission_summary"] == snap1["raw_submission_summary"]
    assert snap2["raw_student_submission"] == snap1["raw_student_submission"]
    assert snap2["raw_question_data"] == snap1["raw_question_data"]
    assert snap2["ingested_files"] == snap1["ingested_files"]
    # Two succeeded runs total
    assert snap2["ingestion_runs_succeeded"] == snap1["ingestion_runs_succeeded"] + 1


@pytest.mark.asyncio
async def test_a_outer_rollback_zeros_run_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B2: when the phase-2 OUTER transaction is rolled back, the run-history
    row must NOT contain the (now-rolled-back) per-file counters.

    We force the outer commit to fail by monkeypatching `session_scope` on its
    second invocation (phase 2). The per-blob SAVEPOINTs have already committed
    by the time the outer commit runs — but those savepoint inserts roll back
    with the outer transaction. So the run row should record 0 rows_inserted /
    0 files_processed (NOT the savepoint counters).

    Test name prefixed with `a_` so pytest collects it BEFORE the
    full-ingestion test (avoids cross-loop pool corruption with
    session-scoped engine).
    """
    from contextlib import asynccontextmanager

    from app.jobs import db as db_mod
    from app.jobs import ingest_schoology as ingest_mod
    from app.jobs.db import dispose_engine

    # Fresh engine for THIS event loop — avoids cross-loop pool corruption.
    await dispose_engine()

    # Inline TRUNCATE (replaces the reset_raw_tables fixture) — doing it after
    # the dispose_engine() call ensures we work with this loop's connections.
    async with session_scope() as session:
        await session.execute(
            text(
                """
                TRUNCATE TABLE
                    raw_submission_summary,
                    raw_student_submission,
                    raw_question_data,
                    ingested_files,
                    ingestion_runs
                RESTART IDENTITY CASCADE
                """
            )
        )
        # Verify the Athenian school is seeded (skip otherwise).
        r = await session.execute(
            text("SELECT 1 FROM schools WHERE schoology_building_id = '186370968'")
        )
        if r.first() is None:
            pytest.skip("Athenian schools row not seeded")

    bc = LocalBlobClient(data_root=DATA_ROOT)

    original_session_scope = db_mod.session_scope
    call_counter = {"n": 0}

    @asynccontextmanager
    async def patched_session_scope():
        call_counter["n"] += 1
        async with original_session_scope() as s:
            if call_counter["n"] == 2:
                # phase-2 session: kill the outer commit so run_ingestion's
                # outer try/except catches the failure and resets counters.
                async def failing_commit() -> None:
                    raise RuntimeError("simulated outer-txn failure")

                s.commit = failing_commit  # type: ignore[method-assign]
            yield s

    monkeypatch.setattr(ingest_mod, "session_scope", patched_session_scope)

    with pytest.raises(RuntimeError, match="simulated outer-txn failure"):
        await ingest_mod.run_ingestion(school_filter="Athenian", blob_client=bc)

    # Verify the run-history row has zero counters and status='failed'.
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT status, rows_inserted, files_processed
                FROM ingestion_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
        )
        row = r.one()
        assert row.status == "failed"
        assert row.rows_inserted == 0
        assert row.files_processed == 0

    # Also confirm the rolled-back inserts didn't survive: raw_* tables
    # should be empty (the test fixture truncated them at the start).
    async with session_scope() as session:
        for tbl in ("raw_submission_summary", "raw_student_submission", "raw_question_data"):
            r = await session.execute(text(f"SELECT count(*) FROM {tbl}"))
            assert r.scalar_one() == 0, f"{tbl} should be empty after outer rollback"

    # Dispose so the next test (full-ingestion) starts with a clean engine
    # bound to its own event loop.
    await dispose_engine()
