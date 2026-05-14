"""cube_school_summary — per-(school, subject, item) totals + averages.

Notebook lines 1367-1391 (40_schoology_py_spec.md §7).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_cube_school_summary_populated(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM cube_school_summary"))
        n = r.scalar_one()
        assert n > 0
        assert n < 5_000


async def test_cube_school_summary_pk_uniqueness(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) AS total, count(DISTINCT id) AS distinct_pks
                FROM cube_school_summary
                """
            )
        )
        row = r.one()
        assert row.total == row.distinct_pks


async def test_cube_school_summary_metrics_consistent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """grade_average == total_score / total_possible_point (within float tolerance)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*)
                FROM cube_school_summary
                WHERE total_possible_point > 0
                  AND grade_average IS NOT NULL
                  AND ABS(grade_average - (total_score / total_possible_point)) > 0.0001
                """
            )
        )
        assert r.scalar_one() == 0


async def test_cube_school_summary_percentage_complement(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """percentage_incorrect_answers == 1 - grade_average."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*)
                FROM cube_school_summary
                WHERE grade_average IS NOT NULL
                  AND percentage_incorrect_answers IS NOT NULL
                  AND ABS(percentage_incorrect_answers - (1 - grade_average)) > 0.0001
                """
            )
        )
        assert r.scalar_one() == 0


async def test_cube_school_summary_total_students_positive(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text("SELECT count(*) FROM cube_school_summary WHERE total_students <= 0")
        )
        assert r.scalar_one() == 0


async def test_cube_school_summary_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM cube_school_summary"))
        before = r.scalar_one()
        await run_transformations(session)
        r = await session.execute(text("SELECT count(*) FROM cube_school_summary"))
        assert r.scalar_one() == before
