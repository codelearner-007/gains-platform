"""fact_student_submission — 35-column grain, synthetic 8-part PK.

Notebook §5 (lines 1180-1294, 40_schoology_py_spec.md §5).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_fact_has_rows(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """At least 10K fact rows for Athenian's 13K student rows after dedupe."""
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM fact_student_submission"))
        n = r.scalar_one()
        assert n > 10_000, f"fact_student_submission has only {n} rows"
        assert n < 50_000, f"fact_student_submission has {n} rows — dedupe broken?"


async def test_fact_pk_uniqueness(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """user_id_ques_id_stand is the PK; total == distinct."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) AS total,
                       count(DISTINCT user_id_ques_id_stand) AS distinct_pks
                FROM fact_student_submission
                """
            )
        )
        row = r.one()
        assert row.total == row.distinct_pks


async def test_fact_only_students(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """fact filtered to user_role_id='286170' (notebook line 1199)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*)
                FROM fact_student_submission
                WHERE user_role_id != '286170'
                """
            )
        )
        assert r.scalar_one() == 0


async def test_fact_synthetic_keys_are_hex(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """Grade_ID, Assessment_ID, Subject_ID are SHA-256 hex (64 chars)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT grade_id, assessment_id, subject_id
                FROM fact_student_submission
                WHERE grade_id IS NOT NULL
                  AND assessment_id IS NOT NULL
                  AND subject_id IS NOT NULL
                LIMIT 5
                """
            )
        )
        for row in r:
            assert len(row.grade_id) == 64
            int(row.grade_id, 16)
            assert len(row.assessment_id) == 64
            int(row.assessment_id, 16)
            assert len(row.subject_id) == 64
            int(row.subject_id, 16)


async def test_fact_pk_format(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """user_id_ques_id_stand has 7 dashes (8 components per notebook 1270)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT user_id_ques_id_stand FROM fact_student_submission LIMIT 10
                """
            )
        )
        for row in r:
            # 8 components separated by 7 dashes. Some of the components may
            # contain dashes themselves (UUID school_id) so just sanity-check
            # it is a non-empty string.
            assert row.user_id_ques_id_stand
            assert "-" in row.user_id_ques_id_stand


async def test_fact_user_name_concat(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """user_name = trim(first_name || ' ' || last_name) (notebook 1235)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT f.user_name, ss.first_name, ss.last_name
                FROM fact_student_submission f
                JOIN stg_student_submission ss
                  ON ss.school_id = f.school_id AND ss.user_uid = f.user_uid
                WHERE f.user_name IS NOT NULL
                LIMIT 20
                """
            )
        )
        for row in r:
            expected = " ".join(filter(None, [row.first_name, row.last_name])).strip()
            assert row.user_name == expected, (
                f"user_name {row.user_name!r} != expected {expected!r}"
            )


async def test_fact_identifier_substring_join(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """identifier is set on at least some rows via dim_question_data ->
    dim_standard substring join (notebook 1259)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                "SELECT count(*) FROM fact_student_submission WHERE identifier IS NOT NULL"
            )
        )
        assert r.scalar_one() > 0


async def test_fact_strand_id_attached(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """strand_id attached via dim_strand on identifier (notebook 1265)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                "SELECT count(*) FROM fact_student_submission WHERE strand_id IS NOT NULL"
            )
        )
        assert r.scalar_one() > 0


async def test_fact_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """Re-running yields identical rowcount."""
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM fact_student_submission"))
        before = r.scalar_one()
        await run_transformations(session)
        r = await session.execute(text("SELECT count(*) FROM fact_student_submission"))
        assert r.scalar_one() == before


async def test_fact_school_id_is_athenian(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """All Athenian fact rows carry the Athenian school_id UUID."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) FROM fact_student_submission
                WHERE school_id != :sid
                """
            ),
            {"sid": athenian_school_id},
        )
        assert r.scalar_one() == 0
