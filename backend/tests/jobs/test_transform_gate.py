"""Transform-gate / no-half-data E2E (HARDENING_PLAN §10 item 2).

ENV-GATED. Skipped entirely unless ``RUN_STORAGE_E2E=1`` — a plain
``pytest tests/jobs/test_transform_gate.py`` collects this module and reports it
SKIPPED (never errors), so it is safe in the default suite.

Unlike ``tests/services/test_ingestion_worker.py`` (which fakes the DB entirely),
this drives the REAL worker transform gate against the REAL local
``warehouse_state`` singleton + jobs engine — but with ``run_all`` MONKEYPATCHED
so it NEVER executes SQL, NEVER rebuilds cubes, and NEVER truncates raw
(STOP conditions §11.3). The empty-raw floor is exercised by STUBBING
``raw_total_count`` below the floor, not by emptying real raw.

Asserts the §10 item-2 gate contract against live ``warehouse_state``:
    * dirty flag (pre-existing) → transform invoked even with 0 rows landed;
    * transform exception → run ``failed`` + flag stays dirty + archive skipped;
    * empty-raw floor → REFUSE (stubbed count) → run ``failed``, dirty stays;
    * collapse-guard aborts on fact → 0 (monkeypatched runner drops it);
    * clear happens ONLY via the same-session transform/skip-clean path.

Safety: the module snapshots ``warehouse_state`` before each test and restores
it after, so the live singleton is left exactly as found. The monkeypatched
``run_all`` records invocations and flips an in-memory fake fact count; the real
``fact_student_submission`` table is only READ (count), never mutated.

Creds (R13): ``DATABASE_URL`` seeded from ``settings`` for the jobs engine;
``SUPABASE_*`` unused (no storage in this module).
"""

from __future__ import annotations

import os
from typing import Any, Optional
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_STORAGE_E2E") != "1",
    reason="transform-gate E2E (live warehouse_state); set RUN_STORAGE_E2E=1 to run",
)


# ── warehouse_state snapshot / restore ──────────────────────────────────────


async def _read_state(session) -> dict:
    row = (
        await session.execute(
            text(
                "SELECT transforms_dirty, dirty_token::text AS dirty_token, "
                "dirty_since, last_transform_run_id::text AS last_transform_run_id "
                "FROM warehouse_state WHERE id = 1"
            )
        )
    ).first()
    return dict(row._mapping) if row else {}


async def _set_state(
    session, *, dirty: bool, dirty_token: Optional[str]
) -> None:
    await session.execute(
        text(
            "UPDATE warehouse_state "
            "SET transforms_dirty = :d, dirty_token = CAST(:tok AS UUID), "
            "dirty_since = CASE WHEN :d THEN now() ELSE NULL END "
            "WHERE id = 1"
        ),
        {"d": dirty, "tok": dirty_token},
    )


@pytest.fixture
async def warehouse_snapshot():
    """Snapshot warehouse_state before the test, restore it after — the live
    singleton is left exactly as found."""
    from app.core.config import settings
    from app.jobs.db import dispose_engine, session_scope

    os.environ.setdefault("DATABASE_URL", settings.DATABASE_URL)

    async with session_scope() as session:
        before = await _read_state(session)
    try:
        yield
    finally:
        async with session_scope() as session:
            await session.execute(
                text(
                    "UPDATE warehouse_state "
                    "SET transforms_dirty = :d, dirty_token = CAST(:tok AS UUID), "
                    "dirty_since = :since, "
                    "last_transform_run_id = CAST(:ltr AS UUID) "
                    "WHERE id = 1"
                ),
                {
                    "d": before.get("transforms_dirty", False),
                    "tok": before.get("dirty_token"),
                    "since": before.get("dirty_since"),
                    "ltr": before.get("last_transform_run_id"),
                },
            )
        await dispose_engine()


@pytest.fixture(autouse=True)
def _transforms_on(monkeypatch: pytest.MonkeyPatch):
    """Enable the kill-switch so the gate proceeds past step 1 to the paths under
    test. ``run_all`` is monkeypatched per-test so NO real SQL runs regardless."""
    import app.services.ingestion_worker as worker_mod

    monkeypatch.setattr(
        worker_mod.settings, "INGESTION_TRANSFORMS_ENABLED", True
    )


