"""F — RLS tenant scoping (DB fixtures) — the payoff.

Locks the NO-CROSS-SCHOOL-READ invariant that the whole LTI per-school gate
exists to protect. A session scoped (via the same SET LOCAL ROLE authenticated +
app.current_school_id GUC that set_school_id_for_session uses) to school A must
NOT read school B's tenant rows, and a session with the GUC UNSET must read ZERO
rows (fail-closed) — never every tenant's data.

We assert at the policy level with synthetic rows we insert into an RLS-protected
tenant table (cube_school_summary) and delete by exact key. Two REAL schools (A,
B) satisfy the school_id FK; only our sentinel-id rows are ever touched.
"""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager

from sqlalchemy import text

from ..services._lti_fixtures import fresh_session

# Sentinel PKs so cleanup only ever removes our two synthetic cube rows.
TAG = f"WAVE4-RLS-{secrets.token_hex(4)}"
ID_A = f"{TAG}-A"
ID_B = f"{TAG}-B"


async def _two_real_schools(session):
    rows = (
        await session.execute(text("SELECT school_id::text FROM schools ORDER BY school_id LIMIT 2"))
    ).all()
    assert len(rows) >= 2, "need >=2 schools in local DB for cross-tenant proof"
    return rows[0][0], rows[1][0]


@asynccontextmanager
async def _seeded_rls_rows():
    """Insert one synthetic cube row per school (A, B); delete both in teardown."""
    async with fresh_session() as session:
        school_a = school_b = None
        try:
            school_a, school_b = await _two_real_schools(session)
            for row_id, sid in ((ID_A, school_a), (ID_B, school_b)):
                await session.execute(
                    text(
                        "INSERT INTO cube_school_summary (id, school_id, total_students) "
                        "VALUES (:id, CAST(:sid AS UUID), 999)"
                    ),
                    {"id": row_id, "sid": sid},
                )
            await session.commit()
            yield session, school_a, school_b
        finally:
            await session.execute(
                text("DELETE FROM cube_school_summary WHERE id IN (:a, :b)"),
                {"a": ID_A, "b": ID_B},
            )
            await session.commit()


async def _count_visible(session, ids) -> int:
    """Rows among our sentinel ids visible to the CURRENT role/GUC."""
    r = await session.execute(
        text("SELECT count(*) FROM cube_school_summary WHERE id = ANY(:ids)"),
        {"ids": list(ids)},
    )
    return r.scalar_one()


async def test_scoped_to_school_a_cannot_read_school_b():
    async with _seeded_rls_rows() as (session, school_a, school_b):
        # Enter the SAME enforcement context the RLS middleware uses.
        await session.execute(text("SET LOCAL ROLE authenticated"))
        await session.execute(text(f"SET LOCAL app.current_school_id = '{school_a}'"))

        # School A's own row is visible…
        assert await _count_visible(session, [ID_A]) == 1
        # …but school B's row is NOT (no cross-tenant read).
        assert await _count_visible(session, [ID_B]) == 0
        # And querying both together still only yields A's single row.
        assert await _count_visible(session, [ID_A, ID_B]) == 1

        await session.rollback()  # release SET LOCAL ROLE / GUC


async def test_unset_guc_reads_zero_rows_failclosed():
    async with _seeded_rls_rows() as (session, school_a, school_b):
        # Role switched (drops superuser bypass) but GUC intentionally UNSET —
        # the fail-closed no-membership path. NULLIF(...,'')::uuid is NULL, so the
        # policy matches ZERO rows rather than leaking every tenant.
        await session.execute(text("SET LOCAL ROLE authenticated"))

        assert await _count_visible(session, [ID_A, ID_B]) == 0

        await session.rollback()


async def test_superuser_bypass_would_see_both_control():
    # Control/sanity: as the connecting superuser (no role switch) BOTH rows are
    # visible — proving the zero-row results above are RLS enforcement, not a
    # missing-data artifact. Guards against a false-green "no rows because nothing
    # was inserted" failure mode.
    async with _seeded_rls_rows() as (session, school_a, school_b):
        assert await _count_visible(session, [ID_A, ID_B]) == 2
