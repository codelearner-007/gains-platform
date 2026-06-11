"""Tests for the gains_data CLI (Wave 3).

Two tiers:

* Pure-Python (no DB) — always run:
    - sampling determinism (same seed → same item set)
    - trio integrity (a selected assessment's full trio is always included)
    - --keep-standards table discovery preserves dim_standard/dim_strand
    - wipe refuses without --yes

* DB-backed — run ONLY against a SCRATCH database. Guarded by
  GAINS_TEST_DATABASE_URL so the live, audit-verified DB is never mutated:
    - multi-school additivity (ingest school A then B; A's raw counts unchanged)

The DB-backed tests build a real two-school local tree from the Athenian
corpus, re-stamping the CSV "User School ID" column so the staging join (which
now resolves school from the CSV, not the folder) routes each subtree to a
distinct seeded school.
"""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

import pytest

from app.jobs.blob_client import BlobInfo, LocalBlobClient
from app.jobs.gains_data import (
    SamplingBlobClient,
    _discover_wipe_tables,
    _trio_key,
    cmd_wipe,
)


DATA_ROOT = Path(__file__).resolve().parents[3] / "data"
ATHENIAN_DIR = DATA_ROOT / "Athenian"

_needs_athenian = pytest.mark.skipif(
    not ATHENIAN_DIR.exists(), reason="data/Athenian not present"
)


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


def _items_in(blobs: list[BlobInfo], base: LocalBlobClient, school_root: str) -> set[str]:
    """Distinct Item IDs represented by the item-bearing files in `blobs`."""
    from app.jobs.gains_data import _item_id_from_csv

    items: set[str] = set()
    for b in blobs:
        fn = b.path.split("/")[-1]
        if fn.startswith(("Question-Data-", "Student-Submissions-")):
            iid = _item_id_from_csv(base.download(b.path, school_root), b.path)
            if iid:
                items.add(iid)
    return items


def _trio_member_counts(blobs: list[BlobInfo]) -> dict:
    members: dict = defaultdict(set)
    for b in blobs:
        key = _trio_key(b.path)
        prefix = b.path.split("/")[-1].split("-")[0]
        members[key].add(prefix)
    return members


# ───────────────────────────────────────────────────────────────────────────
# Pure-Python: sampling
# ───────────────────────────────────────────────────────────────────────────


@_needs_athenian
def test_sampling_is_deterministic_for_same_seed() -> None:
    """Same seed + same school → identical selected blob set (paths + items)."""
    base = LocalBlobClient(data_root=DATA_ROOT)

    a = list(SamplingBlobClient(base, limit=10, seed=42).list_files("Athenian"))
    b = list(SamplingBlobClient(base, limit=10, seed=42).list_files("Athenian"))

    assert sorted(x.path for x in a) == sorted(x.path for x in b)
    assert _items_in(a, base, "Athenian") == _items_in(b, base, "Athenian")


@_needs_athenian
def test_sampling_selects_requested_assessment_count() -> None:
    """N distinct assessments (Item IDs) are selected, not N files."""
    base = LocalBlobClient(data_root=DATA_ROOT)
    blobs = list(SamplingBlobClient(base, limit=7, seed=1).list_files("Athenian"))
    assert len(_items_in(blobs, base, "Athenian")) == 7


@_needs_athenian
def test_different_seed_yields_different_sample() -> None:
    """A different seed selects a different assessment set (sanity for the RNG)."""
    base = LocalBlobClient(data_root=DATA_ROOT)
    a = list(SamplingBlobClient(base, limit=10, seed=42).list_files("Athenian"))
    b = list(SamplingBlobClient(base, limit=10, seed=99).list_files("Athenian"))
    assert _items_in(a, base, "Athenian") != _items_in(b, base, "Athenian")


@_needs_athenian
def test_sampling_never_splits_a_trio() -> None:
    """Every selected assessment includes its full Question-Data /
    Submission-Summary / Student-Submissions trio (3 members)."""
    base = LocalBlobClient(data_root=DATA_ROOT)
    blobs = list(SamplingBlobClient(base, limit=8, seed=7).list_files("Athenian"))
    counts = _trio_member_counts(blobs)
    assert counts, "expected at least one selected trio"
    for key, prefixes in counts.items():
        assert prefixes == {"Question", "Submission", "Student"}, (
            f"trio {key} was split: only {prefixes}"
        )


@_needs_athenian
def test_limit_above_available_returns_all() -> None:
    """A limit larger than the corpus returns every assessment (no error)."""
    base = LocalBlobClient(data_root=DATA_ROOT)
    full = list(base.list_files("Athenian"))
    sampled = list(SamplingBlobClient(base, limit=10_000, seed=3).list_files("Athenian"))
    assert sorted(x.path for x in sampled) == sorted(x.path for x in full)


def test_trio_key_groups_members(tmp_path: Path) -> None:
    """Trio key = (folder, filename-suffix); the three members share it."""
    suffix = "Algebra-2026-05-05-010203.csv"
    folder = "2025-26/1 - Lesson  Assessments/Math/Grade 5/Sec 1"
    keys = {
        _trio_key(f"{folder}/Question-Data-{suffix}"),
        _trio_key(f"{folder}/Submission-Summary-{suffix}"),
        _trio_key(f"{folder}/Student-Submissions-{suffix}"),
    }
    assert len(keys) == 1
    assert _trio_key("some/other/random.csv") is None


