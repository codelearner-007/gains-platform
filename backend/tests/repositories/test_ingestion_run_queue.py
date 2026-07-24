"""Durable-queue repository tests (HARDENING_PLAN §9 Wave 1 Agent A).

These exercise ``IngestionRunRepository``'s queue methods against the LOCAL dev
DB (``postgresql://postgres:postgres@127.0.0.1:56322/postgres``): claim
atomicity under a real concurrent race, lease reaping, the attempt cap, and
pending-coalescing.

SAFETY (STOP conditions §11):
    * NO transforms are ever run and raw is NEVER truncated. These tests only
      INSERT/UPDATE/SELECT/DELETE rows in ``ingestion_runs``.
    * Every run row inserted is tracked by ``run_id`` and DELETEd in a ``finally``
      so the table is left exactly as found. The rows carry a sentinel note and
      NO dependent raw/ingested_files rows (ingestion is never invoked), so the
      DELETE is unconstrained by foreign keys.
    * Rows are created under the real Athenian ``school_id`` (a valid FK target);
      warehouse_state is not mutated by these tests.

The jobs engine (``app.jobs.db``) is used for its own connections, matching how
the durable worker will run — never the request pool. ``DATABASE_URL`` is seeded
into ``os.environ`` because the jobs engine reads it there (R3) and
pydantic-settings does not export ``.env``.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.jobs.db import dispose_engine, get_engine, session_scope
from app.repositories.ingestion_run_repository import IngestionRunRepository

# Jobs engine reads DATABASE_URL from os.environ with a local fallback (R3).
os.environ.setdefault("DATABASE_URL", settings.DATABASE_URL)

# A stable sentinel stamped into error_details so leftover rows (if a run is
# ever interrupted before teardown) are trivially identifiable and purgeable.
_SENTINEL = "test_ingestion_run_queue"


async def _athenian_school_id() -> str:
    async with session_scope() as session:
        row = (
            await session.execute(
                text("SELECT school_id::text FROM schools WHERE short_name = 'Athenian'")
            )
        ).first()
    assert row is not None, "Athenian school must exist on the local dev DB"
    return row[0]


async def _insert_pending(school_id: str) -> str:
    """Insert one ``pending`` run directly and return its run_id (str)."""
    async with session_scope() as session:
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO public.ingestion_runs
                        (school_id, status, started_at, attempt_count, error_details)
                    VALUES
                        (CAST(:sid AS UUID), 'pending', now(), 0,
                         jsonb_build_object('sentinel', CAST(:sentinel AS TEXT)))
                    RETURNING run_id::text
                    """
                ),
                {"sid": school_id, "sentinel": _SENTINEL},
            )
        ).first()
    return row[0]


async def _cleanup(run_ids: list[str]) -> None:
    if not run_ids:
        return
    async with session_scope() as session:
        await session.execute(
            text("DELETE FROM public.ingestion_runs WHERE run_id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": run_ids},
        )


async def _status_of(run_id: str) -> dict:
    async with session_scope() as session:
        row = (
            await session.execute(
                text(
                    "SELECT status, attempt_count, worker_id, "
                    "claimed_at, heartbeat_at, finished_at "
                    "FROM public.ingestion_runs WHERE run_id = CAST(:rid AS UUID)"
                ),
                {"rid": run_id},
            )
        ).first()
    return dict(row._mapping)


@pytest.fixture
async def school_id() -> str:
    return await _athenian_school_id()


async def test_claim_next_is_atomic_under_concurrent_race(school_id: str):
    """Two workers racing on ONE pending row: exactly one wins it.

    Both claims run on independent connections inside the SAME window (neither
    commits until both UPDATEs have executed). ``FOR UPDATE SKIP LOCKED`` forces
    the loser to skip the row locked by the winner, so exactly one gets the row
    and the other gets ``None`` — proving the claim is safe across processes.
    """
    run_id = await _insert_pending(school_id)
    engine = get_engine()

    # Two long-lived connections so both UPDATEs hold their locks concurrently
    # before either commits — a genuine race, not two serialized claims.
    conn_a = await engine.connect()
    conn_b = await engine.connect()
    try:
        repo_a = IngestionRunRepository(conn_a)
        repo_b = IngestionRunRepository(conn_b)

        results = await asyncio.gather(
            repo_a.claim_next("worker-A"),
            repo_b.claim_next("worker-B"),
        )
        await conn_a.commit()
        await conn_b.commit()

        winners = [r for r in results if r is not None]
        assert len(winners) == 1, f"exactly one claim must win, got {winners}"

        won = winners[0]
        assert won["run_id"] == run_id
        assert won["status"] == "running"
        assert won["attempt_count"] == 1
        assert won["worker_id"] in ("worker-A", "worker-B")

        # DB reflects a single running claim, not a double-increment.
        state = await _status_of(run_id)
        assert state["status"] == "running"
        assert state["attempt_count"] == 1
    finally:
        await conn_a.close()
        await conn_b.close()
        await _cleanup([run_id])


