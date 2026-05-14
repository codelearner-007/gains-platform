"""dim_strand — TRUNCATE+rebuild from dim_question_data ⨝ dim_standard.

Notebook lines 1102-1128 (40_schoology_py_spec.md §4.6).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_dim_strand_has_rows(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """At least one strand row must be produced — otherwise the substring
    join in dim_strand.sql is broken or dim_question_data is empty."""
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM dim_strand"))
        assert r.scalar_one() > 0


async def test_dim_strand_no_duplicates_on_identifier_strand(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """The dedupe rule (notebook line 1104) is dropDuplicates on
    (Identifier, Strand). Verify our DISTINCT picks the same."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) AS total,
                       count(DISTINCT (identifier, strand)) AS distinct_pairs
                FROM dim_strand
                """
            )
        )
        row = r.one()
        assert row.total == row.distinct_pairs


async def test_dim_strand_id_is_sequential(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """`id` is ROW_NUMBER OVER (ORDER BY identifier, strand) — a 1..N sequence
    over the rebuilt rows."""
    async with session_scope() as session:
        r = await session.execute(
            text("SELECT id FROM dim_strand ORDER BY id")
        )
        ids = [row.id for row in r]
        assert ids == list(range(1, len(ids) + 1))


async def test_dim_strand_strand_id_is_uuid_2(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """strand_id == uuid_2(identifier, strand) — sha256 hex of 'identifier_strand'."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT strand_id, uuid_2(identifier, strand) AS recomputed
                FROM dim_strand
                LIMIT 10
                """
            )
        )
        for row in r:
            assert row.strand_id == row.recomputed


async def test_dim_strand_truncate_rebuild_is_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """dim_strand uses TRUNCATE+INSERT. The IDENTITY restarts each run, so the
    `id` BIGINT column resets to 1..N. After two runs, count is unchanged."""
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM dim_strand"))
        before = r.scalar_one()
        await run_transformations(session)
        r = await session.execute(text("SELECT count(*) FROM dim_strand"))
        assert r.scalar_one() == before


async def test_dim_strand_pk_restarts(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """dim_strand_pk IDENTITY must restart from 1 on every run since
    dim_strand.sql does TRUNCATE ... RESTART IDENTITY."""
    async with session_scope() as session:
        r = await session.execute(
            text("SELECT MIN(dim_strand_pk) AS lo, MAX(dim_strand_pk) AS hi FROM dim_strand")
        )
        row = r.one()
        assert row.lo == 1
        assert row.hi == row.lo + 0 + (
            (await (await session.execute(text("SELECT count(*) FROM dim_strand"))).scalar_one()) - 1
        ) if False else True
        # Simpler: lo == 1 and hi == count.
        r = await session.execute(text("SELECT count(*) FROM dim_strand"))
        n = r.scalar_one()
        r = await session.execute(text("SELECT MAX(dim_strand_pk) FROM dim_strand"))
        assert r.scalar_one() == n
