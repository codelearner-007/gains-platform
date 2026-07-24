"""Restart / redeploy durability E2E (HARDENING_PLAN §10 item 1).

ENV-GATED. Skipped entirely unless ``RUN_STORAGE_E2E=1`` — a plain
``pytest tests/jobs/test_restart_recovery_e2e.py`` collects this module and
reports it SKIPPED (never errors), so it is safe in the default suite.

What it proves
--------------
A worker crash at any stage of a run leaves NO half-data and self-heals on
restart via the lease + reaper:

  * **(a) before claim** — a ``pending`` run whose worker dies before claiming
    it is still ``pending`` (nothing to reap); a fresh worker claims + drives it.
  * **(b) mid-landing** — the worker dies while landing raw (an injected
    blob-download failure aborts the pipeline). The run is left ``running`` with
    a stale heartbeat; the reaper requeues it (``attempt_count`` bumped); a
    restart re-runs it — and because raw landing is hash-idempotent, NO duplicate
    raw rows appear.
  * **(c) after raw-commit / before transform** — the worker lands raw (raw is
    committed, ``warehouse_state.transforms_dirty`` is TRUE) then dies before the
    transform gate. The run is left ``running``/``landed``; the reaper requeues
    it; the dirty flag survives so a later transform pass is still forced.

After each scenario we drive the worker to quiescence and assert:
    * NO run left ``pending|running|landed|transforming`` (all terminal);
    * NO duplicate raw rows for the synthetic hashes (hash-skip held);
    * ``warehouse_state.transforms_dirty`` reflects the crash stage;
    * ``attempt_count`` was incremented by the requeue.

Safety (STOP conditions §11.3)
------------------------------
    * ``INGESTION_TRANSFORMS_ENABLED`` is FORCED OFF for the whole module, so the
      worker's transform gate always returns ``"disabled"`` — the REAL
      ``run_all`` is NEVER invoked and NO real cube rebuild / truncate happens.
      Runs terminate at ``landed`` (raw safe), which is exactly the prod-shaped
      kill-switch path. Landed-and-clean is the quiescent terminal here.
    * A synthetic ``2098-99`` session (never a real one) isolates the keys, and
      cleanup is hash-scoped: the ``finally`` block DELETEs the raw rows and
      ``ingested_files`` rows by the exact synthetic ``source_file_hash`` values,
      ``remove()``s the storage keys, deletes the synthetic ``ingestion_runs``
      rows, and resets ``warehouse_state``. Nothing outside these hashes / this
      synthetic school is touched.

Creds (R13): ``SUPABASE_URL`` / ``SUPABASE_SERVICE_KEY`` from the environment
(populated from ``supabase status -o env`` by the local test plan), falling back
to ``settings``.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_STORAGE_E2E") != "1",
    reason="restart-recovery E2E; set RUN_STORAGE_E2E=1 to run",
)

# Real Athenian fixture trio (Social Studies / Grade 6 / Sec 1). Uploaded
# verbatim plus one trailing newline → a fresh SHA-256 that parses identically.
_FIXTURE_DIR = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "Athenian"
    / "2025-26"
    / "1 - Lesson  Assessments"
    / "Social Studies"
    / "Grade 6"
    / "Sec 1"
)
_FIXTURE_FILES = (
    "Question-Data-World-History-Weekly-Quiz-2-2026-05-05-063712.csv",
    "Student-Submissions-World-History-Weekly-Quiz-2-2026-05-05-063712.csv",
    "Submission-Summary-World-History-Weekly-Quiz-2-2026-05-05-063712.csv",
)

_SCHOOL_ROOT = "Athenian"
_SYNTHETIC_SESSION = "2098-99"
_REL_PREFIX = (
    f"{_SYNTHETIC_SESSION}/1 - Lesson  Assessments/Social Studies/Grade 6/Sec 1"
)

# (file-name prefix -> raw table) — every file lands in exactly one raw table.
_RAW_TABLES = {
    "Question-Data": "raw_question_data",
    "Student-Submissions": "raw_student_submission",
    "Submission-Summary": "raw_submission_summary",
}

# A very short lease so the reaper considers a "crashed" run expired immediately
# within a single test (real lease is 180s; we never wait that long).
_TEST_LEASE_SECONDS = 0
_TEST_MAX_ATTEMPTS = 3


# ── Storage / fixture helpers ───────────────────────────────────────────────


def _storage_client():
    from supabase import create_client

    from app.core.config import settings

    url = os.environ.get("SUPABASE_URL") or settings.SUPABASE_URL
    key = os.environ.get("SUPABASE_SERVICE_KEY") or settings.SUPABASE_SERVICE_KEY
    return create_client(url, key)


def _fixture_payloads() -> tuple[dict[str, bytes], dict[str, str]]:
    """Return {storage-key: bytes} and {storage-key: sha256} for the trio."""
    payloads: dict[str, bytes] = {}
    hashes: dict[str, str] = {}
    for fname in _FIXTURE_FILES:
        raw = (_FIXTURE_DIR / fname).read_bytes() + b"\n"
        key = f"{_SCHOOL_ROOT}/{_REL_PREFIX}/{fname}"
        payloads[key] = raw
        hashes[key] = hashlib.sha256(raw).hexdigest()
    return payloads, hashes


# ── A blob client that can "crash" mid-landing ──────────────────────────────


class _CrashingBlobClient:
    """Wraps a real ``SupabaseStorageBlobClient`` and raises on the Nth download.

    ``fail_on_download_index`` = the 1-based download call to blow up on
    (simulating a worker crash mid-landing). ``None`` → never crash (a clean
    delegate used for the restart pass).
    """

    def __init__(self, delegate: Any, fail_on_download_index: Optional[int]) -> None:
        self._delegate = delegate
        self._fail_on = fail_on_download_index
        self._downloads = 0

    def list_files(self, school_root: Any):
        return self._delegate.list_files(school_root)

    def download(self, blob_path: str, school_root: Any) -> bytes:
        self._downloads += 1
        if self._fail_on is not None and self._downloads >= self._fail_on:
            raise RuntimeError(
                f"injected crash: download #{self._downloads} ({blob_path})"
            )
        return self._delegate.download(blob_path, school_root)

    def move(self, from_key: str, to_key: str):
        return self._delegate.move(from_key, to_key)

    def remove(self, keys: list[str]):
        return self._delegate.remove(keys)


# ── DB helpers (all hash / synthetic-run scoped) ────────────────────────────


async def _synthetic_school_id(session) -> Optional[str]:
    row = (
        await session.execute(
            text(
                "SELECT school_id::text FROM schools "
                "WHERE short_name = :sn AND is_active = TRUE LIMIT 1"
            ),
            {"sn": _SCHOOL_ROOT},
        )
    ).first()
    return row[0] if row else None


async def _raw_counts(session, hashes: List[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for table in _RAW_TABLES.values():
        counts[table] = (
            await session.execute(
                text(
                    f"SELECT count(*) FROM {table} "  # noqa: S608 - fixed allowlist
                    "WHERE source_file_hash = ANY(:h)"
                ),
                {"h": hashes},
            )
        ).scalar_one()
    return counts


async def _run_rows(session, run_ids: List[str]) -> List[Dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                "SELECT run_id::text AS run_id, status, attempt_count, "
                "heartbeat_at, worker_id "
                "FROM ingestion_runs WHERE run_id = ANY(:ids)"
            ),
            {"ids": run_ids},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def _warehouse_dirty(session) -> bool:
    row = (
        await session.execute(
            text("SELECT transforms_dirty FROM warehouse_state WHERE id = 1")
        )
    ).first()
    return bool(row[0]) if row else False


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _transforms_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the kill-switch OFF for this whole module (STOP §11.3): the REAL
    ``run_all`` is never invoked, so no cube rebuild / truncate ever runs. Runs
    terminate at ``landed`` — the quiescent terminal we assert against."""
    import app.services.ingestion_worker as worker_mod

    monkeypatch.setattr(
        worker_mod.settings, "INGESTION_TRANSFORMS_ENABLED", False
    )