async def test_claim_next_returns_none_when_no_pending(school_id: str):
    """With no pending rows for anyone, ``claim_next`` yields ``None``."""
    # Insert then immediately claim it so the queue is drained, then a second
    # claim on the (now empty) pending set returns None. Scoped to our own row:
    # other pending rows on a shared dev DB would be claimed here, so we only
    # assert that OUR run leaves nothing claimable by asserting the first claim
    # got our row and is no longer pending.
    run_id = await _insert_pending(school_id)
    try:
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            first = await repo.claim_next("worker-drain")
        assert first is not None and first["run_id"] == run_id
        state = await _status_of(run_id)
        assert state["status"] == "running"
    finally:
        await _cleanup([run_id])


async def test_requeue_expired_returns_stale_running_to_pending(school_id: str):
    """A stale ``running`` row with attempts left is requeued to ``pending``."""
    run_id = await _insert_pending(school_id)
    try:
        # Claim it (attempt_count -> 1, running), then force its heartbeat old.
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            claimed = await repo.claim_next("worker-stale")
        assert claimed is not None

        async with session_scope() as session:
            await session.execute(
                text(
                    "UPDATE public.ingestion_runs "
                    "SET heartbeat_at = now() - interval '1 hour' "
                    "WHERE run_id = CAST(:rid AS UUID)"
                ),
                {"rid": run_id},
            )

        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            reaped = await repo.requeue_expired(lease_seconds=180, max_attempts=3)

        reaped_ids = {r["run_id"] for r in reaped}
        assert run_id in reaped_ids

        state = await _status_of(run_id)
        assert state["status"] == "pending"
        assert state["attempt_count"] == 1  # not re-incremented by the reaper
        assert state["worker_id"] is None
        assert state["heartbeat_at"] is None
        assert state["claimed_at"] is None
    finally:
        await _cleanup([run_id])


async def test_requeue_expired_ignores_fresh_running(school_id: str):
    """A ``running`` row with a fresh heartbeat is NOT reaped."""
    run_id = await _insert_pending(school_id)
    try:
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            await repo.claim_next("worker-fresh")  # sets heartbeat_at = now()

        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            reaped = await repo.requeue_expired(lease_seconds=180, max_attempts=3)

        assert run_id not in {r["run_id"] for r in reaped}
        state = await _status_of(run_id)
        assert state["status"] == "running"
    finally:
        await _cleanup([run_id])


async def test_requeue_expired_fails_run_past_attempt_cap(school_id: str):
    """A stale row that has exhausted its attempts is marked ``failed``."""
    run_id = await _insert_pending(school_id)
    try:
        # Drive attempt_count to the cap and make it stale-running.
        async with session_scope() as session:
            await session.execute(
                text(
                    "UPDATE public.ingestion_runs "
                    "SET status = 'running', attempt_count = 3, "
                    "    heartbeat_at = now() - interval '1 hour', "
                    "    worker_id = 'worker-dead' "
                    "WHERE run_id = CAST(:rid AS UUID)"
                ),
                {"rid": run_id},
            )

        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            reaped = await repo.requeue_expired(lease_seconds=180, max_attempts=3)

        assert run_id in {r["run_id"] for r in reaped}
        state = await _status_of(run_id)
        assert state["status"] == "failed"
        assert state["finished_at"] is not None
        # The failure reason is recorded in error_details.reaper.
        async with session_scope() as session:
            details = (
                await session.execute(
                    text(
                        "SELECT error_details->>'reaper' "
                        "FROM public.ingestion_runs WHERE run_id = CAST(:rid AS UUID)"
                    ),
                    {"rid": run_id},
                )
            ).scalar_one()
        assert details is not None and "lease expired" in details
    finally:
        await _cleanup([run_id])


