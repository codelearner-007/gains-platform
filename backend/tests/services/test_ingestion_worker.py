"""Durable ingestion worker tests (HARDENING_PLAN §9 Wave 2 Agent C).

These drive the REAL worker code (``_land_run`` / ``_transform_batch`` /
``_run_transform_gate`` / ``_archive``) with every DB touch redirected to an
in-memory fake — so NO real transforms run and raw is NEVER truncated
(STOP conditions §11.3):

    * ``worker_mod.session_scope`` is monkeypatched to yield a ``FakeSession``
      that interprets the small set of SQL statements the worker issues
      (advisory lock, ``SET statement_timeout``, fact count, dirty-token read,
      warehouse dirty set/clear, run mark, school resolution) against in-memory
      state. It executes NO SQL against the real database.
    * ``run_transformations`` (transformations.run_all) is monkeypatched to a
      recorder that flips the fake fact count — it never opens a connection.
    * ``run_ingestion`` is monkeypatched to return a synthetic ``IngestSummary``.

The empty-raw floor is exercised by STUBBING ``raw_student_submission`` count
below the floor, not by emptying real raw. The collapse-guard is exercised by
having the fake transform runner leave the fake fact at 0 after a positive
pre-count.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

import app.services.ingestion_worker as worker_mod
from app.jobs.blob_client import BlobInfo
from app.jobs.ingest_schoology import IngestSummary
from app.services.ingestion_worker import (
    IngestionWorker,
    _extract_failed_run_ids,
    _extract_pruned_subjects,
)
from app.transformations.runner import ScopeReport, TransformResult

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ── In-memory warehouse the FakeSession reads/writes ────────────────────────


class FakeWarehouse:
    """The tiny slice of DB state the worker touches during a batch."""

    def __init__(self) -> None:
        self.dirty = False
        self.dirty_token: Optional[str] = None
        self.raw_total = 5000  # above the default floor (1000)
        # fact count: first read = pre, later reads = post (run_all flips it).
        self.fact = 100
        # Recorded run-status marks: list of (run_id, status, details_json).
        self.marks: List[tuple[str, str, Optional[str]]] = []
        # Recorded dirty-flag transitions for assertions.
        self.set_dirty: List[str] = []
        self.cleared: List[str] = []
        # school_id -> short_name resolution table.
        self.schools: Dict[str, Optional[str]] = {}
        # Prior-crash 'landed' run_ids the ``_scope_run_ids`` sweep folds in
        # (SELECT run_id::text FROM ingestion_runs WHERE status='landed'). Empty
        # by default so a batch's scope == its own ``landed`` list.
        self.landed_run_ids: List[str] = []
        # ``_post_commit_maintenance`` calls recorded as their ``purge`` arg (the
        # autouse fixture stubs the method so no real engine/VACUUM is touched).
        self.post_commit: List[bool] = []


class _Result:
    def __init__(self, rows: List[Any]) -> None:
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one(self):
        return self._rows[0][0]

    def all(self):
        # ``_scope_run_ids`` reads the swept 'landed' set via ``.all()``.
        return self._rows


class _Row(tuple):
    """A tuple that also exposes ._mapping-free positional access (worker uses
    row[0] only)."""


class FakeSession:
    """Interprets the worker's SQL against a ``FakeWarehouse`` — no real DB."""

    def __init__(self, wh: FakeWarehouse) -> None:
        self.wh = wh

    async def execute(self, statement: Any, params: Optional[dict] = None) -> _Result:
        sql = str(statement).lower()
        p = params or {}

        if "pg_advisory_xact_lock" in sql:
            return _Result([])
        if "set statement_timeout" in sql:
            return _Result([])
        if "count(*) from fact_student_submission" in sql:
            row = _Row((self.wh.fact,))
            return _Result([row])
        if "raw_student_submission" in sql and "count(*)" in sql:
            # Matches BOTH shapes of the empty-raw floor probe: the unbounded
            # `count(*) FROM raw_student_submission` and the bounded probe
            # `count(*) FROM (SELECT 1 FROM raw_student_submission LIMIT :cap) t`.
            # Matching only the unbounded literal silently returned an empty
            # result for the bounded form, so the gate raised and every
            # transform-path assertion in this module tested the failure branch.
            cap = p.get("cap")
            total = self.wh.raw_total if cap is None else min(self.wh.raw_total, cap)
            return _Result([_Row((total,))])
        if "dirty_token" in sql and "select" in sql:
            tok = self.wh.dirty_token if self.wh.dirty else None
            return _Result([_Row((tok,))])
        # ``_scope_run_ids`` sweep of prior-crash 'landed' runs.
        if "run_id::text from ingestion_runs" in sql and "status = 'landed'" in sql:
            return _Result([_Row((rid,)) for rid in self.wh.landed_run_ids])
        # ``warehouse_dirty()`` read (re-drive path).
        if "transforms_dirty from" in sql and "select" in sql:
            return _Result([_Row((self.wh.dirty,))])
        if "short_name from schools" in sql:
            sid = p.get("sid")
            name = self.wh.schools.get(sid)
            return _Result([_Row((name,))] if name is not None else [])
        # warehouse_state UPDATE (set dirty / clear)
        if "update public.warehouse_state" in sql or "update warehouse_state" in sql:
            if "transforms_dirty = true" in sql:
                self.wh.dirty = True
                self.wh.dirty_token = p.get("token")
                self.wh.set_dirty.append(p.get("token"))
            elif "transforms_dirty = false" in sql:
                self.wh.dirty = False
                self.wh.dirty_token = None
                self.wh.cleared.append(p.get("rid"))
            return _Result([])
        # ingestion_runs mark UPDATE
        if "update public.ingestion_runs" in sql:
            # crude status extract from the bound param
            self.wh.marks.append((p.get("rid"), p.get("status"), p.get("details")))
            return _Result([])
        return _Result([])


