"""Blob client abstraction.

For Phase 1 we read scraper output from the LOCAL filesystem (`data/<School>/...`).
Phase 7 will swap in an Azure Blob client behind the same interface.

Selected via the env var `INGESTION_SOURCE` (default = "local").

Both implementations expose:
    list_files(school_root_prefix) -> Iterable[BlobInfo]
    download(blob_path) -> bytes

The orchestrator does NOT care which is in use.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable, Protocol


@dataclass(frozen=True)
class BlobInfo:
    """Lightweight metadata about a single CSV blob.

    `path` is the path RELATIVE TO `school_root` (e.g. starts with the session folder).
    `last_modified` is timezone-aware UTC.
    """

    path: str
    last_modified: datetime
    size_bytes: int


class BlobClient(Protocol):
    """Protocol every blob client implements."""

    def list_files(self, school_root: str | Path) -> Iterable[BlobInfo]:
        """Yield every CSV under `school_root` (recursively)."""
        ...

    def download(self, blob_path: str, school_root: str | Path) -> bytes:
        """Return the bytes of the file at `school_root / blob_path`."""
        ...


# ───────────────────────────────────────────────────────────────────────────
# Local filesystem implementation (dev + integration tests)
# ───────────────────────────────────────────────────────────────────────────


class LocalBlobClient:
    """Reads scraper output from the local filesystem.

    `data_root` is the project's data/ directory. School roots live under it
    as `data/<SchoolShortName>/` (e.g. `data/Athenian/`).
    """

    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root).resolve()

    def list_files(self, school_root: str | Path) -> Iterable[BlobInfo]:
        """Walk the school's folder tree, yielding all .csv files (POSIX-style relative paths)."""
        root = self._resolve_school_root(school_root)
        if not root.exists():
            return
        for p in root.rglob("*.csv"):
            if not p.is_file():
                continue
            stat = p.stat()
            rel = p.relative_to(root)
            # Use forward-slashes for blob-style path equivalence
            rel_posix = "/".join(rel.parts)
            yield BlobInfo(
                path=rel_posix,
                last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                size_bytes=stat.st_size,
            )

    def download(self, blob_path: str, school_root: str | Path) -> bytes:
        """Load and return raw bytes of the file."""
        root = self._resolve_school_root(school_root)
        # Convert POSIX-style relative path back to OS-native
        full = root.joinpath(*PurePosixPath(blob_path).parts)
        return full.read_bytes()

    def _resolve_school_root(self, school_root: str | Path) -> Path:
        p = Path(school_root)
        if not p.is_absolute():
            p = (self.data_root / p).resolve()
        return p


# ───────────────────────────────────────────────────────────────────────────
# Azure Blob implementation (stub for Phase 1; real impl in Phase 7)
# ───────────────────────────────────────────────────────────────────────────


class AzureBlobClient:
    """Phase 7 placeholder. NotImplementedError on every call.

    A real implementation will use `azure-storage-blob` with an SAS token,
    listing under `oea/pre_landing/Schoology/<school>/<session>/...`.
    """

    def __init__(self, sas_url: str | None = None) -> None:
        self.sas_url = sas_url or os.environ.get("AZURE_BLOB_SAS_URL")

    def list_files(self, school_root: str | Path) -> Iterable[BlobInfo]:
        raise NotImplementedError("AzureBlobClient is reserved for Phase 7.")

    def download(self, blob_path: str, school_root: str | Path) -> bytes:
        raise NotImplementedError("AzureBlobClient is reserved for Phase 7.")


# ───────────────────────────────────────────────────────────────────────────
# Factory
# ───────────────────────────────────────────────────────────────────────────


def make_blob_client(
    *, source: str | None = None, data_root: str | Path | None = None
) -> BlobClient:
    """Construct the configured blob client.

    Args:
        source: "local" or "azure". Defaults to env `INGESTION_SOURCE`, then "local".
        data_root: only meaningful for "local"; defaults to `<repo>/data`.
    """
    src = (source or os.environ.get("INGESTION_SOURCE") or "local").lower()
    if src == "local":
        if data_root is None:
            # default to <repo>/data based on this file's location
            data_root = Path(__file__).resolve().parents[3] / "data"
        return LocalBlobClient(data_root=data_root)
    if src == "azure":
        return AzureBlobClient()
    raise ValueError(f"unknown INGESTION_SOURCE: {src!r}")