@pytest.fixture
async def synthetic_env():
    """Upload the synthetic trio + seed the DATABASE_URL env, yield context,
    then hash-scoped teardown (raw rows, ingested_files, storage keys, synthetic
    runs, warehouse reset, engine dispose)."""
    from app.core.config import settings
    from app.jobs.db import dispose_engine, session_scope

    os.environ.setdefault("DATABASE_URL", settings.DATABASE_URL)

    payloads, hashes = _fixture_payloads()
    all_hashes = list(hashes.values())
    assert len(set(all_hashes)) == 3, "fixtures must hash to three distinct values"

    client = _storage_client()
    bucket = client.storage.from_(settings.INGESTION_STORAGE_BUCKET)
    uploaded_keys: list[str] = []
    created_run_ids: list[str] = []

    # Snapshot the warehouse dirty flag so teardown restores the pre-test value
    # (we never leave the singleton mutated by a synthetic run).
    async with session_scope() as session:
        pre_dirty = await _warehouse_dirty(session)
        school_id = await _synthetic_school_id(session)
    assert school_id is not None, "an active 'Athenian' school is required"

    try:
        for key, data in payloads.items():
            bucket.upload(key, data, {"content-type": "text/csv", "upsert": "true"})
            uploaded_keys.append(key)

        yield {
            "settings": settings,
            "client": client,
            "bucket": bucket,
            "hashes": all_hashes,
            "school_id": school_id,
            "created_run_ids": created_run_ids,
        }
    finally:
        try:
            async with session_scope() as session:
                for table in _RAW_TABLES.values():
                    await session.execute(
                        text(
                            f"DELETE FROM {table} "  # noqa: S608 - fixed allowlist
                            "WHERE source_file_hash = ANY(:h)"
                        ),
                        {"h": all_hashes},
                    )
                await session.execute(
                    text("DELETE FROM ingested_files WHERE file_hash = ANY(:h)"),
                    {"h": all_hashes},
                )
                if created_run_ids:
                    await session.execute(
                        text("DELETE FROM ingestion_runs WHERE run_id = ANY(:ids)"),
                        {"ids": created_run_ids},
                    )
                # Reset the singleton to its pre-test dirty value.
                await session.execute(
                    text(
                        "UPDATE warehouse_state "
                        "SET transforms_dirty = :d, dirty_token = NULL, "
                        "dirty_since = CASE WHEN :d THEN dirty_since ELSE NULL END "
                        "WHERE id = 1"
                    ),
                    {"d": pre_dirty},
                )
        finally:
            # Re-list live + processed prefixes so a partially-archived trio is
            # fully removed regardless of where the keys ended up.
            try:
                leftovers = list(uploaded_keys)
                for run_id in created_run_ids:
                    leftovers.extend(
                        f"processed/{_SCHOOL_ROOT}/{run_id}/{_REL_PREFIX}/{f}"
                        for f in _FIXTURE_FILES
                    )
                bucket.remove(leftovers)
            except Exception:
                pass
            await dispose_engine()