class FakeBlobClient:
    """In-memory blob client: path→last_modified map + a move log."""

    def __init__(self, files: Optional[Dict[str, datetime]] = None) -> None:
        self.files: Dict[str, datetime] = dict(files or {})
        self.moves: List[tuple[str, str]] = []

    def list_files(self, school_root: str) -> List[BlobInfo]:  # noqa: ARG002
        return [
            BlobInfo(path=p, last_modified=m, size_bytes=1)
            for p, m in self.files.items()
        ]

    def download(self, blob_path: str, school_root: str) -> bytes:  # noqa: ARG002
        return b""

    def move(self, from_key: str, to_key: str) -> None:
        self.moves.append((from_key, to_key))


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def wh() -> FakeWarehouse:
    return FakeWarehouse()


@pytest.fixture(autouse=True)
def _patch_db(monkeypatch: pytest.MonkeyPatch, wh: FakeWarehouse) -> None:
    """Redirect session_scope + dispose_engine + transformations + ingest so the
    worker never touches a real DB and never runs real transforms."""

    @asynccontextmanager
    async def _fake_scope():
        yield FakeSession(wh)

    async def _noop_dispose() -> None:
        return None

    async def _default_run_all(
        session: Any = None, scope_run_ids: Any = None
    ) -> dict:  # noqa: ARG001
        return {}

    async def _default_run_ingestion(**_kw: Any) -> IngestSummary:
        return IngestSummary(files_seen=0)

    async def _fake_post_commit(self, *, purge: bool) -> None:  # noqa: ANN001, ARG001
        # Record the purge decision; NEVER touch the real jobs engine / VACUUM.
        wh.post_commit.append(purge)

    monkeypatch.setattr(worker_mod, "session_scope", _fake_scope)
    monkeypatch.setattr(worker_mod, "dispose_engine", _noop_dispose)
    monkeypatch.setattr(worker_mod, "run_transformations", _default_run_all)
    monkeypatch.setattr(worker_mod, "run_ingestion", _default_run_ingestion)
    monkeypatch.setattr(
        worker_mod.IngestionWorker, "_post_commit_maintenance", _fake_post_commit
    )


