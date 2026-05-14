"""Pytest fixtures for ingestion-job tests.

These tests talk to a LIVE local Postgres at the URL in DATABASE_URL.
For CI we expect docker-compose / supabase to be running.

The fixtures here:
    - athenian_school_id: UUID of the seeded Athenian school row.
    - reset_raw_tables: TRUNCATE all raw_* + ingestion_runs + ingested_files
      between tests (the integration test wants a clean slate).
    - data_root: absolute path to <repo>/data (used by LocalBlobClient).
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import dispose_engine, session_scope


@pytest.fixture(scope="session")
def data_root() -> Path:
    """Absolute path to the project's data/ directory.

    Resolved from this conftest's location: <repo>/backend/tests/jobs/conftest.py
    so <repo>/data is parents[3] / data.
    """
    return Path(__file__).resolve().parents[3] / "data"


@pytest.fixture
async def athenian_school_id() -> UUID:
    """Look up Athenian's UUID from the live `schools` table.

    Phase 0 must have seeded this (see supabase/seeds/schools_athenian.sql).
    """
    async with session_scope() as session:
        result = await session.execute(
            text(
                """
                SELECT school_id
                FROM schools
                WHERE schoology_building_id = '186370968'
                LIMIT 1
                """
            )
        )
        row = result.first()
        if row is None:
            pytest.skip("Athenian schools row not seeded — run `npx supabase db reset`")
        return row.school_id  # type: ignore[no-any-return]


@pytest.fixture
async def reset_raw_tables() -> None:
    """TRUNCATE the raw_* and run-history tables (CASCADE handles FKs).

    Used by the integration test to start from a clean slate.
    """
    async with session_scope() as session:
        # CASCADE clears children: raw_* are FK to ingestion_runs and ingested_files
        # is FK to ingestion_runs as well, so a single CASCADE on ingestion_runs
        # cleans the lot.
        await session.execute(
            text(
                """
                TRUNCATE TABLE
                    raw_submission_summary,
                    raw_student_submission,
                    raw_question_data,
                    ingested_files,
                    ingestion_runs
                RESTART IDENTITY CASCADE
                """
            )
        )


@pytest.fixture(scope="session", autouse=True)
async def _final_engine_dispose() -> None:
    """Tear down the asyncpg pool at the end of the test session."""
    yield
    await dispose_engine()
