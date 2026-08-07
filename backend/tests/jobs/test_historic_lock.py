"""Proof tests for the historic-lock (MASTER_PLAN §LOCK / §TEST).

Proves all THREE lock layers plus their inertness, without ever destroying real
data:

    1. DB backstop (migration ``20260723100000_historic_lock.sql``):
       * BEFORE DELETE row trigger blocks a DELETE that would erase a locked
         (school_id, session) slice;
       * BEFORE TRUNCATE statement trigger refuses a full-table TRUNCATE while
         ANY lock exists (protecting EVERY year from a wipe).
    2. Runner SQL guard (``runner._assert_no_locked_truncate``): while any lock
       exists it refuses a build whose files unscoped-TRUNCATE a session-bearing
       table, naming the offender; inert (no scan) when nothing is locked.
    3. Worker app guard (``IngestionWorker._land_run`` via
       ``_locked_target_session``): a run whose target session is locked is
       marked ``failed(...locked...)`` BEFORE any landing/ingest; inert when the
       session is not locked.

SAFETY CONTRACT (STRICT — see task spec):
    * A SYNTHETIC session ``'9999-99'`` is the ONLY session ever written to
      ``fact_student_submission``; a real session (2024-25 / 2025-26) is NEVER
      inserted, deleted, or locked.
    * Everything that touches ``fact_student_submission`` runs inside a
      transaction that is ALWAYS ROLLED BACK — no fact row is ever committed.
    * Any ``locked_sessions`` row inserted for the runner/worker layers (which
      use their own sessions and cannot see an uncommitted lock) is committed but
      deleted by EXACT key in a ``finally``, and only ever names ``'9999-99'`` —
      a real session is never left locked.
    * The runner/worker layers here PATCH the repo/guard return values rather
      than committing a real lock where a rollback would do, so no real transform
      or ingest ever runs.

The DB-trigger tests need the real local DB (that is the thing under test), so
this module is NOT env-gated; it connects via a throwaway per-test engine on the
app's ``DATABASE_URL`` (same ``postgres`` role the app uses). Superusers do not
bypass BEFORE triggers.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.repositories.locked_sessions_repository as lock_repo_mod
import app.services.ingestion_worker as worker_mod
from app.core.config import settings
from app.services.ingestion_worker import IngestionWorker
from app.transformations import runner as runner_mod

# The ONLY session label this module is ever allowed to write / lock. Chosen so
# it can never collide with a real year (2024-25 / 2025-26).
SYNTHETIC_SESSION = "9999-99"

# Guard: refuse to run at all if these ever point at a real year, so a future
# edit cannot accidentally arm the tests against production-shaped data.
assert SYNTHETIC_SESSION not in {"2024-25", "2025-26"}

# #24: the Layer-3 tests below use ``_fresh_db_session`` — they issue
# TRUNCATE/DELETE/INSERT against the app's ``DATABASE_URL`` (dev, 56322) and rely
# on transaction rollback + the installed trigger for safety. A default DB-free
# ``pytest`` run must NOT touch the dev DB, so they are gated behind
# ``RUN_DB_LOCK_TESTS=1`` (mirrors ``test_transform_gate.py``'s RUN_STORAGE_E2E
# gate). The Layer-1 (worker) and Layer-2 (runner-guard + helper) tests are
# DB-free (they fake/patch every DB touch) and stay UNGATED.
_db_lock = pytest.mark.skipif(
    os.environ.get("RUN_DB_LOCK_TESTS") != "1",
    reason="Layer-3 DB-trigger tests write to dev DB; set RUN_DB_LOCK_TESTS=1 to run",
)


# ── DB-session helpers ──────────────────────────────────────────────────────


@asynccontextmanager
async def _fresh_db_session() -> AsyncGenerator[AsyncSession, None]:
    """A DB session on a FRESH engine bound to THIS test's event loop.

    The app's global session manager caches a pool tied to the loop it was first
    used on; reusing it across pytest-asyncio's per-test loops raises
    "attached to a different loop". A throwaway engine per test sidesteps that,
    and it is disposed in ``finally``. Every caller rolls back — nothing commits.
    """
    url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url, poolclass=None)
    try:
        async with AsyncSession(engine) as session:
            yield session
    finally:
        await engine.dispose()


async def _a_real_school_id(session) -> str:
    """A real school_id to satisfy the locked_sessions FK. Read-only."""
    row = (await session.execute(text("SELECT school_id::text FROM schools LIMIT 1"))).first()
    assert row is not None, "no schools in local DB — cannot run lock proof"
    return row[0]


async def _insert_synthetic_fact_row(session, school_id: str) -> None:
    """Insert ONE synthetic fact row for (school_id, SYNTHETIC_SESSION).

    Copies an existing row's full column set via ``INSERT ... SELECT ... LIMIT
    1`` and overrides ``session`` to the sentinel and ``user_id_ques_id_stand``
    (the synthetic PK, whose md5 is the unique index) to a sentinel so there is
    no PK clash. MUST be called inside a transaction the caller rolls back.
    """
    await session.execute(
        text(
            """
            INSERT INTO fact_student_submission AS f
            SELECT
                'LOCKTEST-9999-99-SENTINEL'                AS user_id_ques_id_stand,
                src.school_id,
                src.user_uid, src.user_name, src.user_role_id, src.school_id_csv,
                src.course_nid, src.section_nid, src.section_code,
                src.item_id, src.item_name, src.first_access, src.latest_attempt,
                src.total_time, src.submission_grade, src.submission, src.question_id,
                :sess                                       AS session,
                src.assessment_type, src.subject, src.grade, src.section,
                src.file_name, src.position_number, src.sub_question,
                src.answer_submission, src.correct_answer, src.points_received,
                src.points_possible, src.user_id_ques_id, src.grade_id,
                src.assessment_id, src.subject_id, src.strand_id, src.standard,
                src.identifier
            FROM fact_student_submission src
            WHERE src.school_id = CAST(:sid AS UUID)
            LIMIT 1
            """
        ),
        {"sid": school_id, "sess": SYNTHETIC_SESSION},
    )


async def _insert_lock(session, school_id: str) -> None:
    """Insert a lock row for (school_id, SYNTHETIC_SESSION) in this txn."""
    await session.execute(
        text(
            """
            INSERT INTO locked_sessions (school_id, session, locked_by, reason)
            VALUES (CAST(:sid AS UUID), :sess, 'test_historic_lock', 'proof')
            """
        ),
        {"sid": school_id, "sess": SYNTHETIC_SESSION},
    )


# ── Layer 3: DB backstop ────────────────────────────────────────────────────


@_db_lock
async def test_db_trigger_blocks_delete_of_locked_synthetic_session() -> None:
    """Row DELETE guard: with no lock a DELETE of the synthetic slice succeeds;
    once the slice is locked the SAME DELETE is refused by the trigger. Whole
    thing rolls back — no fact row and no lock survive."""
    async with _fresh_db_session() as session:
        try:
            school_id = await _a_real_school_id(session)

            # locked_sessions empty for this slice → deleting the (0 real rows)
            # synthetic session succeeds (inert).
            await session.execute(
                text("DELETE FROM fact_student_submission WHERE session = :s"),
                {"s": SYNTHETIC_SESSION},
            )

            # Arm the lock: one synthetic fact row + a lock on its slice.
            await _insert_synthetic_fact_row(session, school_id)
            await _insert_lock(session, school_id)

            # Now the trigger must refuse the delete of the locked slice.
            with pytest.raises(DBAPIError) as exc:
                await session.execute(
                    text("DELETE FROM fact_student_submission WHERE session = :s"),
                    {"s": SYNTHETIC_SESSION},
                )
            assert "LOCKED" in str(exc.value).upper()
        finally:
            await session.rollback()  # nothing here ever commits


@_db_lock
async def test_db_trigger_refuses_truncate_while_any_lock_exists() -> None:
    """TRUNCATE guard: any lock (even on the synthetic session) makes a full
    ``TRUNCATE fact_student_submission`` raise — proving one lock protects EVERY
    year from a full wipe. Rolled back; the table is never actually truncated."""
    async with _fresh_db_session() as session:
        try:
            school_id = await _a_real_school_id(session)
            await _insert_lock(session, school_id)

            with pytest.raises(DBAPIError) as exc:
                await session.execute(text("TRUNCATE fact_student_submission"))
            assert "TRUNCATE refused" in str(exc.value)
        finally:
            await session.rollback()  # the TRUNCATE (had it run) is undone


@_db_lock
async def test_db_trigger_inert_when_no_locks() -> None:
    """Inertness: with locked_sessions EMPTY, a no-op DELETE (WHERE false)
    succeeds — the trigger is a pure pass-through. Rolled back."""
    async with _fresh_db_session() as session:
        try:
            # Sanity: this txn sees no locks (nothing inserted here).
            n = (await session.execute(text("SELECT count(*) FROM locked_sessions"))).scalar_one()
            assert n == 0
            # No-op delete must NOT raise.
            await session.execute(
                text("DELETE FROM fact_student_submission WHERE false")
            )
        finally:
            await session.rollback()


# ── Layer 2: runner SQL guard ───────────────────────────────────────────────


class _FakeLockRepo:
    """Stand-in for LockedSessionsRepository used by the runner guard. No DB."""

    def __init__(self, *, any_locked: bool) -> None:
        self._any = any_locked
        self.any_locked_calls = 0
        self.list_all_calls = 0

    async def any_locked(self) -> bool:
        self.any_locked_calls += 1
        return self._any

    async def list_all(self) -> List[Dict[str, Any]]:
        self.list_all_calls += 1
        # A synthetic locked label so the raised message can name it.
        return [{"school_id": "synthetic-school", "session": SYNTHETIC_SESSION}]


def _patch_runner_repo(monkeypatch, repo: _FakeLockRepo) -> None:
    """Make ``_assert_no_locked_truncate``'s lazy import yield our fake repo.

    The guard does ``from app.repositories.locked_sessions_repository import
    LockedSessionsRepository`` at call time, so we patch the name on the SOURCE
    module (not on ``runner``, which never binds it)."""
    monkeypatch.setattr(
        lock_repo_mod,
        "LockedSessionsRepository",
        lambda _session: repo,
        raising=True,
    )


async def test_runner_guard_blocks_unscoped_truncate_when_locked(monkeypatch) -> None:
    """With ``any_locked()`` → True, scanning the REAL TRANSFORMATIONS_ORDER in
    LEGACY-FULL mode (``scoped=False``) must raise, naming an offending
    top-level-TRUNCATE file. The surviving tripwire is the two staging files'
    bare ``TRUNCATE`` (fact/cube/dim TRUNCATEs are now DO-block-wrapped and
    statement-aware-skipped per §1c). No transforms run."""
    repo = _FakeLockRepo(any_locked=True)
    _patch_runner_repo(monkeypatch, repo)
    base = runner_mod._base_dir()

    with pytest.raises(RuntimeError) as exc:
        await runner_mod._assert_no_locked_truncate(
            session=object(), base=base, only_tag=None, scoped=False
        )

    msg = str(exc.value)
    assert "historic-lock" in msg
    assert "TRUNCATE" in msg
    # It must name a concrete offending .sql file from the real order.
    assert ".sql" in msg
    # The tripwire is the staging scratch file(s), not the DO-block-wrapped fact.
    assert "stg_" in msg
    assert repo.any_locked_calls == 1
    assert repo.list_all_calls == 1


async def test_runner_guard_blocks_staging_tag_when_locked_legacy(monkeypatch) -> None:
    """A locked env must refuse a legacy ``--tag staging`` rebuild: that tag still
    carries the bare top-level ``TRUNCATE`` of the two session-bearing staging
    tables (the surviving tripwire). Proven against the REAL order."""
    repo = _FakeLockRepo(any_locked=True)
    _patch_runner_repo(monkeypatch, repo)
    base = runner_mod._base_dir()

    with pytest.raises(RuntimeError) as exc:
        await runner_mod._assert_no_locked_truncate(
            session=object(), base=base, only_tag="staging", scoped=False
        )

    msg = str(exc.value)
    assert "historic-lock" in msg
    assert "TRUNCATE" in msg
    assert ".sql" in msg
    assert repo.any_locked_calls == 1


@pytest.mark.parametrize("only_tag", ["dimensions", "facts", "hash", "cubes"])
async def test_runner_guard_permits_derivation_tags_when_locked(monkeypatch, only_tag) -> None:
    """§1c relaxation (DO-NOT #14): with the DO-block idiom, a ``--tag facts`` /
    ``--tag cubes`` / ``--tag dimensions`` / ``--tag hash`` rebuild no longer
    contains a TOP-LEVEL TRUNCATE of a session-bearing/cube table — the fact and
    cube TRUNCATEs live inside ``DO $scope$`` bodies (skipped by the
    statement-aware scan) and the four rollup cubes use ``DELETE FROM``. Layer-2
    therefore does NOT refuse these tags; the §HISTORIC fingerprint guard and the
    DB-level TRUNCATE trigger remain the backstops. Proven against the REAL order.
    """
    repo = _FakeLockRepo(any_locked=True)
    _patch_runner_repo(monkeypatch, repo)
    base = runner_mod._base_dir()

    result = await runner_mod._assert_no_locked_truncate(
        session=object(), base=base, only_tag=only_tag, scoped=False
    )
    assert result is None  # locks exist, but this tag has no refused TRUNCATE
    assert repo.any_locked_calls == 1


async def test_runner_guard_permits_scoped_run_on_real_order_when_locked(monkeypatch) -> None:
    """A SCOPED run under a lock is ALLOWED (§1c): the only top-level TRUNCATEs on
    the real order are the two staging scratch tables, and ``scoped=True`` permits
    exactly those (they are per-run scratch, rebuilt every run). If a future edit
    reintroduces a top-level fact/cube TRUNCATE, this test flips red."""
    repo = _FakeLockRepo(any_locked=True)
    _patch_runner_repo(monkeypatch, repo)
    base = runner_mod._base_dir()

    result = await runner_mod._assert_no_locked_truncate(
        session=object(), base=base, only_tag=None, scoped=True
    )
    assert result is None
    assert repo.any_locked_calls == 1


async def test_runner_guard_inert_when_no_locks(monkeypatch) -> None:
    """With ``any_locked()`` → False the guard returns immediately WITHOUT
    scanning any files (inert fast-path)."""
    repo = _FakeLockRepo(any_locked=False)
    _patch_runner_repo(monkeypatch, repo)
    base = runner_mod._base_dir()

    # Spy that would fire if the guard tried to read any SQL file.
    read_calls: List[str] = []
    orig_read_text = Path.read_text

    def _spy_read_text(self, *a, **k):  # noqa: ANN001
        read_calls.append(str(self))
        return orig_read_text(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", _spy_read_text, raising=True)

    result = await runner_mod._assert_no_locked_truncate(
        session=object(), base=base, only_tag=None, scoped=False
    )
    assert result is None
    assert repo.any_locked_calls == 1
    assert read_calls == []  # inert: no file scanned


# ── Layer 2 (statement-aware helper): DB-free `_truncated_session_tables` ────


def test_truncated_session_tables_flags_real_staging_tripwire() -> None:
    """Unit sanity: the two REAL staging files each carry a top-level TRUNCATE of
    a session-bearing table — the surviving legacy-full tripwire — so the guard
    has something to catch."""
    base = runner_mod._base_dir()
    for relpath, table in (
        ("01_staging/stg_student_submission.sql", "stg_student_submission"),
        ("01_staging/stg_question_data.sql", "stg_question_data"),
    ):
        sql = (base / relpath).read_text(encoding="utf-8")
        assert runner_mod._truncated_session_tables(sql) == [table]


def test_truncated_session_tables_skips_do_block_wrapped_fact_truncate() -> None:
    """The REAL fact SQL wraps its TRUNCATE inside a ``DO $scope$`` body (the
    scoped-idiom full-mode ELSE branch); the statement-aware scan must SKIP it, so
    the fact file reports NO top-level offender (§1c)."""
    base = runner_mod._base_dir()
    fact_sql = (base / "07_facts/fact_student_submission.sql").read_text(encoding="utf-8")
    assert runner_mod._truncated_session_tables(fact_sql) == []


def test_helper_do_block_inner_truncate_not_flagged() -> None:
    """A TRUNCATE inside a ``DO`` body is the scoped idiom's full-mode ELSE branch,
    never an unscoped erase → not flagged."""
    sql = """
    DO $scope$ BEGIN
      IF EXISTS (SELECT 1 FROM _scope_assessments) THEN
        DELETE FROM fact_student_submission WHERE subject_id IN (SELECT 1);
      ELSE
        TRUNCATE TABLE fact_student_submission;
      END IF;
    END $scope$;
    """
    assert runner_mod._truncated_session_tables(sql) == []


def test_helper_top_level_truncate_of_session_table_is_flagged() -> None:
    """A bare top-level TRUNCATE of a session-bearing table IS flagged."""
    assert runner_mod._truncated_session_tables(
        "TRUNCATE TABLE fact_student_submission;"
    ) == ["fact_student_submission"]


def test_helper_top_level_truncate_of_cube_is_flagged() -> None:
    """Any top-level TRUNCATE of a cube_* table is flagged (prefix rule)."""
    assert runner_mod._truncated_session_tables(
        "TRUNCATE TABLE cube_question_summary;"
    ) == ["cube_question_summary"]


def test_helper_mixed_do_block_and_top_level_flags_only_top_level() -> None:
    """A file with a DO-wrapped dim TRUNCATE plus a bare staging TRUNCATE reports
    only the bare (top-level) one."""
    sql = """
    DO $$ BEGIN TRUNCATE TABLE dim_subject; END $$;
    TRUNCATE TABLE stg_question_data;
    """
    assert runner_mod._truncated_session_tables(sql) == ["stg_question_data"]


# ── Layer 2 (scoped filter): hermetic crafted-file guard tests ──────────────
# These monkeypatch TRANSFORMATIONS_ORDER at a temp dir so the scoped/legacy
# filter is exercised in isolation from the evolving real SQL files. DB-free.


async def test_guard_scoped_permits_top_level_staging_truncate(monkeypatch, tmp_path) -> None:
    """A crafted staging file with a bare top-level ``TRUNCATE
    stg_student_submission`` is PERMITTED under a lock when ``scoped=True`` (it is
    per-run scratch)."""
    d = tmp_path / "01_staging"
    d.mkdir()
    (d / "stg_student_submission.sql").write_text(
        "TRUNCATE TABLE stg_student_submission;\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        runner_mod,
        "TRANSFORMATIONS_ORDER",
        [("01_staging/stg_student_submission.sql", "staging")],
        raising=True,
    )
    _patch_runner_repo(monkeypatch, _FakeLockRepo(any_locked=True))

    result = await runner_mod._assert_no_locked_truncate(
        session=object(), base=tmp_path, only_tag=None, scoped=True
    )
    assert result is None


async def test_guard_legacy_full_still_refuses_top_level_staging_truncate(
    monkeypatch, tmp_path
) -> None:
    """The SAME crafted staging file is REFUSED under a lock in legacy-full mode
    (``scoped=False``): the staging scratch TRUNCATE is the surviving tripwire."""
    d = tmp_path / "01_staging"
    d.mkdir()
    (d / "stg_student_submission.sql").write_text(
        "TRUNCATE TABLE stg_student_submission;\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        runner_mod,
        "TRANSFORMATIONS_ORDER",
        [("01_staging/stg_student_submission.sql", "staging")],
        raising=True,
    )
    _patch_runner_repo(monkeypatch, _FakeLockRepo(any_locked=True))

    with pytest.raises(RuntimeError) as exc:
        await runner_mod._assert_no_locked_truncate(
            session=object(), base=tmp_path, only_tag=None, scoped=False
        )
    assert "stg_student_submission" in str(exc.value)


async def test_guard_scoped_still_refuses_top_level_cube_truncate(monkeypatch, tmp_path) -> None:
    """Even ``scoped=True`` REFUSES a top-level cube/fact TRUNCATE: only the two
    staging scratch tables are permitted, everything else stays refused (§1c)."""
    d = tmp_path / "09_cubes"
    d.mkdir()
    (d / "cube_evil.sql").write_text(
        "TRUNCATE TABLE cube_question_summary;\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        runner_mod,
        "TRANSFORMATIONS_ORDER",
        [("09_cubes/cube_evil.sql", "cubes")],
        raising=True,
    )
    _patch_runner_repo(monkeypatch, _FakeLockRepo(any_locked=True))

    with pytest.raises(RuntimeError) as exc:
        await runner_mod._assert_no_locked_truncate(
            session=object(), base=tmp_path, only_tag=None, scoped=True
        )
    assert "cube_question_summary" in str(exc.value)


# ── Layer 1: worker app guard ───────────────────────────────────────────────


def _make_worker() -> IngestionWorker:
    # blob_client_factory is required to construct; never invoked in these tests
    # because the locked branch aborts before any blob use.
    return IngestionWorker(blob_client_factory=lambda: object())


async def test_worker_marks_failed_when_target_session_locked(monkeypatch) -> None:
    """App guard: when ``_locked_target_session`` reports a locked session, the
    worker marks the run ``failed(...locked...)`` and NEVER calls ``run_ingestion``.
    """
    worker = _make_worker()
    marks: List[Tuple[str, str, Optional[Dict[str, Any]]]] = []
    ingest_called: List[bool] = []

    async def _fake_short_name(_run):  # noqa: ANN001
        return "athenian"

    async def _fake_locked(_run):  # noqa: ANN001
        return SYNTHETIC_SESSION

    async def _fake_mark(run_id, status, details=None):  # noqa: ANN001
        marks.append((run_id, status, details))

    async def _fake_ingest(*a, **k):  # noqa: ANN001
        ingest_called.append(True)
        raise AssertionError("run_ingestion must NOT be called for a locked run")

    monkeypatch.setattr(worker, "_short_name_for", _fake_short_name)
    monkeypatch.setattr(worker, "_locked_target_session", _fake_locked)
    monkeypatch.setattr(worker, "_mark", _fake_mark)
    monkeypatch.setattr(worker_mod, "run_ingestion", _fake_ingest, raising=False)

    run_id = str(uuid4())
    result = await worker._land_run({"run_id": run_id, "school_id": "sid"})

    assert result is None
    assert ingest_called == []  # aborted before any ingest
    assert len(marks) == 1
    marked_run_id, status, details = marks[0]
    assert marked_run_id == run_id
    assert status == "failed"
    assert "locked" in (details or {}).get("error", "")
    assert SYNTHETIC_SESSION in (details or {}).get("error", "")


async def test_worker_inert_when_session_not_locked(monkeypatch) -> None:
    """Inert path: when ``_locked_target_session`` returns None the worker does
    NOT short-circuit on the lock — it proceeds past the guard into landing.

    We prove "proceeds past the guard" by stubbing the very next side effect
    (``set_warehouse_dirty`` via a fake ``session_scope``) and having
    ``run_ingestion`` raise a sentinel: reaching that sentinel means the lock
    guard let the run through. No real DB write, no real ingest.
    """
    worker = _make_worker()
    marks: List[Tuple[str, str, Optional[Dict[str, Any]]]] = []
    reached_landing: List[bool] = []

    async def _fake_short_name(_run):  # noqa: ANN001
        return "athenian"

    async def _fake_locked(_run):  # noqa: ANN001
        return None  # NOT locked → guard must be inert

    async def _fake_mark(run_id, status, details=None):  # noqa: ANN001
        marks.append((run_id, status, details))

    class _FakeRepo:
        def __init__(self, _session):  # noqa: ANN001
            pass

        async def set_warehouse_dirty(self, _run_id):  # noqa: ANN001
            return None

    class _FakeScope:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *exc):  # noqa: ANN001
            return False

    def _fake_session_scope():
        return _FakeScope()

    class _Sentinel(Exception):
        pass

    async def _fake_ingest(*a, **k):  # noqa: ANN001
        reached_landing.append(True)
        raise _Sentinel("reached landing past the lock guard")

    # Blob factory returns an object whose list_files is harmless.
    class _FakeBlob:
        def list_files(self, _short):  # noqa: ANN001
            return []

    worker._blob_client_factory = _FakeBlob

    monkeypatch.setattr(worker, "_short_name_for", _fake_short_name)
    monkeypatch.setattr(worker, "_locked_target_session", _fake_locked)
    monkeypatch.setattr(worker, "_mark", _fake_mark)
    monkeypatch.setattr(worker_mod, "session_scope", _fake_session_scope)
    monkeypatch.setattr(worker_mod, "IngestionRunRepository", _FakeRepo)
    monkeypatch.setattr(worker_mod, "run_ingestion", _fake_ingest, raising=False)
    # Heartbeat loop would run forever; stub it to a no-op coroutine.

    async def _noop_heartbeat(_run_id):  # noqa: ANN001
        return None

    monkeypatch.setattr(worker, "_heartbeat_loop", _noop_heartbeat)

    result = await worker._land_run({"run_id": str(uuid4()), "school_id": "sid"})

    # The run was NOT failed by the lock guard; it proceeded to landing and only
    # failed on our injected sentinel (proving the guard was inert).
    assert reached_landing == [True]
    assert result is None
    # The only mark recorded is the sentinel landing failure, NOT a lock failure.
    assert len(marks) == 1
    _run_id, status, details = marks[0]
    assert status == "failed"
    assert "locked" not in (details or {}).get("error", "")
