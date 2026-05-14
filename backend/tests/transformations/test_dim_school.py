"""dim_school: one row per school, with school_id_csv + school_name carried from CSV."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_dim_school_row_count(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """Athenian-only ingestion produces exactly 1 dim_school row."""
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM dim_school"))
        assert r.scalar_one() == 1


async def test_dim_school_columns_populated(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """The single dim_school row must have UUID school_id, CSV id, and name."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT school_id, school_id_csv, school_name
                FROM dim_school
                WHERE school_id = :sid
                """
            ),
            {"sid": athenian_school_id},
        )
        row = r.one()
        assert row.school_id == athenian_school_id
        assert row.school_id_csv == "186370968"  # the User_School_ID from CSV
        assert "Athenian" in row.school_name


async def test_dim_school_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """Re-running transformations does not duplicate rows."""
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        await run_transformations(session)
        r = await session.execute(text("SELECT count(*) FROM dim_school"))
        assert r.scalar_one() == 1