# ───────────────────────────────────────────────────────────────────────────
# Pure-Python / live-read: wipe behaviour
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wipe_refuses_without_yes() -> None:
    """wipe must REFUSE (return 1) and touch nothing without --yes."""
    rc = await cmd_wipe(keep_standards=True, yes=False, backup=False)
    assert rc == 1


@pytest.mark.asyncio
async def test_keep_standards_excludes_standards_tables() -> None:
    """--keep-standards leaves dim_standard/dim_strand OUT of the wipe set,
    while a full wipe includes them. Read-only against the live schema."""
    kept = await _discover_wipe_tables(keep_standards=True)
    full = await _discover_wipe_tables(keep_standards=False)

    assert "dim_standard" not in kept
    assert "dim_strand" not in kept
    assert "dim_standard" in full
    assert "dim_strand" in full
    # Other data tables are wiped in BOTH modes.
    for t in ("raw_student_submission", "fact_student_submission",
              "cube_school_summary", "ingested_files", "ingestion_runs"):
        assert t in kept and t in full


# ───────────────────────────────────────────────────────────────────────────
# DB-backed: multi-school additivity (SCRATCH DB only)
# ───────────────────────────────────────────────────────────────────────────


_SCRATCH = os.environ.get("GAINS_TEST_DATABASE_URL")
_scratch_only = pytest.mark.skipif(
    not _SCRATCH,
    reason="set GAINS_TEST_DATABASE_URL to a throwaway DB to run DB-mutating tests",
)


def _build_two_school_tree(
    dst: Path, a_short: str, a_sid: str, b_short: str, b_sid: str
) -> None:
    """Copy a few Athenian trios into a two-school tree, re-stamping the CSV
    'User School ID' so each subtree resolves to a distinct seeded school via
    the staging join. Folders are named by the real short_names so the
    orchestrator's per-school root walk (`<short_name>/`) finds them."""
    import csv as _csv
    import io as _io

    base = LocalBlobClient(data_root=DATA_ROOT)
    all_blobs = list(base.list_files("Athenian"))
    # Take the first 2 complete trios (6 files).
    by_trio: dict = defaultdict(list)
    for b in all_blobs:
        by_trio[_trio_key(b.path)].append(b)
    trios = [v for k, v in by_trio.items() if k is not None and len(v) == 3][:2]

    def _restamp(raw: bytes, new_school_id: str) -> bytes:
        text = raw.decode("utf-8-sig", errors="replace")
        reader = _csv.reader(_io.StringIO(text, newline=""))
        rows = list(reader)
        if not rows:
            return raw
        header = rows[0]
        if "User School ID" not in header:
            return raw  # Submission-Summary has no school column — copy as-is.
        idx = header.index("User School ID")
        out = _io.StringIO(newline="")
        w = _csv.writer(out)
        w.writerow(header)
        for r in rows[1:]:
            if len(r) > idx:
                r[idx] = new_school_id
            w.writerow(r)
        return out.getvalue().encode("utf-8")

    for short, sid, trio in ((a_short, a_sid, trios[0]),
                             (b_short, b_sid, trios[1])):
        for b in trio:
            target = dst / short / b.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_restamp(base.download(b.path, "Athenian"), sid))


@_scratch_only
@_needs_athenian
@pytest.mark.asyncio
async def test_multi_school_additivity(tmp_path: Path) -> None:
    """Ingest school A, snapshot its raw counts, ingest school B, then assert
    A's raw rows are unchanged (raw_* is append-only + school_id-namespaced)."""
    from sqlalchemy import text

    from app.jobs.db import dispose_engine, session_scope
    from app.jobs.gains_data import cmd_ingest

    os.environ["DATABASE_URL"] = _SCRATCH
    await dispose_engine()

    # Pick two real seeded schools by schoology_school_id.
    async with session_scope() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT short_name, schoology_school_id FROM schools "
                    "WHERE is_active = TRUE ORDER BY short_name LIMIT 2"
                )
            )
        ).all()
    if len(rows) < 2:
        pytest.skip("scratch DB needs >=2 seeded schools (run seed first)")
    a_short, a_sid = rows[0]
    b_short, b_sid = rows[1]

    tree = tmp_path / "tree"
    _build_two_school_tree(tree, a_short, a_sid, b_short, b_sid)

    async def _raw_counts(school_sid: str) -> dict[str, int]:
        async with session_scope() as session:
            out: dict[str, int] = {}
            for tbl in ("raw_student_submission", "raw_question_data"):
                r = await session.execute(
                    text(
                        f"SELECT count(*) FROM {tbl} r "
                        "JOIN schools s ON s.school_id = r.school_id "
                        "WHERE s.schoology_school_id = :sid"
                    ),
                    {"sid": school_sid},
                )
                out[tbl] = r.scalar_one()
            return out

    # The orchestrator walks <data_root>/<short_name>/, so the tree folders are
    # named by the real short_names. Ingest A first, snapshot, then ingest B.
    summary_a = await cmd_ingest(
        school=a_short, data_root=str(tree),
        source="local", limit_per_school=0, seed=0,
    )
    assert summary_a.error_count == 0
    snap_a_before = await _raw_counts(a_sid)
    assert snap_a_before["raw_student_submission"] > 0

    summary_b = await cmd_ingest(
        school=b_short, data_root=str(tree),
        source="local", limit_per_school=0, seed=0,
    )
    assert summary_b.error_count == 0

    snap_a_after = await _raw_counts(a_sid)
    assert snap_a_after == snap_a_before, "school A raw counts changed after ingesting B"

    await dispose_engine()
