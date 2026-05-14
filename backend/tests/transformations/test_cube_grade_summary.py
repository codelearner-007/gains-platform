"""cube_grade_summary — per-(school, subject, item) grade rollup.

Notebook lines 1337-1366 (40_schoology_py_spec.md §7).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_cube_grade_summary_populated(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM cube_grade_summary"))
        n = r.scalar_one()
        assert n > 0
        assert n < 5_000, f"cube_grade_summary count {n} too high"


async def test_cube_grade_summary_pk_uniqueness(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) AS total, count(DISTINCT id) AS distinct_pks
                FROM cube_grade_summary
                """
            )
        )
        row = r.one()
        assert row.total == row.distinct_pks


async def test_cube_grade_summary_grade_average_in_range(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """grade_average should be in [0, 1] for every row that has a value."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*)
                FROM cube_grade_summary
                WHERE grade_average IS NOT NULL
                  AND (grade_average < 0 OR grade_average > 1)
                """
            )
        )
        assert r.scalar_one() == 0


async def test_cube_grade_summary_grade_min_le_max(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """grade_min <= grade_max for every row with both values."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*)
                FROM cube_grade_summary
                WHERE grade_min IS NOT NULL AND grade_max IS NOT NULL
                  AND grade_min > grade_max
                """
            )
        )
        assert r.scalar_one() == 0


async def test_cube_grade_summary_id_is_sha256(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(text("SELECT id FROM cube_grade_summary LIMIT 5"))
        for row in r:
            assert len(row.id) == 64
            int(row.id, 16)


async def test_cube_grade_summary_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM cube_grade_summary"))
        before = r.scalar_one()
        await run_transformations(session)
        r = await session.execute(text("SELECT count(*) FROM cube_grade_summary"))
        assert r.scalar_one() == before