def _worker(blob: Optional[FakeBlobClient] = None) -> IngestionWorker:
    """Real IngestionWorker with a fast heartbeat disabled and a fake blob."""
    b = blob or FakeBlobClient()
    w = IngestionWorker(
        worker_id="test-worker",
        heartbeat_seconds=3600,  # never fires within a test
        blob_client_factory=lambda: b,
    )
    return w


def _run_marks(wh: FakeWarehouse) -> set[tuple[str, str]]:
    return {(rid, st) for rid, st, _ in wh.marks}


# ── Transform-gate tests (§5) ───────────────────────────────────────────────


async def test_transform_runs_on_dirty_even_with_zero_rows(
    monkeypatch: pytest.MonkeyPatch, wh: FakeWarehouse
):
    """0 rows landed but a PRE-EXISTING dirty flag (prior crash) → transforms MUST
    run (closes the permanent-staleness hole, F27)."""
    monkeypatch.setattr(worker_mod.settings, "INGESTION_TRANSFORMS_ENABLED", True)
    ran = {"n": 0}

    async def _run_all(session: Any = None, scope_run_ids: Any = None) -> dict:  # noqa: ARG001
        ran["n"] += 1
        return {"fact": 1}

    monkeypatch.setattr(worker_mod, "run_transformations", _run_all)

    rid = str(uuid4())
    wh.dirty = True
    wh.dirty_token = str(uuid4())  # owned by someone else → pre-dirty
    wh.fact = 100

    w = _worker()
    landed = [{"run_id": rid, "short_name": "Athenian",
               "rows_inserted": 0, "error_count": 0}]
    await w._transform_batch(landed)

    assert ran["n"] == 1
    assert (rid, "succeeded") in _run_marks(wh)
    assert rid in wh.cleared and wh.dirty is False


async def test_skip_clean_when_owns_token_and_zero_rows(
    monkeypatch: pytest.MonkeyPatch, wh: FakeWarehouse
):
    """0 rows + owns the current dirty token → clear WITHOUT transforming."""
    monkeypatch.setattr(worker_mod.settings, "INGESTION_TRANSFORMS_ENABLED", True)
    ran = {"n": 0}

    async def _run_all(session: Any = None, scope_run_ids: Any = None) -> dict:  # noqa: ARG001
        ran["n"] += 1
        return {}

    monkeypatch.setattr(worker_mod, "run_transformations", _run_all)

    rid = str(uuid4())
    wh.dirty = True
    wh.dirty_token = rid  # driver run owns it

    w = _worker()
    landed = [{"run_id": rid, "short_name": "Athenian",
               "rows_inserted": 0, "error_count": 0}]
    await w._transform_batch(landed)

    assert ran["n"] == 0, "skip-clean must not transform"
    assert rid in wh.cleared and wh.dirty is False
    assert (rid, "succeeded") in _run_marks(wh)


async def test_refuse_on_empty_raw_floor_unscoped(
    monkeypatch: pytest.MonkeyPatch, wh: FakeWarehouse
):
    """Raw below the floor → REFUSE (RAISE) on an UNSCOPED rebuild. The floor is a
    total-raw guard for a would-be full rebuild only; the gate is driven directly
    with ``scope_run_ids=[]`` (empty scope == unscoped) since a worker batch that
    landed a run always carries a non-empty scope. Stubbed below-floor; real raw
    untouched."""
    monkeypatch.setattr(worker_mod.settings, "INGESTION_TRANSFORMS_ENABLED", True)
    wh.raw_total = 0  # simulate prod raw=0 WITHOUT truncating real raw
    wh.dirty = True
    wh.dirty_token = str(uuid4())  # pre-dirty (not this batch's)

    rid = str(uuid4())
    w = _worker()
    with pytest.raises(RuntimeError, match="raw layer empty/below floor"):
        await w._run_transform_gate(rid, rows_this_batch=500, scope_run_ids=[])

    assert wh.dirty is True, "dirty must survive a refused transform"
    assert rid not in wh.cleared


