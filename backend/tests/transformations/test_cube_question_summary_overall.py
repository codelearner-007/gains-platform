"""cube_question_summary_overall — per-(subject, question, position, correct,
standard) latest-attempt rollup with incorrect-choice analysis.

Notebook lines 1953-2189 (40_schoology_py_spec.md §7).

The notebook uses the buggy hash that includes Standards twice; we use ukey
per the D1 fix in the user's plan.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_cube_qso_populated(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text("SELECT count(*) FROM cube_question_summary_overall")
        )
        n = r.scalar_one()
        assert n > 100
        assert n < 5_000


async def test_cube_qso_pk_uniqueness(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) AS total, count(DISTINCT id) AS distinct_pks
                FROM cube_question_summary_overall
                """
            )
        )
        row = r.one()
        assert row.total == row.distinct_pks


async def test_cube_qso_question_no_url_strips_html(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) FROM cube_question_summary_overall
                WHERE question_no_url ~ '<[^>]+>'
                """
            )
        )
        assert r.scalar_one() == 0


async def test_cube_qso_grade_average_in_range(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) FROM cube_question_summary_overall
                WHERE grade_average IS NOT NULL
                  AND (grade_average < 0 OR grade_average > 1)
                """
            )
        )
        assert r.scalar_one() == 0


async def test_cube_qso_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        r = await session.execute(
            text("SELECT count(*) FROM cube_question_summary_overall")
        )
        before = r.scalar_one()
        await run_transformations(session)
        r = await session.execute(
            text("SELECT count(*) FROM cube_question_summary_overall")
        )
        assert r.scalar_one() == before
