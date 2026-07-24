"""Unit tests for SupabaseStorageBlobClient against a fake storage proxy.

No network, no DB. A FakeStorage models storage3 2.25.0's single-level,
paginated `list()` shape (R8): each call returns at most `limit` entries starting
at `offset`; folder placeholders carry `id=None`, files carry
`updated_at`/`created_at` + `metadata.size`. We assert:

  * pagination across the 100-entry page boundary (no truncation),
  * depth-first recursion into nested prefixes,
  * folder placeholders (`id is None`) are recursed, never yielded,
  * yielded paths are POSIX-relative to the school_root prefix,
  * non-CSV entries are filtered out,
  * `download` builds `<school_root>/<blob_path>` and passes bytes through,
  * `move`/`remove` delegate to the bucket proxy.
"""

from __future__ import annotations

import pytest

from app.jobs.blob_client import (
    BlobInfo,
    SupabaseStorageBlobClient,
    make_blob_client,
)


class FakeStorage:
    """Fake storage3 SyncBucketProxy.

    `tree` maps a directory prefix ("" for root) to a list of child names. `files`
    maps a full object key to its bytes. `list(prefix, options)` returns one
    single-level page honoring limit/offset, with folder placeholders (`id=None`)
    for directories and file entries (with metadata) for leaves.
    """

    def __init__(self, tree: dict[str, list[str]], files: dict[str, bytes]) -> None:
        self.tree = tree
        self.files = files
        self.list_calls: list[tuple[str, dict]] = []
        self.moved: list[tuple[str, str]] = []
        self.removed: list[list[str]] = []

    def list(self, prefix, options=None):
        self.list_calls.append((prefix, dict(options or {})))
        options = options or {}
        limit = options.get("limit", 100)
        offset = options.get("offset", 0)
        children = self.tree.get(prefix or "", [])
        entries = []
        for name in children:
            child_key = f"{prefix}/{name}" if prefix else name
            if child_key in self.tree:
                # Directory → folder placeholder (id=None, no metadata).
                entries.append({"name": name, "id": None, "metadata": None})
            else:
                entries.append(
                    {
                        "name": name,
                        "id": f"id-{child_key}",
                        "updated_at": "2026-07-22T10:00:00.000Z",
                        "created_at": "2026-07-22T09:00:00.000Z",
                        "metadata": {"size": len(self.files.get(child_key, b""))},
                    }
                )
        return entries[offset : offset + limit]

    def download(self, path):
        return self.files[path]

    def move(self, from_path, to_path):
        self.moved.append((from_path, to_path))
        return {"message": "moved"}

    def remove(self, paths):
        self.removed.append(list(paths))
        return [{"name": p} for p in paths]


class FakeClient:
    """Fake supabase Client exposing `.storage.from_(bucket)`."""

    def __init__(self, storage: FakeStorage) -> None:
        self._storage = storage
        self.storage = self  # `.storage`

    def from_(self, bucket):  # noqa: A003 - mirrors supabase API
        return self._storage


def _make(tree, files, bucket="schoology-ingest"):
    storage = FakeStorage(tree, files)
    client = FakeClient(storage)
    return SupabaseStorageBlobClient(bucket=bucket, client=client), storage


def test_relative_path_contract_single_level():
    """Yielded paths are POSIX-relative to the school_root, not absolute keys."""
    tree = {"Athenian": ["Question-Data-x.csv", "Submission-Summary-x.csv"]}
    files = {
        "Athenian/Question-Data-x.csv": b"a",
        "Athenian/Submission-Summary-x.csv": b"bb",
    }
    bc, _ = _make(tree, files)
    infos = list(bc.list_files("Athenian"))
    paths = sorted(i.path for i in infos)
    assert paths == ["Question-Data-x.csv", "Submission-Summary-x.csv"]
    assert all(isinstance(i, BlobInfo) for i in infos)
    # size comes from metadata.size
    by_path = {i.path: i for i in infos}
    assert by_path["Question-Data-x.csv"].size_bytes == 1
    assert by_path["Submission-Summary-x.csv"].size_bytes == 2
    # last_modified parsed tz-aware UTC
    assert by_path["Question-Data-x.csv"].last_modified.tzinfo is not None


def test_nested_prefixes_recurse_depth_first():
    """Folder placeholders are recursed; the full relative subtree is yielded."""
    tree = {
        "Athenian": ["2025-26"],
        "Athenian/2025-26": ["Social Studies"],
        "Athenian/2025-26/Social Studies": ["Grade 6"],
        "Athenian/2025-26/Social Studies/Grade 6": ["Sec 1"],
        "Athenian/2025-26/Social Studies/Grade 6/Sec 1": [
            "Question-Data-a.csv",
            "Student-Submissions-a.csv",
        ],
    }
    files = {
        "Athenian/2025-26/Social Studies/Grade 6/Sec 1/Question-Data-a.csv": b"q",
        "Athenian/2025-26/Social Studies/Grade 6/Sec 1/Student-Submissions-a.csv": b"s",
    }
    bc, _ = _make(tree, files)
    paths = sorted(i.path for i in bc.list_files("Athenian"))
    assert paths == [
        "2025-26/Social Studies/Grade 6/Sec 1/Question-Data-a.csv",
        "2025-26/Social Studies/Grade 6/Sec 1/Student-Submissions-a.csv",
    ]


