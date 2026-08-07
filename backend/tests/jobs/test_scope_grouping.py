"""Proof tests for scoped-transform assessment grouping
(``app.transformations.runner._connected_components``).

The roster gate prunes assessments in atomic GROUPS, never a single subject out
of a rename-linked set (DO-NOT #16). A group is a connected component of subjects
linked by a shared ``(school_id, item_id)``: the same batch item owned by two
subjects (one in fresh staging, one swept out of pre-delete fact) is exactly the
rename hop that must travel together.

``_connected_components(subjects, item_owner_rows)`` where
``item_owner_rows`` = ``(school_id, item_id, subject_id)``. These are pure
union-find tests — crafted inputs, no DB.
"""

from __future__ import annotations

import inspect
from typing import Any, List, Optional

import pytest

import app.repositories.locked_sessions_repository as lock_repo_mod
from app.transformations import runner as runner_mod
from app.transformations.runner import (
    TransformResult,
    _connected_components,
    _discover_landed_runs,
    _handle_empty_scope,
    _locked_group_prune,
)


def _as_sets(groups) -> set[frozenset[str]]:
    return {frozenset(g) for g in groups}


def test_subjects_sharing_an_item_form_one_component() -> None:
    """Two subjects that own the SAME (school, item) land in a single group."""
    subjects = frozenset({"s1", "s2"})
    rows = [
        ("school-a", "item-1", "s1"),
        ("school-a", "item-1", "s2"),   # same (school, item) → linked
    ]
    comps = _connected_components(subjects, rows)
    assert comps == [frozenset({"s1", "s2"})]


def test_isolated_subjects_are_singletons() -> None:
    """Subjects that share no item are each their own group."""
    subjects = frozenset({"s1", "s2", "s3"})
    rows = [
        ("school-a", "item-1", "s1"),
        ("school-a", "item-2", "s2"),
        ("school-a", "item-3", "s3"),
    ]
    comps = _connected_components(subjects, rows)
    assert _as_sets(comps) == {frozenset({"s1"}), frozenset({"s2"}), frozenset({"s3"})}


def test_rename_old_and_new_subject_group_together() -> None:
    """A rename: the OLD subject (swept from pre-delete fact) and the NEW subject
    (fresh staging) own the same batch item → one atomic group. This is the
    linkage the roster gate must never split."""
    subjects = frozenset({"old-subj", "new-subj"})
    rows = [
        ("school-a", "item-42", "new-subj"),   # fresh-staging edge
        ("school-a", "item-42", "old-subj"),   # swept-fact edge
    ]
    comps = _connected_components(subjects, rows)
    assert comps == [frozenset({"old-subj", "new-subj"})]


def test_empty_input_yields_no_components() -> None:
    """Nothing in, nothing out."""
    assert _connected_components(frozenset(), []) == []


def test_same_item_id_different_school_is_not_linked() -> None:
    """The linkage key is (school_id, item_id), not item_id alone: the same
    item_id string under two schools must NOT merge their subjects."""
    subjects = frozenset({"s1", "s2"})
    rows = [
        ("school-a", "item-1", "s1"),
        ("school-b", "item-1", "s2"),   # same item_id, different school → NOT linked
    ]
    comps = _connected_components(subjects, rows)
    assert _as_sets(comps) == {frozenset({"s1"}), frozenset({"s2"})}


def test_transitive_linkage_merges_chained_subjects() -> None:
    """s1–s2 via item-1 and s2–s3 via item-2 pull all three into one group."""
    subjects = frozenset({"s1", "s2", "s3"})
    rows = [
        ("school-a", "item-1", "s1"),
        ("school-a", "item-1", "s2"),
        ("school-a", "item-2", "s2"),
        ("school-a", "item-2", "s3"),
    ]
    comps = _connected_components(subjects, rows)
    assert comps == [frozenset({"s1", "s2", "s3"})]


def test_subject_with_no_edges_still_appears_as_a_singleton() -> None:
    """Every subject in ``subjects`` must appear — one that owns no batch item
    (no edge row) is still surfaced as its own group so the roster gate can act
    on it."""
    subjects = frozenset({"s1", "s2"})
    rows = [("school-a", "item-1", "s1")]   # s2 has no edge
    comps = _connected_components(subjects, rows)
    assert _as_sets(comps) == {frozenset({"s1"}), frozenset({"s2"})}


# ── _handle_empty_scope: P7 fail-closed raise + QD-only no-op (#14) ─────────


async def test_handle_empty_scope_raises_when_student_raw_landed_all_pruned() -> None:
    """Safety-critical: landed_student > 0 with zero survivors (the roster gate
    pruned everything) MUST raise ``SCOPED TRANSFORM ABORTED`` so the txn rolls
    back and raw is retained — never a silent empty commit."""
    with pytest.raises(RuntimeError, match="ABORTED"):
        await _handle_empty_scope(5, TransformResult(), all_pruned=True)


async def test_handle_empty_scope_raises_when_student_raw_landed_zero_subjects() -> None:
    """The other >0 branch: raw landed but the batch produced ZERO in-scope
    subjects (bad overrides / student_role_id) also fail-closes."""
    with pytest.raises(RuntimeError, match="ABORTED"):
        await _handle_empty_scope(5, TransformResult(), all_pruned=False)


async def test_handle_empty_scope_qd_only_noop_returns_sentinel(caplog) -> None:
    """landed_student == 0 (question-data-only / empty ingest): NO raise. Attaches
    the ``qd_only_noop`` sentinel so the worker marks the folded run(s) FAILED +
    retains raw (never succeeded+purged, which would drop the QD correction)."""
    results = TransformResult()
    with caplog.at_level("WARNING"):
        out = await _handle_empty_scope(0, results, all_pruned=False)
    assert out is results
    assert out.scope is not None
    assert out.scope.qd_only_noop is True
    assert out.scope.survivors == frozenset()
    assert "no-op" in caplog.text.lower()


