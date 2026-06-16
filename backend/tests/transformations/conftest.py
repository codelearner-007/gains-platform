"""Pytest fixtures for Phase 2 transformation tests.

These tests run against the live local Postgres at $DATABASE_URL (default
postgres://postgres:postgres@127.0.0.1:56322/postgres) — same setup as the
ingestion-job tests in tests/jobs/conftest.py.

Each test in this directory expects:
    1. The Phase 0 schema applied (`supabase db reset`).
    2. dim_standard + dim_strand seeded (run `python supabase/seeds/load_standards.py`).
    3. The Athenian school row + teacher_pair_overrides seeded.
    4. Phase 1 ingestion already populated raw_* tables — the
       `ingested_athenian_corpus` fixture handles this lazily, idempotently.

The fixtures here:
    * data_root          — absolute path to <repo>/data.
    * athenian_school_id — UUID of the seeded Athenian school row.
    * reset_dim_tables   — TRUNCATE every stg_* + dim_* table CASCADE.
    * ingested_athenian_corpus — runs ingestion if raw_* are empty (idempotent).
    * run_full_pipeline  — convenience: run transformations against a
      fresh-but-ingested DB and return the resulting count snapshot.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.blob_client import LocalBlobClient
from app.jobs.db import dispose_engine, session_scope
from app.jobs.ingest_schoology import run_ingestion
from app.transformations import run_all as run_transformations


DATA_ROOT = Path(__file__).resolve().parents[3] / "data"
ATHENIAN_DIR = DATA_ROOT / "Athenian"


# Skip the entire transformation test suite if the Athenian corpus is missing —
# the dim build cannot be tested without raw data behind it.
pytestmark_athenian_required = pytest.mark.skipif(
    not ATHENIAN_DIR.exists(),
    reason="data/Athenian not present — required for transformation tests",
)


@pytest.fixture(scope="session")
def data_root() -> Path:
    return DATA_ROOT


@pytest.fixture
async def athenian_school_id() -> UUID:
    """Look up Athenian's UUID school_id from the live `schools` table."""
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
async def reset_dim_tables() -> None:
    """TRUNCATE every staging + dim table CASCADE so each test starts clean.

    We do NOT truncate raw_* — those are slow to repopulate and the
    `ingested_athenian_corpus` fixture handles them separately.
    dim_standard + dim_strand are GLOBAL static lookup tables; we leave
    dim_standard alone but allow dim_strand to be rebuilt by transformations
    (it is intentionally TRUNCATE+rebuilt by the dim_strand.sql file — see
    notebook line 1102).
    """
    async with session_scope() as session:
        await session.execute(
            text(
                """
                TRUNCATE TABLE
                    stg_user,
                    stg_question_data,
                    stg_student_submission,
                    stg_submission_summary,
                    dim_school,
                    dim_student,
                    dim_teacher,
                    dim_parent,
                    dim_course,
                    dim_item,
                    dim_question_data,
                    dim_unit_lesson,
                    dim_section,
                    dim_session,
                    dim_grade,
                    dim_assessment_type,
                    dim_subject,
                    fact_student_submission,
                    fact_student_submissions_hash,
                    dim_section_hash,
                    dim_student_hash,
                    cube_grade_summary,
                    cube_school_summary,
                    cube_standard_summary,
                    cube_question_summary,
                    cube_questionincorrectchoice_summary,
                    cube_question_summary_overall,
                    cube_question_summary_overall_by_item,
                    cube_overallperformance_summary,
                    cube_user_summary
                CASCADE
                """
            )
        )


@pytest.fixture
async def ingested_athenian_corpus(athenian_school_id: UUID) -> None:
    """Ensure raw_* tables hold the Athenian corpus.

    Cheap when already loaded (just a count query). Loads once per test
    session via the on-disk `ingested_files` idempotency table.
    """
    if not ATHENIAN_DIR.exists():
        pytest.skip("data/Athenian not present")

    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM raw_student_submission"))
        if r.scalar_one() > 0:
            return  # already ingested in a prior test or run

    bc = LocalBlobClient(data_root=DATA_ROOT)
    summary = await run_ingestion(school_filter="Athenian", blob_client=bc)
    assert summary.error_count == 0, f"ingestion errors: {summary.errors}"


@pytest.fixture
async def transformed_athenian(
    reset_dim_tables: None, ingested_athenian_corpus: None
) -> dict[str, int]:
    """Run transformations against the ingested raw_* tables. Return per-model rowcounts."""
    async with session_scope() as session:
        results = await run_transformations(session)
    return results


@pytest.fixture(autouse=True)
async def _per_test_engine_dispose() -> None:
    """Dispose the asyncpg engine before AND after every test.

    Why per-test:
        On Windows, asyncpg's ProactorEventLoop closes between tests; the
        next test creates a new loop, but our `app.jobs.db._engine` singleton
        still points at connections bound to the dead loop. The first DB
        call in the new loop then fails with
        `AttributeError: 'NoneType' object has no attribute 'send'`.
        Disposing the engine before each test forces a fresh pool on the
        live event loop. The post-yield dispose is for the very last test
        of the session.
    """
    await dispose_engine()
    yield
    await dispose_engine()
