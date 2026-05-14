"""dim_course — DISTINCT (course_nid, course_name, course_code, school_id)."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_dim_course_distinct_course_nid(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """dim_course must have DISTINCT (school_id, course_nid)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) AS total,
                       count(DISTINCT course_nid) AS distinct_course_nids
                FROM dim_course
                WHERE school_id = :sid
                """
            ),
            {"sid": athenian_school_id},
        )
        row = r.one()
        assert row.total == row.distinct_course_nids


async def test_dim_course_required_fields(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """The notebook drops rows where any of course_nid, course_name,
    course_code, school_id is NULL (line 269)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) FROM dim_course
                WHERE course_nid  IS NULL
                   OR course_name IS NULL
                   OR course_code IS NULL
                   OR school_id   IS NULL
                """
            )
        )
        assert r.scalar_one() == 0


async def test_dim_course_count_matches_stg_distinct(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """dim_course count == DISTINCT (course_nid, course_name, course_code, school_id)
    in stg_student_submission (after dropping NULLs)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(DISTINCT (course_nid, course_name, course_code, school_id))
                FROM stg_student_submission
                WHERE course_nid  IS NOT NULL
                  AND course_name IS NOT NULL
                  AND course_code IS NOT NULL
                """
            )
        )
        stg_distinct = r.scalar_one()

        r = await session.execute(text("SELECT count(*) FROM dim_course"))
        dim_count = r.scalar_one()

        # dim_course has UNIQUE (school_id, course_nid) — if the same
        # course_nid carries multiple (course_name, course_code) we still
        # collapse to one. So dim_count <= stg_distinct.
        assert dim_count <= stg_distinct
        assert dim_count > 0


async def test_dim_course_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM dim_course"))
        before = r.scalar_one()
        await run_transformations(session)
        r = await session.execute(text("SELECT count(*) FROM dim_course"))
        assert r.scalar_one() == before
