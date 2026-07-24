"""Repository for the ``ingestion_runs`` and ``ingested_files`` admin tables.

These tables are intentionally NOT under RLS (see migration 090 header), so
this repo is used only from admin endpoints that check the ``ingestion:*``
permissions.
"""

from __future__ import annotations

import json as _json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repository import row_to_dict

# Columns the durable queue reads back on claim/mark so the worker has the full
# run context in one round-trip. Kept in one place so every SELECT stays aligned.
_RUN_COLUMNS = """
    run_id::text AS run_id,
    school_id::text AS school_id,
    started_at, finished_at, status,
    files_processed, rows_inserted, error_count, error_details,
    claimed_at, heartbeat_at, worker_id, attempt_count, transforms_applied
"""


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

    # ------------------------------------------------------------------
    # Durable queue (HARDENING_PLAN §4) — claim / heartbeat / reaper / mark.
    # ------------------------------------------------------------------

    async def pending_for_school(
        self, school_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Return the oldest ``pending`` run for a school (coalescing check).

        Endpoints call this before enqueueing so a second request for a school
        that already has a queued run returns the existing run instead of
        creating a duplicate. ``NULL`` school_id (all-schools run) matches only
        other all-schools pending runs.
        """
        sql = text(
            f"""
            SELECT {_RUN_COLUMNS}
            FROM public.ingestion_runs
            WHERE status = 'pending'
              AND school_id IS NOT DISTINCT FROM CAST(:sid AS UUID)
            ORDER BY started_at
            LIMIT 1
            """
        )
        result = await self.session.execute(sql, {"sid": school_id})
        row = result.first()
        return row_to_dict(row) if row else None

    async def claim_next(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Atomically claim the oldest ``pending`` run for this worker.

        ``FOR UPDATE SKIP LOCKED`` on the inner select means two workers racing
        on the same pending row can never both win it: the loser skips the
        locked row and either grabs a different pending run or gets ``None``.
        Flips the row to ``running`` and bumps ``attempt_count`` in one UPDATE.
        """
        sql = text(
            f"""
            UPDATE public.ingestion_runs
            SET status = 'running',
                claimed_at = now(),
                heartbeat_at = now(),
                worker_id = :w,
                attempt_count = attempt_count + 1
            WHERE run_id = (
                SELECT run_id
                FROM public.ingestion_runs
                WHERE status = 'pending'
                ORDER BY started_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING {_RUN_COLUMNS}
            """
        )
        result = await self.session.execute(sql, {"w": worker_id})
        row = result.first()
        return row_to_dict(row) if row else None

    async def heartbeat(self, run_id: str, worker_id: str) -> None:
        """Refresh ``heartbeat_at`` for a run this worker still owns.

        Scoped to ``worker_id`` so a worker whose lease was already reaped and
        reassigned cannot keep a stale claim alive.
        """
        sql = text(
            """
            UPDATE public.ingestion_runs
            SET heartbeat_at = now()
            WHERE run_id = :rid AND worker_id = :w
              AND status IN ('running', 'transforming')
            """
        )
        await self.session.execute(sql, {"rid": run_id, "w": worker_id})

    async def requeue_expired(
        self, lease_seconds: int, max_attempts: int
    ) -> List[Dict[str, Any]]:
        """Reap runs whose lease expired (crashed / redeployed worker).

        A row in ``running``/``transforming`` whose ``heartbeat_at`` is older
        than ``lease_seconds`` (or NULL) is stale. If it still has attempts left
        it goes back to ``pending`` (idempotent: hash-skip + TRUNCATE-idempotent
        transforms make a retry safe); otherwise it is marked ``failed``.
        Returns the affected rows (post-update) for logging/assertions.
        """
        sql = text(
            f"""
            UPDATE public.ingestion_runs
            SET status = CASE
                    WHEN attempt_count < :max THEN 'pending'
                    ELSE 'failed'
                END,
                finished_at = CASE
                    WHEN attempt_count < :max THEN NULL
                    ELSE now()
                END,
                claimed_at = NULL,
                heartbeat_at = NULL,
                worker_id = NULL,
                error_details = CASE
                    WHEN attempt_count < :max THEN error_details
                    ELSE COALESCE(error_details, '{{}}'::jsonb)
                         || jsonb_build_object(
                                'reaper',
                                'lease expired after ' || attempt_count || ' attempts'
                            )
                END
            WHERE status IN ('running', 'transforming')
              AND (
                    heartbeat_at IS NULL
                    OR heartbeat_at < now() - make_interval(secs => :lease)
                  )
            RETURNING {_RUN_COLUMNS}
            """
        )
        result = await self.session.execute(
            sql, {"lease": lease_seconds, "max": max_attempts}
        )
        return [row_to_dict(r) for r in result.all()]

    async def mark(
        self,
        run_id: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Set a run's terminal/intermediate status (+ optional error details).

        Terminal statuses (``succeeded``/``failed``) also stamp ``finished_at``.
        ``details`` is merged into ``error_details`` (never clobbered) so earlier
        context survives.
        """
        terminal = status in ("succeeded", "failed")
        sql = text(
            """
            UPDATE public.ingestion_runs
            SET status = :status,
                finished_at = CASE WHEN :terminal THEN now() ELSE finished_at END,
                error_details = CASE
                    WHEN CAST(:details AS jsonb) IS NULL THEN error_details
                    ELSE COALESCE(error_details, '{}'::jsonb) || CAST(:details AS jsonb)
                END
            WHERE run_id = :rid
            """
        )
        await self.session.execute(
            sql,
            {
                "rid": run_id,
                "status": status,
                "terminal": terminal,
                "details": _json.dumps(details) if details is not None else None,
            },
        )

    # ------------------------------------------------------------------
    # warehouse_state (HARDENING_PLAN §5) — transform dirty flag.
    # ------------------------------------------------------------------

    async def set_warehouse_dirty(self, token: str) -> None:
        """Mark the warehouse dirty with ``token`` (the run_id doing the landing).

        Idempotent single-row update; if already dirty from an earlier crash the
        ``dirty_since`` is preserved so staleness age is not reset.
        """
        sql = text(
            """
            UPDATE public.warehouse_state
            SET transforms_dirty = true,
                dirty_token = CAST(:token AS UUID),
                dirty_since = COALESCE(dirty_since, now())
            WHERE id = 1
            """
        )
        await self.session.execute(sql, {"token": token})

    async def clear_warehouse_dirty(self, run_id: str) -> None:
        """Clear the dirty flag and record which run applied the transforms.

        Callers run this in the SAME txn as the cube rebuild so new cubes and a
        clean flag commit atomically.
        """
        sql = text(
            """
            UPDATE public.warehouse_state
            SET transforms_dirty = false,
                dirty_since = NULL,
                dirty_token = NULL,
                last_transform_run_id = CAST(:rid AS UUID),
                last_transform_at = now()
            WHERE id = 1
            """
        )
        await self.session.execute(sql, {"rid": run_id})

    async def warehouse_dirty(self) -> bool:
        """Return whether the warehouse currently has pending transforms."""
        sql = text(
            "SELECT transforms_dirty FROM public.warehouse_state WHERE id = 1"
        )
        result = await self.session.execute(sql)
        row = result.first()
        return bool(row[0]) if row is not None else False

    async def raw_total_count(self, *, cap: Optional[int] = None) -> int:
        """Rows in ``raw_student_submission`` (empty-raw floor preflight).

        A total-raw guard: ~2.6M on the local full-raw env, 0 on prod. It never
        inspects per-school counts, so the mixed-backup routing cannot make it
        false-positive. Pass ``cap`` to stop counting once that many rows are
        seen — the floor check only needs "at least N", so a bounded probe
        avoids a full-table ``count(*)`` over millions of rows (the result is
        exact whenever it is below ``cap``, which is the only case the caller
        acts on).
        """
        if cap is None:
            sql = text("SELECT count(*) FROM raw_student_submission")
        else:
            sql = text(
                "SELECT count(*) FROM "
                "(SELECT 1 FROM raw_student_submission LIMIT :cap) t"
            )
        result = await self.session.execute(sql, {"cap": cap} if cap is not None else {})
        return int(result.scalar_one())
