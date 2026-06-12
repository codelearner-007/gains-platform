"""Repository for the ``ingestion_runs`` and ``ingested_files`` admin tables.

These tables are intentionally NOT under RLS (see migration 090 header), so
this repo is used only from admin endpoints that check the ``ingestion:*``
permissions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repository import row_to_dict


class IngestionRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_runs(
        self,
        school_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT
                run_id::text AS run_id,
                school_id::text AS school_id,
                started_at, finished_at, status,
                files_processed, rows_inserted, error_count, error_details
            FROM public.ingestion_runs
            WHERE (CAST(:sid AS TEXT) IS NULL OR school_id::text = CAST(:sid AS TEXT))
            ORDER BY started_at DESC
            LIMIT :lim
            """
        )
        result = await self.session.execute(
            sql, {"sid": school_id, "lim": limit}
        )
        return [dict(r._mapping) for r in result.all()]

    async def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        sql = text(
            """
            SELECT
                run_id::text AS run_id,
                school_id::text AS school_id,
                started_at, finished_at, status,
                files_processed, rows_inserted, error_count, error_details
            FROM public.ingestion_runs
            WHERE run_id = :rid
            LIMIT 1
            """
        )
        result = await self.session.execute(sql, {"rid": run_id})
        row = result.first()
        return row_to_dict(row) if row else None

    async def create_pending(
        self, school_id: Optional[str], note: Optional[str] = None
    ) -> Dict[str, Any]:
        """Insert a row in ``ingestion_runs`` with ``status='pending'``.

        The actual ingestion is scheduled out-of-band (the orchestrator flips
        the row to ``running`` and then ``succeeded`` / ``failed``). We just
        record the request so the admin UI can surface it.
        """
        sql = text(
            """
            INSERT INTO public.ingestion_runs
                (school_id, status, started_at, error_details)
            VALUES
                (:sid, 'pending', :now, :details)
            RETURNING
                run_id::text AS run_id,
                school_id::text AS school_id,
                started_at, finished_at, status,
                files_processed, rows_inserted, error_count, error_details
            """
        )
        details = {"requested_via": "api"}
        if note:
            details["note"] = note
        import json as _json
        result = await self.session.execute(
            sql,
            {
                "sid": school_id,
                "now": datetime.now(timezone.utc),
                "details": _json.dumps(details),
            },
        )
        row = result.first()
        return row_to_dict(row)