def _worker():
    """A real IngestionWorker; the blob client is never used in these tests
    (they drive the transform batch directly, not landing)."""
    from app.services.ingestion_worker import IngestionWorker

    return IngestionWorker(
        worker_id=f"gate-{uuid4().hex[:8]}",
        heartbeat_seconds=3600,
        blob_client_factory=lambda: None,
    )


async def _current_state():
    from app.jobs.db import session_scope

    async with session_scope() as session:
        return await _read_state(session)


# ── 1. dirty flag → transform invoked even with 0 rows landed ───────────────


async def test_pre_dirty_zero_rows_invokes_transform(
    warehouse_snapshot, monkeypatch: pytest.MonkeyPatch
):
    """rows_inserted==0 but a PRE-EXISTING dirty flag (owned by someone else)
    forces a transform pass — closing the permanent-staleness hole (F27)."""
    import app.services.ingestion_worker as worker_mod
    from app.jobs.db import session_scope

    calls = {"n": 0}
    fake_fact = {"pre": 100, "post": 100}

    async def _fake_run_all(session: Any = None):  # noqa: ARG001
        calls["n"] += 1
        return {}

    # The gate reads real fact count; stub it so we don't depend on live data and
    # never trip the collapse-guard here.
    monkeypatch.setattr(worker_mod, "run_transformations", _fake_run_all)
    monkeypatch.setattr(
        worker_mod.IngestionWorker,
        "_fact_count",
        staticmethod(lambda session: _make_fact(fake_fact)),
    )

    rid = str(uuid4())
    async with session_scope() as session:
        await _set_state(session, dirty=True, dirty_token=str(uuid4()))  # pre-dirty

    outcome = await _worker()._run_transform_gate(rid, rows_this_batch=0)

    assert outcome == "applied", "pre-dirty + 0 rows must still transform"
    assert calls["n"] == 1
    state = await _current_state()
    assert state["transforms_dirty"] is False, "clear happens via the transform path"


# ── 2. transform exception → failed + dirty stays + archive skipped ─────────


async def test_transform_exception_marks_failed_and_leaves_dirty(
    warehouse_snapshot, monkeypatch: pytest.MonkeyPatch
):
    """A ``run_all`` exception surfaces from the gate; ``_transform_batch`` marks
    the clean landed run ``failed`` and the dirty flag is LEFT set (self-heals).
    Archive is a landing-phase concern that never runs here (batch = transform
    only), i.e. no post-failure archive is attempted."""
    import app.services.ingestion_worker as worker_mod
    from app.jobs.db import session_scope

    async def _boom(session: Any = None):  # noqa: ARG001
        raise RuntimeError("transform boom")

    monkeypatch.setattr(worker_mod, "run_transformations", _boom)
    monkeypatch.setattr(
        worker_mod.IngestionWorker,
        "_fact_count",
        staticmethod(lambda session: _make_fact({"pre": 100, "post": 100})),
    )

    rid = str(uuid4())
    async with session_scope() as session:
        await _set_state(session, dirty=True, dirty_token=str(uuid4()))

    landed = [{"run_id": rid, "short_name": "Athenian",
               "rows_inserted": 500, "error_count": 0}]

    marks: list = []
    _capture_marks(monkeypatch, worker_mod, marks)

    await _worker()._transform_batch(landed)

    assert (rid, "failed") in marks, "transform failure must fail the run"
    assert (rid, "succeeded") not in marks
    state = await _current_state()
    assert state["transforms_dirty"] is True, "dirty must survive a failed transform"


# ── 3. empty-raw floor → REFUSE (stubbed count, real raw untouched) ─────────


async def test_empty_raw_floor_refuses(
    warehouse_snapshot, monkeypatch: pytest.MonkeyPatch
):
    """raw below the floor → gate RAISES (refusal). Stubbed via
    ``raw_total_count`` — real raw is NEVER truncated."""
    import app.services.ingestion_worker as worker_mod
    from app.jobs.db import session_scope
    from app.repositories.ingestion_run_repository import IngestionRunRepository

    ran = {"n": 0}

    async def _fake_run_all(session: Any = None):  # noqa: ARG001
        ran["n"] += 1
        return {}

    monkeypatch.setattr(worker_mod, "run_transformations", _fake_run_all)

    # Stub the total-raw count BELOW the floor without touching real raw.
    async def _fake_raw_total(self) -> int:  # noqa: ARG001
        return 0

    monkeypatch.setattr(
        IngestionRunRepository, "raw_total_count", _fake_raw_total
    )

    rid = str(uuid4())
    async with session_scope() as session:
        await _set_state(session, dirty=True, dirty_token=str(uuid4()))  # pre-dirty

    with pytest.raises(RuntimeError, match="raw layer empty/below floor"):
        # rows_this_batch>0 so we bypass skip-clean and hit the floor preflight.
        await _worker()._run_transform_gate(rid, rows_this_batch=500)

    assert ran["n"] == 0, "refusal must not run transforms"
    state = await _current_state()
    assert state["transforms_dirty"] is True, "dirty must survive a refusal"