async def test_scoped_path_bypasses_empty_raw_floor(
    monkeypatch: pytest.MonkeyPatch, wh: FakeWarehouse
):
    """The floor is BYPASSED on the scoped path (non-empty ``scope_run_ids``): a
    lean prod box (raw≈20, below the 1000 floor) must still apply the scoped
    subjects — safety is the subject-grain §HISTORIC guard, not a global row
    floor. So a batch with raw below the floor transforms + succeeds."""
    monkeypatch.setattr(worker_mod.settings, "INGESTION_TRANSFORMS_ENABLED", True)
    ran = {"n": 0}

    async def _run_all(session: Any = None, scope_run_ids: Any = None) -> dict:  # noqa: ARG001
        ran["n"] += 1
        return {}

    monkeypatch.setattr(worker_mod, "run_transformations", _run_all)

    wh.raw_total = 20  # below the 1000 floor, like a lean prod box
    wh.fact = 100
    wh.dirty = True
    wh.dirty_token = str(uuid4())

    rid = str(uuid4())
    w = _worker()
    landed = [{"run_id": rid, "short_name": "Athenian",
               "rows_inserted": 20, "error_count": 0}]
    await w._transform_batch(landed)

    assert ran["n"] == 1, "scoped path must transform despite raw below the floor"
    assert (rid, "succeeded") in _run_marks(wh)
    assert rid in wh.cleared


async def test_collapse_guard_aborts_on_fact_zero(
    monkeypatch: pytest.MonkeyPatch, wh: FakeWarehouse
):
    """fact_pre>0 and post==0 → collapse-guard raises → failed, dirty stays."""
    monkeypatch.setattr(worker_mod.settings, "INGESTION_TRANSFORMS_ENABLED", True)

    async def _run_all(session: Any = None, scope_run_ids: Any = None) -> dict:  # noqa: ARG001
        # The rebuild "wipes" the fact to 0 (a bug we must catch).
        wh.fact = 0
        return {}

    monkeypatch.setattr(worker_mod, "run_transformations", _run_all)

    wh.fact = 100  # positive pre-count
    wh.dirty = True
    wh.dirty_token = str(uuid4())

    rid = str(uuid4())
    w = _worker()
    landed = [{"run_id": rid, "short_name": "Athenian",
               "rows_inserted": 500, "error_count": 0}]
    await w._transform_batch(landed)

    assert (rid, "failed") in _run_marks(wh)
    assert wh.dirty is True
    assert rid not in wh.cleared


async def test_transform_failure_marks_failed_and_leaves_dirty(
    monkeypatch: pytest.MonkeyPatch, wh: FakeWarehouse
):
    """A transform exception → run failed + flag stays dirty (self-heals)."""
    monkeypatch.setattr(worker_mod.settings, "INGESTION_TRANSFORMS_ENABLED", True)

    async def _boom(session: Any = None, scope_run_ids: Any = None) -> dict:  # noqa: ARG001
        raise RuntimeError("transform boom")

    monkeypatch.setattr(worker_mod, "run_transformations", _boom)

    wh.fact = 100
    wh.dirty = True
    wh.dirty_token = str(uuid4())

    rid = str(uuid4())
    w = _worker()
    landed = [{"run_id": rid, "short_name": "Athenian",
               "rows_inserted": 500, "error_count": 0}]
    await w._transform_batch(landed)

    assert (rid, "failed") in _run_marks(wh)
    assert wh.dirty is True
    assert rid not in wh.cleared


async def test_kill_switch_leaves_landed_and_dirty(
    monkeypatch: pytest.MonkeyPatch, wh: FakeWarehouse
):
    """Kill-switch OFF (prod) → no transform; runs stay 'landed'; dirty stays."""
    monkeypatch.setattr(worker_mod.settings, "INGESTION_TRANSFORMS_ENABLED", False)
    ran = {"n": 0}

    async def _run_all(session: Any = None, scope_run_ids: Any = None) -> dict:  # noqa: ARG001
        ran["n"] += 1
        return {}

    monkeypatch.setattr(worker_mod, "run_transformations", _run_all)

    rid = str(uuid4())
    wh.dirty = True
    wh.dirty_token = rid

    w = _worker()
    landed = [{"run_id": rid, "short_name": "Athenian",
               "rows_inserted": 500, "error_count": 0}]
    await w._transform_batch(landed)

    assert ran["n"] == 0
    assert all(st != "succeeded" for _, st in _run_marks(wh))
    assert wh.dirty is True