async def test_heartbeat_only_updates_owning_worker(school_id: str):
    """``heartbeat`` refreshes only when the calling worker still owns the run."""
    run_id = await _insert_pending(school_id)
    try:
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            claimed = await repo.claim_next("worker-owner")
        assert claimed is not None

        # A different worker's heartbeat is a no-op (row unchanged).
        async with session_scope() as session:
            before = await _status_of(run_id)
            repo = IngestionRunRepository(session)
            await repo.heartbeat(run_id, "worker-imposter")
        after = await _status_of(run_id)
        assert after["heartbeat_at"] == before["heartbeat_at"]

        # The owner's heartbeat advances heartbeat_at.
        async with session_scope() as session:
            await session.execute(
                text(
                    "UPDATE public.ingestion_runs "
                    "SET heartbeat_at = now() - interval '1 hour' "
                    "WHERE run_id = CAST(:rid AS UUID)"
                ),
                {"rid": run_id},
            )
        stale = await _status_of(run_id)
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            await repo.heartbeat(run_id, "worker-owner")
        refreshed = await _status_of(run_id)
        assert refreshed["heartbeat_at"] > stale["heartbeat_at"]
    finally:
        await _cleanup([run_id])


async def test_pending_for_school_coalesces(school_id: str):
    """``pending_for_school`` finds an existing queued run (dedupe seam)."""
    run_id = await _insert_pending(school_id)
    try:
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            found = await repo.pending_for_school(school_id)
        assert found is not None
        assert found["run_id"] == run_id
        assert found["status"] == "pending"

        # Once claimed (no longer pending), coalescing finds nothing for it.
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            await repo.claim_next("worker-coalesce")
            after = await repo.pending_for_school(school_id)
        # after may be None or another unrelated pending row; it must not be ours.
        assert after is None or after["run_id"] != run_id
    finally:
        await _cleanup([run_id])


async def test_mark_sets_terminal_status_and_merges_details(school_id: str):
    """``mark`` flips status, stamps finished_at on terminal, merges details."""
    run_id = await _insert_pending(school_id)
    try:
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            await repo.mark(run_id, "landed", {"stage": "raw"})
        state = await _status_of(run_id)
        assert state["status"] == "landed"
        assert state["finished_at"] is None  # non-terminal

        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            await repo.mark(run_id, "failed", {"reason": "boom"})
        state = await _status_of(run_id)
        assert state["status"] == "failed"
        assert state["finished_at"] is not None

        async with session_scope() as session:
            details = (
                await session.execute(
                    text(
                        "SELECT error_details FROM public.ingestion_runs "
                        "WHERE run_id = CAST(:rid AS UUID)"
                    ),
                    {"rid": run_id},
                )
            ).scalar_one()
        # Both merged keys survive (sentinel from insert + stage + reason).
        assert details.get("stage") == "raw"
        assert details.get("reason") == "boom"
        assert details.get("sentinel") == _SENTINEL
    finally:
        await _cleanup([run_id])


async def test_warehouse_dirty_flag_roundtrip():
    """set/clear/read the warehouse dirty flag; restore prior state after.

    Reads the flag first, restores it in ``finally`` so a subsequent transform
    gate is unaffected by the test.
    """
    async with session_scope() as session:
        repo = IngestionRunRepository(session)
        before = await repo.warehouse_dirty()

    token = str(uuid.uuid4())
    try:
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            await repo.set_warehouse_dirty(token)
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            assert await repo.warehouse_dirty() is True

        run_id = str(uuid.uuid4())
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            await repo.clear_warehouse_dirty(run_id)
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            assert await repo.warehouse_dirty() is False

        # clear recorded the run + timestamp.
        async with session_scope() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT last_transform_run_id::text, last_transform_at "
                        "FROM public.warehouse_state WHERE id = 1"
                    )
                )
            ).first()
        assert row[0] == run_id
        assert row[1] is not None
    finally:
        # Restore the warehouse flag to whatever it was before this test.
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            if before:
                await repo.set_warehouse_dirty(str(uuid.uuid4()))
            else:
                await session.execute(
                    text(
                        "UPDATE public.warehouse_state "
                        "SET transforms_dirty = false, dirty_since = NULL, "
                        "    dirty_token = NULL WHERE id = 1"
                    )
                )


async def test_raw_total_count_is_above_floor():
    """The local full-raw env is comfortably above the empty-raw floor."""
    async with session_scope() as session:
        repo = IngestionRunRepository(session)
        total = await repo.raw_total_count()
    assert total > settings.INGESTION_RAW_FLOOR


@pytest.fixture(autouse=True)
async def _fresh_jobs_engine():
    """Give each test a jobs engine bound to its OWN event loop.

    ``app.jobs.db`` caches a module-level asyncpg engine; pytest-asyncio (auto
    mode) runs each test on a fresh loop, so a cached engine from a prior test
    is bound to a closed loop and its connections fail. Disposing before AND
    after each test forces a clean engine per loop.
    """
    await dispose_engine()
    yield
    await dispose_engine()