# ── 4. collapse-guard aborts on fact → 0 ────────────────────────────────────


async def test_collapse_guard_aborts_on_fact_zero(
    warehouse_snapshot, monkeypatch: pytest.MonkeyPatch
):
    """fact_pre>0 and post==0 (a bad rebuild) → gate RAISES so the txn rolls back
    and old cubes survive; the flag is NOT cleared."""
    import app.services.ingestion_worker as worker_mod
    from app.jobs.db import session_scope

    fact = {"value": 100}  # pre-count

    async def _wipe(session: Any = None):  # noqa: ARG001
        fact["value"] = 0  # the "rebuild" wipes the fact — the bug we catch
        return {}

    monkeypatch.setattr(worker_mod, "run_transformations", _wipe)
    monkeypatch.setattr(
        worker_mod.IngestionWorker,
        "_fact_count",
        staticmethod(lambda session: _make_fact_dynamic(fact)),
    )

    rid = str(uuid4())
    async with session_scope() as session:
        await _set_state(session, dirty=True, dirty_token=str(uuid4()))

    with pytest.raises(RuntimeError, match="collapse-guard"):
        await _worker()._run_transform_gate(rid, rows_this_batch=500)

    state = await _current_state()
    assert state["transforms_dirty"] is True, (
        "collapse-guard rollback must leave the flag dirty"
    )


# ── 5. clear ONLY via same-session (skip-clean) path ────────────────────────


async def test_skip_clean_clears_only_when_owns_token_zero_rows(
    warehouse_snapshot, monkeypatch: pytest.MonkeyPatch
):
    """0 rows + OWNS the current dirty token → clear WITHOUT transforming
    (skip-clean). No ``run_all`` call; the flag is cleared through the gate's own
    same-session path, not any external mutation."""
    import app.services.ingestion_worker as worker_mod
    from app.jobs.db import session_scope

    ran = {"n": 0}

    async def _fake_run_all(session: Any = None):  # noqa: ARG001
        ran["n"] += 1
        return {}

    monkeypatch.setattr(worker_mod, "run_transformations", _fake_run_all)

    rid = str(uuid4())
    async with session_scope() as session:
        await _set_state(session, dirty=True, dirty_token=rid)  # driver owns it

    outcome = await _worker()._run_transform_gate(rid, rows_this_batch=0)

    assert outcome == "skip_clean"
    assert ran["n"] == 0, "skip-clean must NOT transform"
    state = await _current_state()
    assert state["transforms_dirty"] is False, "own-token skip-clean clears the flag"
    assert state["last_transform_run_id"] == rid, "clear records the driver run_id"


# ── Small helpers for stubbing the fact count coroutine ─────────────────────


def _make_fact(fake: dict):
    """Return an awaitable resolving to the ``post`` fact count (or ``pre`` on
    first read). Used where the count is constant across pre/post."""
    async def _coro():
        return fake.get("post", fake.get("pre", 1))

    return _coro()


def _make_fact_dynamic(fact: dict):
    """Return an awaitable resolving to the CURRENT ``fact['value']`` — so a
    monkeypatched runner that mutates ``fact['value']`` is observed by the
    post-count read (drives the collapse-guard)."""
    async def _coro():
        return fact["value"]

    return _coro()


def _capture_marks(monkeypatch, worker_mod, sink: list) -> None:
    """Redirect ``IngestionWorker._mark`` to record (run_id, status) in ``sink``
    without writing to the real ``ingestion_runs`` table (these synthetic run_ids
    have no row)."""
    async def _fake_mark(self, run_id, status, details=None):  # noqa: ARG001
        sink.append((run_id, status))

    monkeypatch.setattr(worker_mod.IngestionWorker, "_mark", _fake_mark)