# ── Landing / archive tests (§4 / §6) ───────────────────────────────────────


async def test_empty_school_run_fails(wh: FakeWarehouse):
    """F9: a claimed run whose school does not resolve → failed, not silent."""
    # school_id present but not in the resolution table → _short_name_for None.
    rid = str(uuid4())
    w = _worker()
    result = await w._land_run({"run_id": rid, "school_id": "unknown-sid"})

    assert result is None
    assert (rid, "failed") in _run_marks(wh)


async def test_archive_skips_changed_key(wh: FakeWarehouse):
    """A key re-uploaded mid-run (newer last_modified) is left LIVE, not archived."""
    blob = FakeBlobClient({"a.csv": _T0, "b.csv": _T0})
    w = _worker(blob)
    snapshot = [
        BlobInfo(path="a.csv", last_modified=_T0, size_bytes=1),
        BlobInfo(path="b.csv", last_modified=_T0, size_bytes=1),
    ]
    blob.files["a.csv"] = _T0 + timedelta(minutes=5)  # re-uploaded newer mid-run

    w._archive(blob, "Athenian", str(uuid4()), snapshot)

    moved = {frm for frm, _ in blob.moves}
    assert "Athenian/b.csv" in moved, "unchanged key must archive"
    assert "Athenian/a.csv" not in moved, "re-uploaded key must stay live"


async def test_clean_landing_sets_dirty_archives_and_returns_context(
    monkeypatch: pytest.MonkeyPatch, wh: FakeWarehouse
):
    """Clean landing: dirty set BEFORE landing, snapshot keys archived, context
    returned for the batch transform pass."""
    wh.schools = {"sid-1": "Athenian"}

    async def _good(**_kw: Any) -> IngestSummary:
        return IngestSummary(
            files_seen=2, files_processed=2, files_skipped=0,
            error_count=0, rows_inserted=42,
        )

    monkeypatch.setattr(worker_mod, "run_ingestion", _good)

    rid = str(uuid4())
    blob = FakeBlobClient({"x.csv": _T0, "y.csv": _T0})
    w = _worker(blob)
    result = await w._land_run({"run_id": rid, "school_id": "sid-1"})

    assert result == {
        "run_id": rid, "short_name": "Athenian",
        "rows_inserted": 42, "error_count": 0,
    }
    assert wh.set_dirty == [rid], "dirty set BEFORE landing, token=run_id"
    assert len(blob.moves) == 2
    assert all(to.startswith(f"processed/Athenian/{rid}/") for _, to in blob.moves)


async def test_invariant_violation_fails_run_no_archive(
    monkeypatch: pytest.MonkeyPatch, wh: FakeWarehouse
):
    """files_seen != processed+skipped+errors → run failed, no archive (F4 belt)."""
    wh.schools = {"sid-1": "Athenian"}

    async def _bad(**_kw: Any) -> IngestSummary:
        return IngestSummary(
            files_seen=3, files_processed=1, files_skipped=0, error_count=0
        )

    monkeypatch.setattr(worker_mod, "run_ingestion", _bad)

    rid = str(uuid4())
    blob = FakeBlobClient({"a.csv": _T0})
    w = _worker(blob)
    result = await w._land_run({"run_id": rid, "school_id": "sid-1"})

    assert result is None
    assert (rid, "failed") in _run_marks(wh)
    assert blob.moves == []