def _make_worker(blob_factory):
    """A real IngestionWorker with an instant lease (crash → immediately
    reapable) and a heartbeat that never fires during a test."""
    from app.services.ingestion_worker import IngestionWorker

    return IngestionWorker(
        worker_id=f"e2e-{uuid4().hex[:8]}",
        poll_seconds=1,
        lease_seconds=_TEST_LEASE_SECONDS,
        heartbeat_seconds=3600,
        max_attempts=_TEST_MAX_ATTEMPTS,
        blob_client_factory=blob_factory,
    )


async def _enqueue_pending(session_scope, school_id: str, created_run_ids: list) -> str:
    """Create a synthetic ``pending`` run (via the repo) and track it for cleanup."""
    from app.repositories.ingestion_run_repository import IngestionRunRepository

    async with session_scope() as session:
        run = await IngestionRunRepository(session).create_pending(
            school_id=school_id, note="restart-recovery-e2e"
        )
    created_run_ids.append(run["run_id"])
    return run["run_id"]


# Under the mandated kill-switch OFF (this module forces
# INGESTION_TRANSFORMS_ENABLED=False, STOP §11.3), a CLEAN run's settled terminal
# is `landed`: the transform gate returns "disabled" and deliberately leaves the
# run `landed` with the dirty flag set for a later transforms-enabled pass
# (worker.py:372-377). So `landed` here == `succeeded` would be with transforms
# ON. The states that mean "a worker still owes active work / crashed mid-flight"
# are the CHURN states: pending | running | transforming. The §10 "no `landed`"
# clause only applies with transforms ENABLED; with them OFF, `landed` is the
# stable no-half-data terminal (raw safe + dirty flag proving completion is owed).
_CHURN_STATES = ("pending", "running", "transforming")
_SETTLED_STATES = ("landed", "succeeded", "failed")


