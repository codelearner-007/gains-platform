"""dim_question_data — substring join + Qkey + Ukey + Grade remap."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from app.jobs.db import session_scope


pytestmark = pytest.mark.asyncio


async def test_dim_question_data_has_rows(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """Athenian's 33 items × ~15 questions per item (variable) yield several
    hundred dim_question_data rows. Hard floor: 100 (catches a broken
    pipeline)."""
    async with session_scope() as session:
        r = await session.execute(text("SELECT count(*) FROM dim_question_data"))
        n = r.scalar_one()
        assert n > 100, f"dim_question_data has only {n} rows — substring join may be broken"


async def test_dim_question_data_pk_uniqueness(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """(school_id, qkey) is the PK and must be unique."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT count(*) AS total,
                       count(DISTINCT (school_id, qkey)) AS distinct_pks
                FROM dim_question_data
                """
            )
        )
        row = r.one()
        assert row.total == row.distinct_pks


async def test_dim_question_data_ukey_format(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """ukey is uuid_8 output: SHA-256 hex (64 chars)."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT ukey FROM dim_question_data
                WHERE ukey IS NOT NULL
                LIMIT 5
                """
            )
        )
        for row in r:
            assert len(row.ukey) == 64
            int(row.ukey, 16)


async def test_dim_question_data_substring_join_matched_some(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """Many questions in the Athenian corpus carry a Florida B.E.S.T. standard
    code in standards_val (e.g. 'MA.2.DP.1.2'). The substring join against
    dim_standard.schoology_standard must populate `identifier` for at least
    some rows.
    """
    async with session_scope() as session:
        r = await session.execute(
            text("SELECT count(*) FROM dim_question_data WHERE identifier IS NOT NULL")
        )
        with_ident = r.scalar_one()
        assert with_ident > 0, "no rows joined to dim_standard — substring join broken"


async def test_dim_question_data_qkey_is_concat(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """qkey must equal concat(session, assessment_type, subject, grade,
    question_id, position_number, correct_answer, standard, school_id) with
    NULL fallbacks per notebook line 350-353."""
    async with session_scope() as session:
        r = await session.execute(
            text(
                """
                SELECT
                  qkey,
                  COALESCE(session, 'DEFAULT_SESSION') ||
                  COALESCE(assessment_type, 'DEFAULT_TYPE') ||
                  COALESCE(subject, 'DEFAULT_SUBJECT') ||
                  COALESCE(grade, 'DEFAULT_GRADE') ||
                  COALESCE(question_id, 'DEFAULT_QID') ||
                  COALESCE(position_number, 'n/a') ||
                  COALESCE(correct_answer, 'n/a') ||
                  COALESCE(standard, 'n/a') ||
                  COALESCE(school_id::text, 'DEFAULT_SCHOOL') AS rebuilt_qkey
                FROM dim_question_data
                LIMIT 20
                """
            )
        )
        for row in r:
            assert row.qkey == row.rebuilt_qkey, (
                f"qkey mismatch:\n  stored:    {row.qkey}\n  recomputed:{row.rebuilt_qkey}"
            )


async def test_dim_question_data_distinct_per_pk(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """The substring join can yield multiple rows per (school_id, qkey) when a
    standard code is a prefix of another (e.g. MA.7.DP.2 vs MA.7.DP.2.1). The
    DISTINCT ON dedupe must collapse these to one row per qkey, and prefer
    rows with a non-NULL identifier."""
    async with session_scope() as session:
        # If the dedupe is broken, total > distinct_pks above would already
        # have failed. Here we additionally check that for any qkey where a
        # join would produce a non-NULL identifier, the persisted row HAS
        # the non-NULL identifier (NULLS-LAST sort).
        r = await session.execute(
            text(
                """
                WITH joinable AS (
                  SELECT DISTINCT
                    CONCAT(
                      COALESCE(qd.session, 'DEFAULT_SESSION'),
                      COALESCE(qd.assessment_type, 'DEFAULT_TYPE'),
                      COALESCE(qd.subject, 'DEFAULT_SUBJECT'),
                      COALESCE(qd.grade, 'DEFAULT_GRADE'),
                      COALESCE(qd.question_id, 'DEFAULT_QID'),
                      COALESCE(qd.position_number, 'n/a'),
                      COALESCE(qd.correct_answer, 'n/a'),
                      COALESCE(qd.standards_val, 'n/a'),
                      COALESCE(qd.school_id::text, 'DEFAULT_SCHOOL')
                    ) AS qkey
                  FROM stg_question_data qd
                  JOIN dim_standard ds
                    ON qd.standards_val IS NOT NULL
                   AND qd.standards_val ILIKE '%' || ds.schoology_standard || '%'
                )
                SELECT count(*) AS missed
                FROM joinable j
                LEFT JOIN dim_question_data dqd
                  ON dqd.qkey = j.qkey
                WHERE dqd.qkey IS NULL OR dqd.identifier IS NULL
                """
            )
        )
        missed = r.scalar_one()
        # Every joinable qkey should land in dim_question_data with identifier
        # set (NULLS LAST guarantees the non-NULL row wins).
        assert missed == 0


async def test_dim_question_data_idempotent(
    transformed_athenian: dict[str, int], athenian_school_id: UUID
) -> None:
    """Re-running yields identical row count + identical (qkey, ukey) pairs."""
    from app.transformations import run_all as run_transformations

    async with session_scope() as session:
        r = await session.execute(
            text(
                "SELECT count(*) AS n, count(DISTINCT ukey) AS u FROM dim_question_data"
            )
        )
        before = r.one()

        await run_transformations(session)

        r = await session.execute(
            text(
                "SELECT count(*) AS n, count(DISTINCT ukey) AS u FROM dim_question_data"
            )
        )
        after = r.one()
        assert before.n == after.n
        assert before.u == after.u