async def test_errored_landing_leaves_files_live(
    monkeypatch: pytest.MonkeyPatch, wh: FakeWarehouse
):
    """error_count>0 → no archive (source files stay live for a fresh re-ingest).
    But once the batch transform APPLIES that run's subjects, the run is promoted
    to ``succeeded`` with a ``landing_note`` (#4/#8) — leaving it 'landed' would
    re-fold + re-DELETE/INSERT it on every future drain forever."""
    wh.schools = {"sid-1": "Athenian"}

    async def _err(**_kw: Any) -> IngestSummary:
        return IngestSummary(
            files_seen=2, files_processed=1, files_skipped=0,
            error_count=1, rows_inserted=10,
        )

    monkeypatch.setattr(worker_mod, "run_ingestion", _err)

    rid = str(uuid4())
    blob = FakeBlobClient({"x.csv": _T0, "y.csv": _T0})
    w = _worker(blob)
    result = await w._land_run({"run_id": rid, "school_id": "sid-1"})

    assert result is not None and result["error_count"] == 1
    assert blob.moves == [], "errored landing must not archive"

    # The batch pass now PROMOTES an errored landing whose subjects applied to
    # succeeded, carrying a landing_note (else it is re-folded forever).
    monkeypatch.setattr(worker_mod.settings, "INGESTION_TRANSFORMS_ENABLED", True)
    wh.fact = 100
    wh.dirty = True
    wh.dirty_token = str(uuid4())
    await w._transform_batch([result])

    assert (rid, "succeeded") in _run_marks(wh)
    # ...and the success carries a landing_note recording the file errors.
    succeeded_details = [
        det for r, st, det in wh.marks if r == rid and st == "succeeded"
    ]
    assert succeeded_details and "landing_note" in (succeeded_details[0] or "")


# ── _extract_failed_run_ids / _extract_pruned_subjects (pure, DB-free) #7/#14 ─


def _scope(run_subjects, survivors, *, noop_reason=None) -> TransformResult:
    """A ``TransformResult`` carrying a faithful ``ScopeReport`` — the exact shape
    ``run_all`` returns on a scoped run and the worker's extractors read."""
    survivor_set = frozenset(survivors)
    all_subjects = {s for subs in run_subjects.values() for s in subs}
    tr = TransformResult()
    tr.scope = ScopeReport(
        run_subjects={r: frozenset(s) for r, s in run_subjects.items()},
        groups=(),
        survivors=survivor_set,
        failed_subjects=frozenset(all_subjects - survivor_set),
        noop_reason=noop_reason,
    )
    return tr


def test_extract_failed_run_ids_all_survive_is_empty() -> None:
    """Every produced subject survived → no run failed."""
    tr = _scope({"r1": {"s1", "s2"}}, {"s1", "s2"})
    assert _extract_failed_run_ids(tr) == []


def test_extract_failed_run_ids_run_fully_pruned() -> None:
    """A run whose only subject was pruned is failed."""
    tr = _scope({"r1": {"s1"}}, set())
    assert _extract_failed_run_ids(tr) == ["r1"]


def test_extract_failed_run_ids_partial_multigroup_run_is_failed() -> None:
    """Any-pruned semantics: a run contributing to BOTH a surviving group and a
    pruned group (run_subjects ⊄ survivors) is failed so its raw is retained for a
    full re-scrape — even though its surviving subject's data WAS applied."""
    tr = _scope({"r1": {"s1", "s2"}}, {"s1"})  # s2 pruned
    assert _extract_failed_run_ids(tr) == ["r1"]


def test_extract_failed_run_ids_none_scope_is_empty() -> None:
    """Full/empty-scope mode: ``.scope`` is None → no run failed (byte-identical
    to today's unscoped promotion)."""
    assert _extract_failed_run_ids(TransformResult()) == []
    assert _extract_failed_run_ids({}) == []


def test_extract_failed_run_ids_malformed_shape_is_empty() -> None:
    """A defensive no-crash: an unrecognized scope shape yields [] (no run wrongly
    failed)."""

    class _Bad:
        scope = object()  # has .scope but no run_subjects/survivors

    assert _extract_failed_run_ids(_Bad()) == []


