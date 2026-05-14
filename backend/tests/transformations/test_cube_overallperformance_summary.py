"""cube_overallperformance_summary — per-(identifier, item, item_name,
question, question_no, standards) totals + averages.

Notebook lines 2192-2273 (40_schoology_py_spec.md §7).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_cube_overallperformance_populated(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text("SELECT count(*) FROM cube_overallperformance_summary")
        )
        n = r.scalar_one()
        assert n > 100
        assert n < 5_000


async def test_cube_overallperformance_pk_uniqueness(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) AS total, count(DISTINCT id) AS distinct_pks
                FROM cube_overallperformance_summary
                """
            )
        )
        row = r.one()
        assert row.total == row.distinct_pks


async def test_cube_overallperformance_grade_average_in_range(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) FROM cube_overallperformance_summary
                WHERE grade_average IS NOT NULL
                  AND (grade_average < 0 OR grade_average > 1)
                """
            )
        )
        assert r.scalar_one() == 0


async def test_cube_overallperformance_standards_other(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """NULL/blank standards must be replaced with 'Other' (notebook §8)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) FROM cube_overallperformance_summary
                WHERE standards IS NULL OR standards IN ('', 'null')
                """
            )
        )
        assert r.scalar_one() == 0


async def test_cube_overallperformance_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        r = await session.execute(
            text("SELECT count(*) FROM cube_overallperformance_summary")
        )
        before = r.scalar_one()
        await run_transformations(session)
        r = await session.execute(
            text("SELECT count(*) FROM cube_overallperformance_summary")
        )
        assert r.scalar_one() == before
