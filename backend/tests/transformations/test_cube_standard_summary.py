"""cube_standard_summary — per-(item, strand, identifier) rollup.

Notebook lines 1392-1416 (40_schoology_py_spec.md §7).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_cube_standard_summary_populated(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM cube_standard_summary"))
        n = r.scalar_one()
        assert n > 0
        assert n < 5_000


async def test_cube_standard_summary_pk_uniqueness(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) AS total, count(DISTINCT id) AS distinct_pks
                FROM cube_standard_summary
                """
            )
        )
        row = r.one()
        assert row.total == row.distinct_pks


async def test_cube_standard_summary_grade_average_in_range(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*)
                FROM cube_standard_summary
                WHERE grade_average IS NOT NULL
                  AND (grade_average < 0 OR grade_average > 1)
                """
            )
        )
        assert r.scalar_one() == 0


async def test_cube_standard_summary_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM cube_standard_summary"))
        before = r.scalar_one()
        await run_transformations(session)
        r = await session.execute(text("SELECT count(*) FROM cube_standard_summary"))
        assert r.scalar_one() == before