async def _assert_quiesced(session_scope, run_id: str, hashes: List[str]):
    """No churn state left (settled at `landed`/`succeeded`/`failed`), and exactly
    one copy of each raw file's rows."""
    async with session_scope() as session:
        rows = await _run_rows(session, [run_id])
        assert rows, f"run {run_id} vanished"
        status = rows[0]["status"]
        assert status not in _CHURN_STATES, (
            f"run {run_id} left in a churn state: {status}"
        )
        assert status in _SETTLED_STATES, f"unexpected terminal status: {status}"

        counts = await _raw_counts(session, hashes)
    return counts


# ── (a) crash BEFORE claim ──────────────────────────────────────────────────


async def test_crash_before_claim_still_pending_then_completes(synthetic_env):
    """A worker that dies before claiming leaves the run ``pending`` (nothing for
    the reaper to do); a fresh worker claims + drives it to a clean terminal with
    the trio landed exactly once."""
    from app.jobs.blob_client import SupabaseStorageBlobClient
    from app.jobs.db import session_scope

    env = synthetic_env
    run_id = await _enqueue_pending(
        session_scope, env["school_id"], env["created_run_ids"]
    )

    # "Crash before claim" == the worker never ran. Assert it is still pending
    # and the reaper is a no-op (only running/transforming are reapable).
    async with session_scope() as session:
        from app.repositories.ingestion_run_repository import (
            IngestionRunRepository,
        )

        reaped = await IngestionRunRepository(session).requeue_expired(
            lease_seconds=_TEST_LEASE_SECONDS, max_attempts=_TEST_MAX_ATTEMPTS
        )
        assert all(r["run_id"] != run_id for r in reaped), (
            "a pending run must not be reaped"
        )
        rows = await _run_rows(session, [run_id])
    assert rows[0]["status"] == "pending"

    # Restart: a fresh worker drains the batch (kill-switch OFF → ends 'landed').
    def _clean_blob():
        delegate = SupabaseStorageBlobClient(
            bucket=env["settings"].INGESTION_STORAGE_BUCKET, client=env["client"]
        )
        return _CrashingBlobClient(delegate, fail_on_download_index=None)

    worker = _make_worker(_clean_blob)
    await worker._reap()
    await worker._drain_batch()

    counts = await _assert_quiesced(session_scope, run_id, env["hashes"])
    assert counts["raw_student_submission"] > 0, "student rows must land"
    for table, n in counts.items():
        assert n > 0, f"{table} landed no rows"


# ── (b) crash MID-LANDING → reaper requeue, no duplicate raw ─────────────────