def test_folder_placeholder_never_yielded():
    """Directories (id=None) must not appear as BlobInfo entries."""
    tree = {
        "Athenian": ["subdir", "top.csv"],
        "Athenian/subdir": ["nested.csv"],
    }
    files = {
        "Athenian/top.csv": b"t",
        "Athenian/subdir/nested.csv": b"n",
    }
    bc, _ = _make(tree, files)
    paths = sorted(i.path for i in bc.list_files("Athenian"))
    # "subdir" (the folder placeholder) is absent; its child is present.
    assert paths == ["subdir/nested.csv", "top.csv"]


def test_non_csv_filtered_out():
    tree = {"Athenian": ["keep.csv", "skip.txt", "also.CSV"]}
    files = {
        "Athenian/keep.csv": b"k",
        "Athenian/skip.txt": b"x",
        "Athenian/also.CSV": b"c",
    }
    bc, _ = _make(tree, files)
    paths = sorted(i.path for i in bc.list_files("Athenian"))
    # .csv match is case-insensitive; .txt dropped.
    assert paths == ["also.CSV", "keep.csv"]


def test_pagination_across_100_boundary():
    """>100 files in one prefix must page (offset += limit) with no truncation."""
    names = [f"Question-Data-{i:04d}.csv" for i in range(250)]
    tree = {"Athenian/2025-26/Sec 1": names}
    # add the intermediate folder placeholders so recursion reaches the leaves
    tree["Athenian"] = ["2025-26"]
    tree["Athenian/2025-26"] = ["Sec 1"]
    files = {f"Athenian/2025-26/Sec 1/{n}": b"x" for n in names}
    bc, storage = _make(tree, files)
    infos = list(bc.list_files("Athenian"))
    assert len(infos) == 250
    assert sorted(i.path for i in infos) == sorted(
        f"2025-26/Sec 1/{n}" for n in names
    )
    # The leaf prefix was paged: offsets 0, 100, 200 (plus a terminating short page).
    leaf = "Athenian/2025-26/Sec 1"
    offsets = [opts["offset"] for pfx, opts in storage.list_calls if pfx == leaf]
    assert offsets == [0, 100, 200]


def test_download_builds_full_key_and_passes_through():
    tree = {"Athenian": ["2025-26"], "Athenian/2025-26": ["Question-Data-a.csv"]}
    files = {"Athenian/2025-26/Question-Data-a.csv": b"raw-bytes"}
    bc, _ = _make(tree, files)
    data = bc.download("2025-26/Question-Data-a.csv", "Athenian")
    assert data == b"raw-bytes"


def test_school_root_slashes_normalized():
    """Leading/trailing slashes on school_root are stripped before prefixing."""
    tree = {"Athenian": ["x.csv"]}
    files = {"Athenian/x.csv": b"1"}
    bc, _ = _make(tree, files)
    assert [i.path for i in bc.list_files("/Athenian/")] == ["x.csv"]
    assert bc.download("x.csv", "/Athenian/") == b"1"


def test_move_and_remove_delegate():
    bc, storage = _make({}, {})
    bc.move("Athenian/2025-26/a.csv", "processed/Athenian/run/2025-26/a.csv")
    bc.remove(["Athenian/2025-26/a.csv"])
    assert storage.moved == [
        ("Athenian/2025-26/a.csv", "processed/Athenian/run/2025-26/a.csv")
    ]
    assert storage.removed == [["Athenian/2025-26/a.csv"]]


def test_empty_prefix_yields_nothing():
    bc, _ = _make({"Athenian": []}, {})
    assert list(bc.list_files("Athenian")) == []


def test_factory_registers_supabase_branch(monkeypatch):
    """make_blob_client(source='supabase') returns the storage client without
    touching the network (client is lazy, created only on first storage call)."""
    client = make_blob_client(source="supabase")
    assert isinstance(client, SupabaseStorageBlobClient)
    assert client.bucket == "schoology-ingest"


def test_factory_supabase_via_env(monkeypatch):
    monkeypatch.setenv("INGESTION_SOURCE", "supabase")
    client = make_blob_client()
    assert isinstance(client, SupabaseStorageBlobClient)


def test_factory_unknown_source_raises():
    with pytest.raises(ValueError):
        make_blob_client(source="nope")
