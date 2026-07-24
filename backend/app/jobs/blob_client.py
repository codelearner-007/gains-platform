"""Blob client abstraction.

For Phase 1 we read scraper output from the LOCAL filesystem (`data/<School>/...`).
Phase 2 adds a Supabase Storage client (`SupabaseStorageBlobClient`) reading from
the private `schoology-ingest` bucket the scraper uploads into.

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
from typing import Any, Iterable, Protocol


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
# Supabase Storage implementation (Phase 2 — scraper landing zone)
# ───────────────────────────────────────────────────────────────────────────

# storage3 2.25.0 `list()` is single-level and paginated with a default page of
# 100 (`DEFAULT_SEARCH_OPTIONS`). We page with an explicit limit and walk each
# prefix depth-first.
_STORAGE_PAGE_LIMIT = 100


class SupabaseStorageBlobClient:
    """Reads scraper output from a private Supabase Storage bucket.

    The scraper uploads CSV exports under
    `<short_name>/<session>/<category>/<subject>/<grade>/<section>/<file>.csv`.
    Per-school ingestion roots each pass at `school.short_name`, so `school_root`
    passed to `list_files`/`download` is exactly `<short_name>` and every yielded
    `BlobInfo.path` is POSIX-relative to it (matching `LocalBlobClient`).

    storage3 2.25.0 contract (verified empirically, R8):
      - `list(path, {limit, offset, sortBy, search}) -> list[dict]` — single level,
        default limit 100; page `offset += limit` until a page returns `< limit`.
      - An entry is a FOLDER placeholder iff `id is None` (recurse into it, do not
        yield it); a FILE carries `updated_at`/`created_at` and `metadata.size`.
      - `download(path) -> bytes`, `move(from, to) -> dict`, `remove(list) -> list`.
    """

    def __init__(self, bucket: str | None = None, client: Any | None = None) -> None:
        # `client` is an injected supabase Client (tests supply a fake); when None
        # the service-role client is created lazily on first use.
        from app.core.config import settings

        self.bucket = bucket or settings.INGESTION_STORAGE_BUCKET
        self._client = client

    def _storage(self):
        """Return the bucket proxy (`storage.from_(bucket)`), creating the
        service-role client on first use (copied from school_service.py:37-44)."""
        if self._client is None:
            from supabase import create_client

            from app.core.config import settings

            self._client = create_client(
                settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY
            )
        return self._client.storage.from_(self.bucket)

    def list_files(self, school_root: str | Path) -> Iterable[BlobInfo]:
        """Yield every CSV under `<school_root>/` (recursively), paths relative
        to `school_root`."""
        root_prefix = self._normalize_prefix(school_root)
        storage = self._storage()
        yield from self._walk(storage, root_prefix, root_prefix)

    def _walk(
        self, storage: Any, prefix: str, root_prefix: str
    ) -> Iterable[BlobInfo]:
        """Depth-first walk of a single prefix, paging until exhausted."""
        offset = 0
        while True:
            page = storage.list(
                prefix,
                {
                    "limit": _STORAGE_PAGE_LIMIT,
                    "offset": offset,
                    "sortBy": {"column": "name", "order": "asc"},
                },
            )
            for entry in page:
                name = entry.get("name")
                if not name:
                    continue
                child_prefix = f"{prefix}/{name}" if prefix else name
                if entry.get("id") is None:
                    # Folder placeholder → recurse, never yield.
                    yield from self._walk(storage, child_prefix, root_prefix)
                    continue
                if not name.lower().endswith(".csv"):
                    continue
                rel = child_prefix[len(root_prefix) + 1 :] if root_prefix else child_prefix
                metadata = entry.get("metadata") or {}
                yield BlobInfo(
                    path=rel,
                    last_modified=_parse_last_modified(entry),
                    size_bytes=int(metadata.get("size") or 0),
                )
            if len(page) < _STORAGE_PAGE_LIMIT:
                break
            offset += _STORAGE_PAGE_LIMIT

    def download(self, blob_path: str, school_root: str | Path) -> bytes:
        """Return the bytes of `<school_root>/<blob_path>`."""
        root_prefix = self._normalize_prefix(school_root)
        key = f"{root_prefix}/{blob_path}" if root_prefix else blob_path
        return self._storage().download(key)

    # ── Non-Protocol helpers (post-ingest archive/cleanup; used by the dispatch
    #    path, NOT the ingest core). ──────────────────────────────────────────

    def move(self, from_key: str, to_key: str) -> Any:
        """Move an object to a new key within the bucket (archive to processed/)."""
        return self._storage().move(from_key, to_key)

    def remove(self, keys: list[str]) -> Any:
        """Delete objects by absolute key."""
        return self._storage().remove(keys)

    @staticmethod
    def _normalize_prefix(school_root: str | Path) -> str:
        """Coerce a school-root to a POSIX prefix with no leading/trailing slash."""
        return str(school_root).strip("/")


def _parse_last_modified(entry: dict[str, Any]) -> datetime:
    """Best-effort tz-aware UTC timestamp from a storage3 list entry.

    Prefers `updated_at`, falls back to `created_at`, then to now(). Handles the
    trailing-`Z` ISO-8601 form storage3 returns.
    """
    raw = entry.get("updated_at") or entry.get("created_at")
    if raw:
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


# ───────────────────────────────────────────────────────────────────────────
# Factory
# ───────────────────────────────────────────────────────────────────────────


def make_blob_client(
    *, source: str | None = None, data_root: str | Path | None = None
) -> BlobClient:
    """Construct the configured blob client.

    Args:
        source: "local", "supabase", or "azure". Defaults to env
            `INGESTION_SOURCE`, then "local".
        data_root: only meaningful for "local"; defaults to `<repo>/data`.
    """
    src = (source or os.environ.get("INGESTION_SOURCE") or "local").lower()
    if src == "local":
        if data_root is None:
            # default to <repo>/data based on this file's location
            data_root = Path(__file__).resolve().parents[3] / "data"
        return LocalBlobClient(data_root=data_root)
    if src == "supabase":
        return SupabaseStorageBlobClient()
    if src == "azure":
        return AzureBlobClient()
    raise ValueError(f"unknown INGESTION_SOURCE: {src!r}")