def test_extract_pruned_subjects_maps_run_to_dropped_subjects() -> None:
    """The operator-facing map: pruned run → the subject_ids it lost (sorted)."""
    tr = _scope({"r1": {"s1", "s2"}, "r2": {"s3"}}, {"s1", "s3"})
    assert _extract_pruned_subjects(tr) == {"r1": ["s2"]}


def test_extract_pruned_subjects_none_scope_is_empty() -> None:
    assert _extract_pruned_subjects(TransformResult()) == {}


# ── _transform_batch marking over the FULL folded set (b)/(c) #7/#8 ──────────


async def test_transform_batch_marks_full_folded_set(
    monkeypatch: pytest.MonkeyPatch, wh: FakeWarehouse
):
    """The transform folds this batch's runs ∪ every prior-crash 'landed' run
    (``_scope_run_ids``) and must mark that WHOLE set (#4/#8): a swept run whose
    subject survived → succeeded; a swept run whose subject was pruned → failed
    (raw retained). Here R1 is the fresh landed run (survives) and R2 is a swept
    prior-'landed' run (pruned)."""
    monkeypatch.setattr(worker_mod.settings, "INGESTION_TRANSFORMS_ENABLED", True)
    r1, r2 = str(uuid4()), str(uuid4())

    async def _run_all(session: Any = None, scope_run_ids: Any = None):  # noqa: ARG001
        # R1 survives (s1 ∈ survivors); R2 pruned (s2 ∉ survivors).
        return _scope({r1: {"s1"}, r2: {"s2"}}, {"s1"})

    monkeypatch.setattr(worker_mod, "run_transformations", _run_all)

    wh.fact = 100
    wh.dirty = True
    wh.dirty_token = str(uuid4())
    wh.landed_run_ids = [r2]  # a swept prior-'landed' run, not in this batch

    w = _worker()
    landed = [{"run_id": r1, "short_name": "Athenian",
               "rows_inserted": 500, "error_count": 0}]
    await w._transform_batch(landed)

    marks = _run_marks(wh)
    assert (r1, "succeeded") in marks, "surviving run promoted"
    assert (r2, "failed") in marks, "swept, pruned run marked failed"
    assert (r2, "succeeded") not in marks, "pruned run's raw must be retained"
    # A real applied transform runs post-commit maintenance (purge decision made).
    assert wh.post_commit, "applied transform must run post-commit maintenance"
    # The failed run names the assessment(s) to re-scrape.
    r2_failed = [det for r, st, det in wh.marks if r == r2 and st == "failed"]
    assert r2_failed and "s2" in (r2_failed[0] or "")


async def test_transform_batch_qd_only_fails_and_retains_raw(
    monkeypatch: pytest.MonkeyPatch, wh: FakeWarehouse
):
    """A QD-only batch (question-data raw, ZERO student submissions) built nothing:
    every folded run is marked ``failed`` (transforms_applied stays false → the
    purge RETAINS their raw for a re-scrape / full rebuild) and NO post-commit
    purge/VACUUM runs (#5/#9/#12)."""
    monkeypatch.setattr(worker_mod.settings, "INGESTION_TRANSFORMS_ENABLED", True)
    rid = str(uuid4())

    async def _run_all(session: Any = None, scope_run_ids: Any = None):  # noqa: ARG001
        # The QD-only sentinel: no subjects, nothing built.
        return _scope({}, set(), noop_reason="qd_only")

    monkeypatch.setattr(worker_mod, "run_transformations", _run_all)

    wh.fact = 100
    wh.dirty = True
    wh.dirty_token = str(uuid4())

    w = _worker()
    landed = [{"run_id": rid, "short_name": "Athenian",
               "rows_inserted": 5, "error_count": 0}]  # QD rows, no submissions
    await w._transform_batch(landed)

    marks = _run_marks(wh)
    assert (rid, "failed") in marks
    assert (rid, "succeeded") not in marks
    assert wh.post_commit == [], "QD-only no-op must not purge/VACUUM"
    failed_details = [det for r, st, det in wh.marks if r == rid and st == "failed"]
    assert failed_details and "question-data" in (failed_details[0] or "")
