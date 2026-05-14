"""cube_user_summary — per-(section, session, grade, subject, assessment,
user, item, question, standards, school) cube with 6 chained aggregates.

Notebook lines 2278-2483 (40_schoology_py_spec.md §7).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_cube_user_summary_populated(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM cube_user_summary"))
        n = r.scalar_one()
        assert n > 1_000
        assert n < 100_000


async def test_cube_user_summary_pk_uniqueness(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) AS total, count(DISTINCT id) AS distinct_pks
                FROM cube_user_summary
                """
            )
        )
        row = r.one()
        assert row.total == row.distinct_pks


async def test_cube_user_summary_user_name_present(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """user_name should be present on most rows."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT
                    sum(CASE WHEN user_name IS NOT NULL THEN 1 ELSE 0 END) AS named,
                    count(*) AS total
                FROM cube_user_summary
                """
            )
        )
        row = r.one()
        assert row.named > 0.5 * row.total


async def test_cube_user_summary_student_name_hash_present(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """student_name_hash should be set on most rows (joined from dim_student_hash)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) FROM cube_user_summary
                WHERE student_name_hash IS NOT NULL
                """
            )
        )
        with_hash = r.scalar_one()
        r = await session.execute(text("SELECT count(*) FROM cube_user_summary"))
        total = r.scalar_one()
        assert with_hash > 0.5 * total


async def test_cube_user_summary_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM cube_user_summary"))
        before = r.scalar_one()
        await run_transformations(session)
        r = await session.execute(text("SELECT count(*) FROM cube_user_summary"))
        assert r.scalar_one() == before
