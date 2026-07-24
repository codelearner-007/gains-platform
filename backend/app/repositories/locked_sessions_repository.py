"""Repository for the ``locked_sessions`` historic-lock registry.

See migration ``20260723100000_historic_lock.sql`` and MASTER_PLAN §LOCK.

A row in ``locked_sessions`` freezes a ``(school_id, session)`` fact slice: the
DB triggers on ``fact_student_submission`` refuse to DELETE any locked row and
refuse to TRUNCATE the table entirely while any lock exists. This repo is the
app-layer read/write path over that registry (the App guard consults it before
a run writes; lock/unlock are manual, gated operations).

All statements are parameterized and run under the caller's (read-committed)
transaction. ``lock_session`` computes the fact_checksum from the frozen slice
in the same round-trip so the recorded checksum reflects the data at lock time.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repository import row_to_dict

# Columns returned by list/read helpers, kept aligned in one place.
_LOCK_COLUMNS = """
    school_id::text AS school_id,
    session,
    locked_at,
    locked_by,
    fact_checksum,
    reason
"""


class LockedSessionsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def is_locked(self, school_id: str, session: str) -> bool:
        """Whether a specific ``(school_id, session)`` slice is locked."""
        sql = text(
            """
            SELECT EXISTS (
                SELECT 1 FROM public.locked_sessions
                WHERE school_id = CAST(:sid AS UUID) AND session = :sess
            )
            """
        )
        result = await self.session.execute(sql, {"sid": school_id, "sess": session})
        return bool(result.scalar_one())

    async def any_locked(self) -> bool:
        """Whether ANY lock exists (drives the TRUNCATE-refusal / SQL guard)."""
        sql = text("SELECT EXISTS (SELECT 1 FROM public.locked_sessions)")
        result = await self.session.execute(sql)
        return bool(result.scalar_one())

    async def locked_sessions_for(self, school_id: str) -> List[str]:
        """Return the locked session labels for a school (ordered)."""
        sql = text(
            """
            SELECT session
            FROM public.locked_sessions
            WHERE school_id = CAST(:sid AS UUID)
            ORDER BY session
            """
        )
        result = await self.session.execute(sql, {"sid": school_id})
        return [r[0] for r in result.all()]

    async def list_all(self) -> List[Dict[str, Any]]:
        """Return every lock row (admin/audit surface)."""
        sql = text(
            f"""
            SELECT {_LOCK_COLUMNS}
            FROM public.locked_sessions
            ORDER BY locked_at DESC
            """
        )
        result = await self.session.execute(sql)
        return [row_to_dict(r) for r in result.all()]

    async def lock_session(
        self,
        school_id: str,
        session: str,
        locked_by: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Freeze a ``(school_id, session)`` slice, recording its fact_checksum.

        The checksum is an ``md5`` over the ``string_agg`` of the slice's ordered
        synthetic PKs (``user_id_ques_id_stand``). Ordering makes the digest
        deterministic; an operator can later recompute it to prove the frozen
        data is byte-identical. Re-locking the same slice refreshes the checksum
        and metadata (``ON CONFLICT DO UPDATE``).
        """
        sql = text(
            """
            INSERT INTO public.locked_sessions
                (school_id, session, locked_by, reason, fact_checksum)
            SELECT
                CAST(:sid AS UUID),
                :sess,
                :by,
                :reason,
                (
                    SELECT md5(COALESCE(
                        string_agg(f.user_id_ques_id_stand, ',' ORDER BY f.user_id_ques_id_stand),
                        ''
                    ))
                    FROM public.fact_student_submission f
                    WHERE f.school_id = CAST(:sid AS UUID) AND f.session = :sess
                )
            ON CONFLICT (school_id, session) DO UPDATE
                SET locked_by     = EXCLUDED.locked_by,
                    reason        = EXCLUDED.reason,
                    fact_checksum = EXCLUDED.fact_checksum,
                    locked_at     = now()
            RETURNING
                school_id::text AS school_id,
                session, locked_at, locked_by, fact_checksum, reason
            """
        )
        result = await self.session.execute(
            sql,
            {"sid": school_id, "sess": session, "by": locked_by, "reason": reason},
        )
        return row_to_dict(result.first())

    async def unlock_session(self, school_id: str, session: str) -> bool:
        """Remove a lock. Returns True if a row was deleted."""
        sql = text(
            """
            DELETE FROM public.locked_sessions
            WHERE school_id = CAST(:sid AS UUID) AND session = :sess
            RETURNING 1
            """
        )
        result = await self.session.execute(sql, {"sid": school_id, "sess": session})
        return result.first() is not None
