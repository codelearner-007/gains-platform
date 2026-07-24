"""Live-storage E2E: rows actually land through the real Supabase Storage path.

ENV-GATED. Skipped entirely unless ``RUN_STORAGE_E2E=1`` — a plain
``pytest tests/jobs/test_ingestion_storage_e2e.py`` collects this module and
reports it SKIPPED (never errors), so it is safe in the default suite.

What it proves (BUILD_PLAN Wave 3, Agent E):
    Upload the REAL Athenian trio bytes (Question-Data / Student-Submissions /
    Submission-Summary) to the private ``schoology-ingest`` bucket under a
    SYNTHETIC session prefix ``Athenian/2098-99/…/Sec 1/`` — with ONE trailing
    newline appended to each file so the SHA-256 differs from any already-ingested
    copy while the CSV parses identically — then run the real ingestion via
    ``SupabaseStorageBlobClient`` with ``skip_transforms=True`` and assert rows
    land in the three raw tables for the three known hashes.

Safety (R12):
    * ``skip_transforms=True`` — transforms/cubes are NEVER run, so no synthetic
      row ever reaches staging/dims/facts/cubes or moves a KPI baseline.
    * A synthetic ``2098-99`` session (never a real one) isolates the keys.
    * Cleanup is hash-scoped: the ``finally`` block DELETEs the raw rows and
      ``ingested_files`` rows by the exact three ``source_file_hash`` /
      ``file_hash`` values, ``remove()``s the uploaded storage keys, and disposes
      the jobs engine. Nothing outside these three hashes is touched.

Creds (R13): sourced from ``SUPABASE_URL`` / ``SUPABASE_SERVICE_KEY`` in the
environment (which the local test plan populates from ``supabase status -o env``),
falling back to ``settings`` when unset.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_STORAGE_E2E") != "1",
    reason="live-storage E2E; set RUN_STORAGE_E2E=1 to run",
)

# Real Athenian fixture trio (Social Studies / Grade 6 / Sec 1). The bytes are
# uploaded verbatim (plus one trailing newline) — same fixtures the repo ships.
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

# Synthetic session — MUST NOT collide with any real session so the keys, hashes,
# and raw rows are exclusively ours to assert on and clean up.
_SCHOOL_ROOT = "Athenian"
_SYNTHETIC_SESSION = "2098-99"
_REL_PREFIX = f"{_SYNTHETIC_SESSION}/1 - Lesson  Assessments/Social Studies/Grade 6/Sec 1"

# (raw table, hash column) triples the three files land in.
_RAW_TABLES = {
    "Question-Data": "raw_question_data",
    "Student-Submissions": "raw_student_submission",
    "Submission-Summary": "raw_submission_summary",
}


def _storage_client():
    """Service-role Supabase client, creds from env (R13) or settings."""
    from supabase import create_client

    from app.core.config import settings

    url = os.environ.get("SUPABASE_URL") or settings.SUPABASE_URL
    key = os.environ.get("SUPABASE_SERVICE_KEY") or settings.SUPABASE_SERVICE_KEY
    return create_client(url, key)


async def test_storage_e2e_rows_land_and_cleanup():
    from app.core.config import settings
    from app.jobs.blob_client import SupabaseStorageBlobClient
    from app.jobs.db import dispose_engine, session_scope
    from app.jobs.ingest_schoology import run_ingestion

    # The jobs engine reads DATABASE_URL from os.environ with a local fallback;
    # pydantic-settings does NOT export .env to os.environ (R3), so seed it.
    os.environ.setdefault("DATABASE_URL", settings.DATABASE_URL)

    # 1. Read the real fixtures, append one trailing newline → new SHA-256, same
    #    parse. Compute the hash the ingester will see (over the exact bytes).
    payloads: dict[str, bytes] = {}
    hashes: dict[str, str] = {}  # storage key -> sha256
    for fname in _FIXTURE_FILES:
        raw = (_FIXTURE_DIR / fname).read_bytes() + b"\n"
        key = f"{_SCHOOL_ROOT}/{_REL_PREFIX}/{fname}"
        payloads[key] = raw
        hashes[key] = hashlib.sha256(raw).hexdigest()

    all_hashes = list(hashes.values())
    assert len(set(all_hashes)) == 3, "fixtures must hash to three distinct values"

    client = _storage_client()
    bucket = client.storage.from_(settings.INGESTION_STORAGE_BUCKET)
    uploaded_keys: list[str] = []

    try:
        # 2. Upload the trio to the private bucket under the synthetic prefix.
        for key, data in payloads.items():
            bucket.upload(
                key,
                data,
                {"content-type": "text/csv", "upsert": "true"},
            )
            uploaded_keys.append(key)

        # 3. Run the REAL ingestion via the Storage blob client — transforms OFF.
        blob_client = SupabaseStorageBlobClient(
            bucket=settings.INGESTION_STORAGE_BUCKET, client=client
        )
        summary = await run_ingestion(
            school_filter="Athenian",
            blob_client=blob_client,
            skip_transforms=True,
        )

        # The three synthetic files must have landed with no per-file errors.
        assert summary.error_count == 0, summary.errors
        assert summary.rows_inserted > 0

        # 4. Assert raw rows exist for each hash in its expected table.
        async with session_scope() as session:
            for fname in _FIXTURE_FILES:
                key = f"{_SCHOOL_ROOT}/{_REL_PREFIX}/{fname}"
                file_hash = hashes[key]
                prefix = fname.split("-World-History", 1)[0]
                table = _RAW_TABLES[prefix]
                count = (
                    await session.execute(
                        text(
                            f"SELECT count(*) FROM {table} "  # noqa: S608 - table from fixed allowlist
                            "WHERE source_file_hash = :h"
                        ),
                        {"h": file_hash},
                    )
                ).scalar_one()
                assert count > 0, f"no rows in {table} for {fname} ({file_hash})"

            # And each landed hash was recorded in ingested_files.
            recorded = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM ingested_files "
                        "WHERE file_hash = ANY(:hashes)"
                    ),
                    {"hashes": all_hashes},
                )
            ).scalar_one()
            assert recorded == 3, "expected 3 ingested_files rows"

    finally:
        # 5. Hash-scoped teardown: raw rows, ingested_files, storage keys, engine.
        try:
            async with session_scope() as session:
                for table in _RAW_TABLES.values():
                    await session.execute(
                        text(
                            f"DELETE FROM {table} "  # noqa: S608 - table from fixed allowlist
                            "WHERE source_file_hash = ANY(:hashes)"
                        ),
                        {"hashes": all_hashes},
                    )
                await session.execute(
                    text(
                        "DELETE FROM ingested_files WHERE file_hash = ANY(:hashes)"
                    ),
                    {"hashes": all_hashes},
                )
        finally:
            if uploaded_keys:
                bucket.remove(uploaded_keys)
            await dispose_engine()
