"""Derived dims (dim_unit_lesson, dim_section, dim_session, dim_grade,
dim_assessment_type, dim_subject) — DISTINCT projections of stg_student_submission.

Notebook lines 1135-1176 (40_schoology_py_spec.md §4.7).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_dim_unit_lesson_count_matches_distinct_items(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """dim_unit_lesson PK is item_id; count == distinct (school_id, item_id)
    in stg_student_submission with non-NULL item_id + item_name."""
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM dim_unit_lesson"))
        dim_count = r.scalar_one()

        r = await session.execute(
            text(
                """
                SELECT count(DISTINCT (school_id, item_id))
                FROM stg_student_submission
                WHERE item_id IS NOT NULL AND item_name IS NOT NULL
                """
            )
        )
        stg_count = r.scalar_one()
        assert dim_count == stg_count


async def test_dim_section_required_fields(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """No section row may have NULL on any required field."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) FROM dim_section
                WHERE section_nid         IS NULL
                   OR section_code        IS NULL
                   OR item_id             IS NULL
                   OR section_name        IS NULL
                   OR section_instructors IS NULL
                """
            )
        )
        assert r.scalar_one() == 0


async def test_dim_section_pk_unique(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """(school_id, section_nid) must be unique."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) AS total,
                       count(DISTINCT (school_id, section_nid)) AS distinct_pks
                FROM dim_section
                """
            )
        )
        row = r.one()
        assert row.total == row.distinct_pks


async def test_dim_session_id_is_uuid_2(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """session_id = uuid_2(school_id::text, session) — SHA-256 hex (64 chars)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT session_id, school_id::text AS sid_text, session,
                       uuid_2(school_id::text, session) AS recomputed
                FROM dim_session
                """
            )
        )
        for row in r:
            assert len(row.session_id) == 64
            assert row.session_id == row.recomputed


async def test_dim_grade_id_is_uuid_2(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT grade_id, uuid_2(school_id::text, grade) AS recomputed
                FROM dim_grade
                """
            )
        )
        for row in r:
            assert row.grade_id == row.recomputed


async def test_dim_assessment_type_count_matches_distinct(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """dim_assessment_type count == distinct (school_id, assessment_type)
    in student rows."""
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM dim_assessment_type"))
        dim_count = r.scalar_one()

        r = await session.execute(
            text(
                """
                SELECT count(DISTINCT (school_id, assessment_type))
                FROM stg_student_submission
                WHERE user_role_id = '286170' AND assessment_type IS NOT NULL
                """
            )
        )
        stg_count = r.scalar_one()
        assert dim_count == stg_count


async def test_dim_subject_calculated_columns(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """grade_sort, grade_no, show_history_subject must follow notebook 1170-1175."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT grade, subject, grade_sort, grade_no, show_history_subject
                FROM dim_subject
                LIMIT 50
                """
            )
        )
        for row in r:
            # grade_sort: Grade K -> Grade 0, else passthrough
            if row.grade == "Grade K":
                assert row.grade_sort == "Grade 0"
            else:
                assert row.grade_sort == row.grade
            # grade_no: RIGHT(grade, 1) — last char of the grade string
            assert row.grade_no == row.grade[-1:]
            # show_history_subject: Grade 6/History -> World History; Grade 7/History -> US History
            if row.grade == "Grade 6" and row.subject == "History":
                assert row.show_history_subject == "World History"
            elif row.grade == "Grade 7" and row.subject == "History":
                assert row.show_history_subject == "US History"
            else:
                assert row.show_history_subject == row.subject


async def test_dim_subject_id_is_uuid_6(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """subject_id = uuid_6(school_id, subject, assessment_type, grade, session, item_name)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT subject_id,
                       uuid_6(
                         school_id::text, subject, assessment_type, grade, session, item_name
                       ) AS recomputed
                FROM dim_subject
                """
            )
        )
        for row in r:
            assert row.subject_id == row.recomputed


async def test_derived_dims_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """All six derived dims have identical row counts after a re-run."""
    from app.transformations import run_all as run_transformations

    tables = (
        "dim_unit_lesson",
        "dim_section",
        "dim_session",
        "dim_grade",
        "dim_assessment_type",
        "dim_subject",
    )
    async with session_scope() as session:
        before = {}
        for t in tables:
            r = await session.execute(text(f"SELECT count(*) FROM {t}"))
            before[t] = r.scalar_one()

        await run_transformations(session)

        for t in tables:
            r = await session.execute(text(f"SELECT count(*) FROM {t}"))
            assert r.scalar_one() == before[t], f"{t} count drifted on re-run"