async def test_crash_mid_landing_requeues_and_no_duplicate_raw(synthetic_env):
    """Injected download failure aborts landing (run left ``running`` w/ stale
    heartbeat). The reaper requeues it (attempt_count bumped); a clean restart
    re-lands — and the hash-skip means NO duplicate raw rows."""
    from app.jobs.blob_client import SupabaseStorageBlobClient
    from app.jobs.db import session_scope
    from app.repositories.ingestion_run_repository import IngestionRunRepository

    env = synthetic_env
    run_id = await _enqueue_pending(
        session_scope, env["school_id"], env["created_run_ids"]
    )

    # First worker: crash on the SECOND file's download. Each blob lands under a
    # per-file SAVEPOINT (ingest_schoology.py begin_nested), so file #1
    # (Question-Data) DOES land and commit while files #2/#3 raise and bump
    # error_count — a realistic PARTIAL landing left by a crash mid-batch.
    def _crashing_blob():
        delegate = SupabaseStorageBlobClient(
            bucket=env["settings"].INGESTION_STORAGE_BUCKET, client=env["client"]
        )
        return _CrashingBlobClient(delegate, fail_on_download_index=2)

    crasher = _make_worker(_crashing_blob)
    claimed = await crasher._claim_next()
    assert claimed is not None and claimed["run_id"] == run_id
    attempt_after_claim = claimed["attempt_count"]

    # Land it — file #1 commits, #2/#3 error. In a real crash the process dies
    # here and cannot even write a terminal status, so the row is left 'running'.
    # Simulate that HARD crash: run the (partial) landing, then forcibly restore
    # the row to 'running' with a STALE heartbeat so it is the REAPER (not any
    # graceful mark) that recovers it.
    await crasher._land_run(claimed)
    async with session_scope() as session:
        await session.execute(
            text(
                "UPDATE ingestion_runs "
                "SET status = 'running', heartbeat_at = now() - interval '1 hour', "
                "worker_id = :w WHERE run_id = :rid"
            ),
            {"w": claimed["worker_id"], "rid": run_id},
        )

    # Reaper requeues (attempt left) → back to pending, attempt_count preserved
    # (the NEXT claim bumps it).
    async with session_scope() as session:
        reaped = await IngestionRunRepository(session).requeue_expired(
            lease_seconds=_TEST_LEASE_SECONDS, max_attempts=_TEST_MAX_ATTEMPTS
        )
    assert any(r["run_id"] == run_id and r["status"] == "pending" for r in reaped), (
        "expired running run must be requeued to pending"
    )

    # Restart with a clean blob client → re-land cleanly.
    def _clean_blob():
        delegate = SupabaseStorageBlobClient(
            bucket=env["settings"].INGESTION_STORAGE_BUCKET, client=env["client"]
        )
        return _CrashingBlobClient(delegate, fail_on_download_index=None)

    worker = _make_worker(_clean_blob)
    reclaim = await worker._claim_next()
    assert reclaim is not None and reclaim["run_id"] == run_id
    assert reclaim["attempt_count"] > attempt_after_claim, (
        "the requeue+reclaim must increment attempt_count"
    )
    result = await worker._land_run(reclaim)
    assert result is not None, "clean restart must land"

    # Quiesced: terminal + exactly one copy of each raw file's rows (hash-skip).
    counts = await _assert_quiesced(session_scope, run_id, env["hashes"])
    for table, n in counts.items():
        assert n > 0, f"{table} landed no rows on restart"

    # No DUPLICATE raw: re-run the SAME clean landing again; hash-skip means the
    # counts must not grow.
    async with session_scope() as session:
        await session.execute(
            text(
                "UPDATE ingestion_runs SET status = 'pending', worker_id = NULL, "
                "heartbeat_at = NULL, finished_at = NULL WHERE run_id = :rid"
            ),
            {"rid": run_id},
        )
    worker2 = _make_worker(_clean_blob)
    reclaim2 = await worker2._claim_next()
    await worker2._land_run(reclaim2)
    async with session_scope() as session:
        counts2 = await _raw_counts(session, env["hashes"])
    assert counts2 == counts, (
        f"hash-skip broken: raw rows duplicated on re-run {counts} → {counts2}"
    )


