"""cube_question_summary — per-(item, question, position, standard, correct
answer) totals plus incorrect-choice analysis.

Notebook lines 1581-1771 (40_schoology_py_spec.md §7).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_cube_question_summary_populated(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM cube_question_summary"))
        n = r.scalar_one()
        assert n > 100
        assert n < 5_000


async def test_cube_question_summary_pk_uniqueness(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) AS total, count(DISTINCT id) AS distinct_pks
                FROM cube_question_summary
                """
            )
        )
        row = r.one()
        assert row.total == row.distinct_pks


async def test_cube_question_summary_question_no_url_strips_html(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """question_no_url has no HTML tags (notebook 1727)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) FROM cube_question_summary
                WHERE question_no_url ~ '<[^>]+>'
                """
            )
        )
        assert r.scalar_one() == 0


async def test_cube_question_summary_incorrect_choice_format(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """incorrect_choice_details, when present, should contain '%' and 'chose'."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) FROM cube_question_summary
                WHERE incorrect_choice_details IS NOT NULL
                  AND incorrect_choice_details NOT LIKE '%chose%'
                """
            )
        )
        assert r.scalar_one() == 0


async def test_cube_question_summary_grade_average_in_range(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) FROM cube_question_summary
                WHERE grade_average IS NOT NULL
                  AND (grade_average < 0 OR grade_average > 1)
                """
            )
        )
        assert r.scalar_one() == 0


async def test_cube_question_summary_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM cube_question_summary"))
        before = r.scalar_one()
        await run_transformations(session)
        r = await session.execute(text("SELECT count(*) FROM cube_question_summary"))
        assert r.scalar_one() == before