# ── (d) #13 GROUP-grain locked prune + roster coverage keyed on group_id ─────


class _AttrRow:
    """A row exposing ``.subject_id`` / ``.school_id`` / ``.session`` like the
    runner reads off ``_scope_assessments``."""

    def __init__(self, subject_id: str, school_id: str, session: Optional[str]) -> None:
        self.subject_id = subject_id
        self.school_id = school_id
        self.session = session


class _FakeResult:
    def __init__(self, rows: List[Any]) -> None:
        self._rows = rows

    def all(self) -> List[Any]:
        return self._rows


class _FakeSession:
    """Returns a fixed ``_scope_assessments`` row set for any execute() — no DB."""

    def __init__(self, rows: List[Any]) -> None:
        self._rows = rows

    async def execute(self, *_a: Any, **_k: Any) -> _FakeResult:
        return _FakeResult(self._rows)


class _FakeLockRepo:
    def __init__(self, *, any_locked: bool, locked_pairs: List[tuple]) -> None:
        self._any = any_locked
        self._pairs = locked_pairs

    async def any_locked(self) -> bool:
        return self._any

    async def list_all(self) -> List[dict]:
        return [{"school_id": s, "session": ss} for s, ss in self._pairs]


def _patch_lock_repo(monkeypatch, repo: _FakeLockRepo) -> None:
    # ``_locked_group_prune`` lazily imports the repo from its SOURCE module.
    monkeypatch.setattr(
        lock_repo_mod, "LockedSessionsRepository", lambda _session: repo, raising=True
    )


async def test_locked_group_prune_fails_whole_group_touching_a_lock(monkeypatch) -> None:
    """#18: a group whose subject touches a locked (school, session) is pruned
    WHOLE (fail-closed at group grain) up-front; a co-ingested group touching no
    lock is preserved."""
    repo = _FakeLockRepo(any_locked=True, locked_pairs=[("sa", "2024-25")])
    _patch_lock_repo(monkeypatch, repo)
    session = _FakeSession([
        _AttrRow("s1", "sa", "2024-25"),   # touches the locked slice
        _AttrRow("s2", "sb", "2025-26"),   # untouched
    ])
    groups = [frozenset({"s1"}), frozenset({"s2"})]

    pruned = await _locked_group_prune(session, groups)
    assert pruned == frozenset({"s1"})


async def test_locked_group_prune_prunes_the_entire_rename_group(monkeypatch) -> None:
    """A multi-subject rename group where ONLY ONE subject touches the lock still
    prunes the WHOLE group (never split — DO-NOT #16)."""
    repo = _FakeLockRepo(any_locked=True, locked_pairs=[("sa", "2024-25")])
    _patch_lock_repo(monkeypatch, repo)
    session = _FakeSession([
        _AttrRow("old", "sa", "2024-25"),  # locked
        _AttrRow("new", "sa", "2025-26"),  # not locked, but same group as `old`
    ])
    groups = [frozenset({"old", "new"})]

    pruned = await _locked_group_prune(session, groups)
    assert pruned == frozenset({"old", "new"})


async def test_locked_group_prune_inert_when_nothing_locked(monkeypatch) -> None:
    """The prod invariant: locked_sessions empty → the prune is inert (returns
    empty) and never inspects _scope_assessments."""
    repo = _FakeLockRepo(any_locked=False, locked_pairs=[])
    _patch_lock_repo(monkeypatch, repo)

    class _Boom(_FakeSession):
        async def execute(self, *_a: Any, **_k: Any):
            raise AssertionError("must not query _scope_assessments when unlocked")

    pruned = await _locked_group_prune(_Boom([]), [frozenset({"s1"})])
    assert pruned == frozenset()


def test_roster_coverage_is_keyed_on_group_id_not_school() -> None:
    """(d) #13 tripwire: the roster coverage SQL matches (group_id, user_uid), so a
    partial re-scrape of one subject can no longer be vouched for by a co-ingested
    SIBLING subject in a DIFFERENT rename-group. If a future edit drops the
    group_id join (reverting to (school_id, user_uid)), this flips red."""
    sql = str(runner_mod._ROSTER_UNCOVERED_SQL).lower()
    assert "group_id" in sql
    # have/need coverage joined on BOTH group_id and user_uid.
    assert "h.group_id = n.group_id" in sql
    assert "h.user_uid = n.user_uid" in sql


def test_discover_landed_runs_filters_on_landed_status() -> None:
    """#16 tripwire: ``_discover_landed_runs`` must carry ``status = 'landed'`` so
    ``--scope-landed`` matches the worker's fold semantics and never re-scopes
    already-'succeeded' history on a full-raw box."""
    src = inspect.getsource(_discover_landed_runs)
    assert "status = 'landed'" in src


def test_cube_user_summary_delete_and_insert_are_null_session_safe() -> None:
    """#23 tripwire: cube_user_summary's scoped DELETE + INSERT filter must match
    ``(school_id, COALESCE(session,'(null)'))`` so a NULL-session slice is not
    silently skipped by a row-value ``IN`` (NULL never equals NULL)."""
    base = runner_mod._base_dir()
    sql = (base / "09_cubes/cube_user_summary.sql").read_text(encoding="utf-8").lower()
    assert sql.count("coalesce(session, '(null)')") >= 2  # DELETE + INSERT filter
    # The bare row-value IN over a NULL-able session (the original bug) must be gone.
    assert "(school_id, session) in" not in sql