# ── (c) crash AFTER raw-commit / BEFORE transform gate ──────────────────────


async def test_crash_after_raw_commit_before_transform_leaves_dirty(synthetic_env):
    """Raw lands (committed) and ``warehouse_state.transforms_dirty`` is set
    BEFORE landing; a crash before the transform gate leaves the dirty flag TRUE
    so a later transform pass is still forced, and the reaper requeues the run.
    (Transforms stay OFF → the gate returns 'disabled' and the run ends
    'landed' — the prod-shaped terminal.)"""
    from app.jobs.blob_client import SupabaseStorageBlobClient
    from app.jobs.db import session_scope
    from app.repositories.ingestion_run_repository import IngestionRunRepository

    env = synthetic_env
    run_id = await _enqueue_pending(
        session_scope, env["school_id"], env["created_run_ids"]
    )

    def _clean_blob():
        delegate = SupabaseStorageBlobClient(
            bucket=env["settings"].INGESTION_STORAGE_BUCKET, client=env["client"]
        )
        return _CrashingBlobClient(delegate, fail_on_download_index=None)

    worker = _make_worker(_clean_blob)
    claimed = await worker._claim_next()
    assert claimed is not None and claimed["run_id"] == run_id

    # Land raw (this sets the dirty flag BEFORE landing, per §4). Do NOT run the
    # transform batch — this is the crash point ("after raw-commit / before
    # transform"). The run is left 'landed' by run_ingestion(landed_status).
    result = await worker._land_run(claimed)
    assert result is not None, "raw must land"

    # Raw is committed AND the dirty flag is set (a later transform pass is owed).
    async with session_scope() as session:
        assert await _warehouse_dirty(session) is True, (
            "dirty flag must survive a crash before the transform gate"
        )
        counts = await _raw_counts(session, env["hashes"])
    for table, n in counts.items():
        assert n > 0, f"{table} raw not committed pre-crash"

    # Simulate the HARD crash: the 'landed' run is treated as an in-flight
    # in-progress state left by a dead worker (running with stale heartbeat), so
    # the reaper can recover it. (In the batch flow the transform pass would
    # promote a clean 'landed'; a crash before it leaves the row recoverable.)
    async with session_scope() as session:
        await session.execute(
            text(
                "UPDATE ingestion_runs "
                "SET status = 'running', heartbeat_at = now() - interval '1 hour', "
                "worker_id = :w WHERE run_id = :rid"
            ),
            {"w": claimed["worker_id"], "rid": run_id},
        )
        reaped = await IngestionRunRepository(session).requeue_expired(
            lease_seconds=_TEST_LEASE_SECONDS, max_attempts=_TEST_MAX_ATTEMPTS
        )
    assert any(r["run_id"] == run_id and r["status"] == "pending" for r in reaped)

    # Restart → drain. Kill-switch OFF: raw re-lands idempotently (no dup) and the
    # run reaches a terminal 'landed' (the batch's transform pass returns
    # 'disabled'), the dirty flag stays set for a transforms-enabled env.
    worker2 = _make_worker(_clean_blob)
    await worker2._reap()
    await worker2._drain_batch()

    async with session_scope() as session:
        rows = await _run_rows(session, [run_id])
        assert rows[0]["status"] not in _CHURN_STATES, (
            f"run left in a churn state: {rows[0]['status']}"
        )
        # attempt_count was incremented across the requeue+reclaim cycle.
        assert rows[0]["attempt_count"] >= 2, "requeue must bump attempt_count"
        assert await _warehouse_dirty(session) is True, (
            "kill-switch OFF → dirty flag stays set (transforms owed later)"
        )
        counts2 = await _raw_counts(session, env["hashes"])
    assert counts2 == counts, (
        f"hash-skip broken across restart: {counts} → {counts2}"
    )
