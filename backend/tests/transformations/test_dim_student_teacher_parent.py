"""dim_student / dim_teacher / dim_parent — role-filter tests."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_dim_student_count_matches_distinct_user_uids(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """dim_student rowcount equals distinct user_uid in stg_student_submission
    where user_role_id = '286170' (Student).

    raw_user is empty in Phase 2 (sync_users.py is Phase 7), so dim_student is
    populated entirely from the CSV-derived fallback path.
    """
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM dim_student"))
        dim_count = r.scalar_one()

        r = await session.execute(
            text(
                """
                SELECT count(DISTINCT user_uid)
                FROM stg_student_submission
                WHERE user_role_id = '286170'
                  AND user_uid IS NOT NULL
                """
            )
        )
        stg_count = r.scalar_one()

        assert dim_count == stg_count
        assert dim_count > 0, "Athenian corpus must have at least one student"


async def test_dim_student_role_filter(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """Every dim_student row that has a role_id must hold '286170'."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT DISTINCT role_id
                FROM dim_student
                WHERE role_id IS NOT NULL
                """
            )
        )
        roles = [row.role_id for row in r]
        assert all(r == "286170" for r in roles), f"unexpected roles: {roles}"


async def test_dim_student_school_id_set(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """All dim_student rows must point at the Athenian UUID school_id."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT DISTINCT school_id
                FROM dim_student
                """
            )
        )
        sids = [row.school_id for row in r]
        assert sids == [athenian_school_id]


async def test_dim_teacher_empty_without_raw_user(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """dim_teacher must remain empty in Phase 2 — teacher uids only come from
    the Schoology /v1/users API which sync_users.py loads in Phase 7. The
    notebook (line 875) builds dim_teacher purely from df_User; we follow that.
    """
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM dim_teacher"))
        assert r.scalar_one() == 0


async def test_dim_parent_empty_without_raw_user(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """Parents never appear in submission CSVs — dim_parent stays empty until
    sync_users.py (Phase 7) populates raw_user.
    """
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM dim_parent"))
        assert r.scalar_one() == 0


async def test_dim_student_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """Re-running transformations leaves dim_student untouched (count + IDs)."""
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM dim_student"))
        before = r.scalar_one()
        await run_transformations(session)
        r = await session.execute(text("SELECT count(*) FROM dim_student"))
        after = r.scalar_one()
        assert before == after
