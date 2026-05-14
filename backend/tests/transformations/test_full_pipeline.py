"""Integration test: ingestion -> transformations -> dim row counts."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.blob_client import LocalBlobClient
from app.jobs.db import session_scope
from app.jobs.ingest_schoology import run_ingestion


pytestmark = pytest.mark.asyncio

DATA_ROOT = Path(__file__).resolve().parents[3] / "data"
ATHENIAN_DIR = DATA_ROOT / "Athenian"


# Floor counts derived from the Athenian-only Phase 2 spec (see task brief).
# Hard pinned counts where the data is fully deterministic; floor + ceiling
# elsewhere (e.g. dim_question_data is data-volume-dependent).
ATHENIAN_DIM_EXPECTED: dict[str, tuple[int, int | None]] = {
    # (min_inclusive, max_inclusive). max=None means unbounded.
    "dim_school":          (1, 1),
    "dim_student":         (300, 700),
    "dim_teacher":         (0, 0),    # raw_user empty in Phase 2
    "dim_parent":          (0, 0),
    "dim_course":          (10, 100),
    "dim_item":            (33, 33),
    "dim_question_data":   (300, None),
    "dim_strand":          (1, None),
    "dim_unit_lesson":     (33, 33),
    "dim_section":         (20, 60),
    "dim_session":         (1, 1),
    "dim_grade":           (5, 12),
    "dim_assessment_type": (1, 1),
    "dim_subject":         (15, 100),
    # Phase 3 — fact + hash + cubes.
    "fact_student_submission":              (10_000, 50_000),
    "fact_student_submissions_hash":        (10_000, 50_000),
    "dim_section_hash":                     (20, 60),
    "dim_student_hash":                     (200, 500),
    "cube_grade_summary":                   (1, 5_000),
    "cube_school_summary":                  (1, 5_000),
    "cube_standard_summary":                (1, 5_000),
    "cube_question_summary":                (100, 5_000),
    "cube_questionincorrectchoice_summary": (100, 100_000),
    "cube_question_summary_overall":        (100, 5_000),
    "cube_overallperformance_summary":      (100, 5_000),
    "cube_user_summary":                    (1_000, 100_000),
}


@pytest.mark.skipif(not ATHENIAN_DIR.exists(), reason="data/Athenian not present")
async def test_full_ingestion_then_transformations(
    athenian_school_id: UUID,
) -> None:
    """End-to-end: TRUNCATE everything, ingest, transform, verify counts.

    Cleans every raw + stg + dim table first so this test is deterministic.
    Reuses the production orchestrator (run_ingestion) which now calls
    `run_transformations` at the end of phase 2.
    """
    async with session_scope() as session:
        # Truncate every domain table CASCADE so nothing survives from prior tests.
        await session.execute(
            text(
                """
                TRUNCATE TABLE
                    raw_submission_summary,
                    raw_student_submission,
                    raw_question_data,
                    ingested_files,
                    ingestion_runs,
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
                    cube_overallperformance_summary,
                    cube_user_summary
                RESTART IDENTITY CASCADE
                """
            )
        )

    bc = LocalBlobClient(data_root=DATA_ROOT)
    summary = await run_ingestion(school_filter="Athenian", blob_client=bc)
    assert summary.error_count == 0, f"ingestion errors: {summary.errors}"
    assert summary.rows_inserted > 25_000

    # Verify dim row counts fall within expected ranges.
    async with session_scope() as session:
        for table, (lo, hi) in ATHENIAN_DIM_EXPECTED.items():
            r = await session.execute(text(f"SELECT count(*) FROM {table}"))
            n = r.scalar_one()
            assert n >= lo, f"{table} count {n} < lower bound {lo}"
            if hi is not None:
                assert n <= hi, f"{table} count {n} > upper bound {hi}"


@pytest.mark.skipif(not ATHENIAN_DIR.exists(), reason="data/Athenian not present")
async def test_pipeline_idempotent_end_to_end(
    athenian_school_id: UUID,
) -> None:
    """Running the full ingestion + transformations TWICE leaves dim counts
    unchanged (modulo: ingestion_runs count grows by 1 each time)."""
    bc = LocalBlobClient(data_root=DATA_ROOT)

    # First run (in case the previous test didn't run / DB started empty).
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM dim_school"))
        if r.scalar_one() == 0:
            await run_ingestion(school_filter="Athenian", blob_client=bc)

    # Snapshot dim counts.
    tables = list(ATHENIAN_DIM_EXPECTED.keys())
    async with session_scope() as session:
        before = {}
        for t in tables:
            r = await session.execute(text(f"SELECT count(*) FROM {t}"))
            before[t] = r.scalar_one()

    # Re-run.
    summary = await run_ingestion(school_filter="Athenian", blob_client=bc)
    # All Athenian files should be in `ingested_files` already → 105 skips.
    assert summary.files_skipped == 105
    assert summary.files_processed == 0

    # Snapshot again — counts must be identical.
    async with session_scope() as session:
        for t in tables:
            r = await session.execute(text(f"SELECT count(*) FROM {t}"))
            after = r.scalar_one()
            assert after == before[t], f"{t}: before={before[t]} after={after}"
