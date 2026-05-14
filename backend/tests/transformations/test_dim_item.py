"""dim_item — first-occurrence per item by earliest assessment_date.

Notebook lines 925-944 (40_schoology_py_spec.md §4.4):
    1. Synthetic Subject_ID = uuid_6(school_id, subject, assessment_type, grade,
       session, item_name)
    2. Filter rows to user_role_id == '286170' (students)
    3. drop_duplicates + dropna on the 8 dim columns
    4. Window: PARTITION BY (Item_ID, Subject_ID, Section_Name,
       Section_Instructors, Item_Type, Item_Name, School_ID)
       ORDER BY assessment_date ASC -> keep ROW_NUMBER = 1
    5. PK Item_ID
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_dim_item_count_equals_distinct_items(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """dim_item count == distinct item_id in student rows (the unique-per-PK
    grain). The Athenian corpus has exactly 33 distinct items.
    """
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM dim_item"))
        dim_count = r.scalar_one()

        r = await session.execute(
            text(
                """
                SELECT count(DISTINCT item_id)
                FROM stg_student_submission
                WHERE user_role_id = '286170'
                  AND item_id IS NOT NULL
                """
            )
        )
        stg_count = r.scalar_one()

        # dim_item is keyed on (school_id, item_id) and dedupes on the
        # 7-tuple partition key. dim_count <= stg_count by construction.
        assert dim_count == 33, f"Athenian corpus expected 33 items, got {dim_count}"
        assert dim_count == stg_count


async def test_dim_item_subject_id_format(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """subject_id must be the SHA-256 hex of the 6-tuple — uuid_6 produces a
    64-char hex string."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT subject_id
                FROM dim_item
                WHERE subject_id IS NOT NULL
                LIMIT 5
                """
            )
        )
        for row in r:
            assert len(row.subject_id) == 64
            int(row.subject_id, 16)  # raises ValueError if not hex


async def test_dim_item_first_occurrence_kept(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """For an item that appears with multiple latest_attempt dates across
    students, dim_item.assessment_date must be the EARLIEST."""
    async with session_scope() as session:
        # Pick an item_id that has multiple distinct latest_attempt dates.
        r = await session.execute(
            text(
                """
                SELECT item_id, MIN(to_char(latest_attempt, 'MM/DD/YYYY')) AS earliest
                FROM stg_student_submission
                WHERE user_role_id = '286170' AND latest_attempt IS NOT NULL
                GROUP BY item_id
                HAVING count(DISTINCT to_char(latest_attempt, 'MM/DD/YYYY')) > 1
                LIMIT 1
                """
            )
        )
        row = r.first()
        if row is None:
            pytest.skip("no item with multiple distinct latest_attempt dates")

        r = await session.execute(
            text(
                """
                SELECT to_char(assessment_date, 'MM/DD/YYYY') AS d
                FROM dim_item
                WHERE item_id = :iid
                """
            ),
            {"iid": row.item_id},
        )
        # Note: the notebook sorts on the MM/DD/YYYY STRING (not the date),
        # so we compare on the same string format.
        dim_date_str = r.scalar_one()
        # The dim row should be the lexically-earliest MM/DD/YYYY string —
        # which is also the date-earliest for any single year. Athenian's
        # corpus is all 2025-26 so MM/DD lexical order = chronological.
        assert dim_date_str == row.earliest


async def test_dim_item_only_students(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """dim_item is built ONLY from user_role_id='286170' rows (notebook 924-927).
    Athenian's CSVs only contain student rows so this is a smoke test that
    nothing else accidentally crept in."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*)
                FROM dim_item d
                LEFT JOIN stg_student_submission s
                  ON s.school_id = d.school_id AND s.item_id = d.item_id
                  AND s.user_role_id = '286170'
                WHERE s.item_id IS NULL
                """
            )
        )
        unmapped = r.scalar_one()
        assert unmapped == 0


async def test_dim_item_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """Re-running produces identical rows including identical subject_ids
    (deterministic UUID composition)."""
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        r = await session.execute(
            text("SELECT item_id, subject_id FROM dim_item ORDER BY item_id")
        )
        before = [(row.item_id, row.subject_id) for row in r]

        await run_transformations(session)

        r = await session.execute(
            text("SELECT item_id, subject_id FROM dim_item ORDER BY item_id")
        )
        after = [(row.item_id, row.subject_id) for row in r]
        assert before == after
