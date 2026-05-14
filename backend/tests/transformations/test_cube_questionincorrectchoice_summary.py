"""cube_questionincorrectchoice_summary — per-(question, ukey, answer)
rollup of student counts and points.

Notebook lines 1772-1798 (40_schoology_py_spec.md §7).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_cube_qic_populated(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text("SELECT count(*) FROM cube_questionincorrectchoice_summary")
        )
        n = r.scalar_one()
        assert n > 100
        assert n < 100_000


async def test_cube_qic_pk_uniqueness(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) AS total, count(DISTINCT id) AS distinct_pks
                FROM cube_questionincorrectchoice_summary
                """
            )
        )
        row = r.one()
        assert row.total == row.distinct_pks


async def test_cube_qic_total_student_positive(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """total_student should be > 0 on every row."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) FROM cube_questionincorrectchoice_summary
                WHERE total_student <= 0
                """
            )
        )
        assert r.scalar_one() == 0


async def test_cube_qic_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        r = await session.execute(
            text("SELECT count(*) FROM cube_questionincorrectchoice_summary")
        )
        before = r.scalar_one()
        await run_transformations(session)
        r = await session.execute(
            text("SELECT count(*) FROM cube_questionincorrectchoice_summary")
        )
        assert r.scalar_one() == before
