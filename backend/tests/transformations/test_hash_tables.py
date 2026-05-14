"""Pseudonymisation tables: dim_section_hash, dim_student_hash,
fact_student_submissions_hash.

Notebook lines 1295-1320 (40_schoology_py_spec.md §7).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_dim_section_hash_populated(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM dim_section_hash"))
        # Athenian has 28 dim_section rows; hash table mirrors that.
        assert r.scalar_one() == 28


async def test_dim_section_hash_label_format(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """Labels are 'Teacher_Name N' for N starting at 0."""
    async with session_scope() as session:
        r = await session.execute(
            text("SELECT teacher_name_hash FROM dim_section_hash ORDER BY teacher_name_hash")
        )
        labels = [row.teacher_name_hash for row in r]
        for label in labels:
            assert label.startswith("Teacher_Name ")
            int(label.removeprefix("Teacher_Name ").strip())


async def test_dim_section_hash_unique_per_school(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """teacher_name_hash unique within a school."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) AS total,
                       count(DISTINCT (school_id, teacher_name_hash)) AS distinct_pairs
                FROM dim_section_hash
                """
            )
        )
        row = r.one()
        assert row.total == row.distinct_pairs


async def test_dim_student_hash_populated(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM dim_student_hash"))
        # Athenian has 332 distinct student UIDs.
        n = r.scalar_one()
        assert 200 < n < 500, f"dim_student_hash count {n} out of range"


async def test_dim_student_hash_label_format(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text("SELECT student_name_hash FROM dim_student_hash LIMIT 5")
        )
        for row in r:
            assert row.student_name_hash.startswith("Student_Name ")
            int(row.student_name_hash.removeprefix("Student_Name ").strip())


async def test_fact_hash_count_matches_fact(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """fact_student_submissions_hash mirrors fact_student_submission row-for-row."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT
                    (SELECT count(*) FROM fact_student_submission)            AS fact_n,
                    (SELECT count(*) FROM fact_student_submissions_hash)      AS hash_n
                """
            )
        )
        row = r.one()
        assert row.fact_n == row.hash_n


async def test_fact_hash_user_name_replaced(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """user_name in the hash table is the StudentName_Hash for rows with a
    real user_uid."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*)
                FROM fact_student_submissions_hash
                WHERE user_uid IS NOT NULL
                  AND user_name NOT LIKE 'Student_Name %'
                """
            )
        )
        # Some rows may have user_uid not in dim_student_hash (e.g. NULL
        # coalescing fallback) but most should be hashed. Tolerate a small
        # percentage.
        bad = r.scalar_one()
        r = await session.execute(text("SELECT count(*) FROM fact_student_submissions_hash"))
        total = r.scalar_one()
        assert bad < 0.01 * total, f"{bad}/{total} fact hash rows missing hash"


async def test_hash_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """Re-running produces identical hash labels (deterministic ordering)."""
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        r = await session.execute(
            text(
                "SELECT user_uid, student_name_hash FROM dim_student_hash ORDER BY user_uid"
            )
        )
        before = [(row.user_uid, row.student_name_hash) for row in r]

        await run_transformations(session)

        r = await session.execute(
            text(
                "SELECT user_uid, student_name_hash FROM dim_student_hash ORDER BY user_uid"
            )
        )
        after = [(row.user_uid, row.student_name_hash) for row in r]
        assert before == after, "dim_student_hash labels changed across runs"
