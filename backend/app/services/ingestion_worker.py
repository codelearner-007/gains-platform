"""Durable in-process ingestion worker (HARDENING_PLAN §4/§5/§6).

Replaces the fire-and-forget ``BackgroundTask`` + ``threading.Lock`` dispatch.
``ingestion_runs`` is the queue; this async loop claims one pending run at a
time (``FOR UPDATE SKIP LOCKED``), lands its raw rows, runs the transform gate,
archives its source files, and marks the run terminal — all wrapped so ANY
exception marks the run ``failed`` with error details (fixes F8: no run ever
gets stuck ``running``).

Design (why it looks the way it does):
  * **Own connections, own loop.** The worker uses the jobs engine
    (``app.jobs.db``) on its own ``session_scope`` connections, NEVER the
    request pool — the jobs engine is loop-bound and the request pool must stay
    free for HTTP. The lifespan starts this coroutine on the server loop, which
    is the same loop the jobs engine binds to, so there is no cross-loop reuse.
  * **Lease + heartbeat + reaper.** A crashed / redeployed worker leaves its run
    ``running`` with a stale ``heartbeat_at``; the reaper (startup + every poll)
    requeues it (attempts left) or fails it (cap hit). SIGTERM stops claiming
    and lets the in-flight run finish or lease-expire — crash-equivalent, safe.
  * **Transform gate (§5).** Raw is landed with ``skip_transforms=True`` and the
    run left ``landed``; transforms run ONCE per batch behind the kill-switch,
    the empty-raw floor, a global advisory mutex, and a collapse-guard, and the
    dirty flag is cleared in the SAME txn as the cube rebuild. Prod
    (``INGESTION_TRANSFORMS_ENABLED=False``, raw=0) NEVER rebuilds.

STOP conditions honored: the transform txn only ever runs the real
``transformations.run_all``; nothing here truncates raw. The empty-raw floor is
a total-raw guard (never a per-school comparison), so the mixed-backup routing
cannot false-positive.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.jobs.blob_client import BlobInfo, SupabaseStorageBlobClient
from app.jobs.db import dispose_engine, session_scope
from app.jobs.ingest_schoology import IngestSummary, run_ingestion
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.repositories.locked_sessions_repository import LockedSessionsRepository
from app.transformations import run_all as run_transformations

logger = logging.getLogger("ingestion_worker")

# Constant advisory-lock key for the GLOBAL transform mutex (§5 step 3). A fixed
# int64 unrelated to any per-school key (those are derived from school_id bytes),
# so only one transform pass can run across all workers/processes at a time.
_TRANSFORM_LOCK_KEY = 0x1A9E571A5F0  # fixed advisory-lock key; value arbitrary, must stay constant


def _worker_id() -> str:
    """A stable-ish id for this worker instance (host + pid + random suffix)."""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"


class IngestionWorker:
    """Polls the ``ingestion_runs`` queue and drives each run to completion."""

    def __init__(
        self,
        *,
        worker_id: Optional[str] = None,
        poll_seconds: Optional[int] = None,
        lease_seconds: Optional[int] = None,
        heartbeat_seconds: Optional[int] = None,
        max_attempts: Optional[int] = None,
        blob_client_factory: Any = None,
    ) -> None:
        self.worker_id = worker_id or _worker_id()
        self.poll_seconds = (
            poll_seconds
            if poll_seconds is not None
            else settings.INGESTION_WORKER_POLL_SECONDS
        )
        self.lease_seconds = (
            lease_seconds
            if lease_seconds is not None
            else settings.INGESTION_LEASE_SECONDS
        )
        self.heartbeat_seconds = (
            heartbeat_seconds
            if heartbeat_seconds is not None
            else settings.INGESTION_HEARTBEAT_SECONDS
        )
        self.max_attempts = (
            max_attempts
            if max_attempts is not None
            else settings.INGESTION_MAX_ATTEMPTS
        )
        # Injected in tests (fake blob client); defaults to the real Storage
        # client. A factory (not an instance) so each run gets a fresh client.
        self._blob_client_factory = blob_client_factory or SupabaseStorageBlobClient
        self._stop = asyncio.Event()

    # ------------------------------------------------------------------
    # Loop lifecycle
    # ------------------------------------------------------------------

    async def run_forever(self) -> None:
        """Reaper-on-startup, then poll until stopped.

        Startup reconciliation: run the reaper once so any run left ``running``/
        ``transforming`` by a prior crashed instance is requeued/failed before we
        start claiming. Then loop: reap, drain the pending batch, sleep.
        """
        logger.info("ingestion worker %s starting", self.worker_id)
        try:
            await self._reap()
        except Exception:
            logger.exception("ingestion worker startup reaper failed")

        while not self._stop.is_set():
            try:
                await self._reap()
                await self._drain_batch()
            except Exception:
                logger.exception("ingestion worker poll iteration failed")
            await self._sleep_or_stop(self.poll_seconds)

        logger.info("ingestion worker %s stopped", self.worker_id)

    def stop(self) -> None:
        """Signal the loop to stop claiming and exit after the current run."""
        self._stop.set()

    async def _sleep_or_stop(self, seconds: float) -> None:
        """Sleep up to ``seconds``, waking early if ``stop()`` is called."""
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    # ------------------------------------------------------------------
    # Reaper
    # ------------------------------------------------------------------

    async def _reap(self) -> None:
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            reaped = await repo.requeue_expired(
                lease_seconds=self.lease_seconds, max_attempts=self.max_attempts
            )
        if reaped:
            logger.info(
                "reaper: %d expired run(s) reconciled (%s)",
                len(reaped),
                ", ".join(f"{r['run_id']}→{r['status']}" for r in reaped),
            )

    # ------------------------------------------------------------------
    # Batch drain (§4): land ALL pending first, then ONE transform pass.
    # ------------------------------------------------------------------

    async def _drain_batch(self) -> None:
        """Claim + land every currently-pending run, then run ONE transform pass.

        N schools queued at once become one warehouse rebuild, not N. Each run is
        landed independently (its own terminal ``landed``/``failed`` + archive);
        the single trailing transform pass then flips every clean ``landed`` run
        for this batch to ``succeeded``. If nothing landed cleanly, no transform
        pass runs.
        """
        landed: List[Dict[str, Any]] = []
        while not self._stop.is_set():
            claimed = await self._claim_next()
            if claimed is None:
                break
            result = await self._land_run(claimed)
            if result is not None:
                landed.append(result)

        if not landed:
            return

        # ONE transform pass for the whole batch. It flips every clean landed run
        # to `succeeded` (or fails them all together on a transform error).
        await self._transform_batch(landed)

    async def _claim_next(self) -> Optional[Dict[str, Any]]:
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            return await repo.claim_next(self.worker_id)

    # ------------------------------------------------------------------
    # Per-run landing (§4) — wrapped so ANY exception → failed (F8).
    # ------------------------------------------------------------------

    async def _land_run(self, run: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Land ONE claimed run's raw rows + archive. Returns landing context on
        clean landing (so the batch can transform + finalize it), else ``None``.

        Everything is wrapped: any exception marks the run ``failed`` with error
        details and returns ``None``. The run is left in ``landed`` (not
        ``succeeded``) — the batch transform pass promotes it to ``succeeded``.
        """
        run_id: str = run["run_id"]
        short_name = await self._short_name_for(run)

        # F9: a claimed run whose school does not resolve to an active school has
        # nothing to ingest — fail loudly rather than silently no-op.
        if short_name is None:
            await self._mark(run_id, "failed", {"error": "no matching active school"})
            logger.warning("run %s: no matching active school → failed", run_id)
            return None

        # §LOCK layer 1 (App guard): resolve this run's target session(s) and
        # refuse to land/transform if any is frozen in ``locked_sessions``. This
        # fires BEFORE any staging/land write, so a locked historic year can never
        # be rebuilt from a stray re-ingest. INERT when nothing is locked (the
        # common path): with no matching lock the run proceeds untouched.
        locked = await self._locked_target_session(run)
        if locked is not None:
            msg = f"session {locked} is locked; refusing to rebuild"
            await self._mark(run_id, "failed", {"error": msg})
            logger.warning("run %s (%s): %s", run_id, short_name, msg)
            return None

        heartbeat = asyncio.create_task(self._heartbeat_loop(run_id))
        bc = self._blob_client_factory()
        try:
            # Mark warehouse dirty BEFORE landing (token=run_id): if we crash
            # after committing raw but before transforming, the reaper re-runs and
            # the dirty flag still forces a transform pass (no permanent
            # staleness).
            async with session_scope() as session:
                await IngestionRunRepository(session).set_warehouse_dirty(run_id)

            # Snapshot live keys BEFORE the run so files uploaded mid-run stay
            # live for the next run (§6).
            snapshot = list(bc.list_files(short_name))

            summary: IngestSummary = await run_ingestion(
                school_filter=short_name,
                blob_client=bc,
                skip_transforms=True,
                run_id=UUID(run_id),
                landed_status="landed",
            )

            # Invariant (belt for F4): every seen file must be accounted for.
            accounted = (
                summary.files_processed + summary.files_skipped + summary.error_count
            )
            if summary.files_seen != accounted:
                raise RuntimeError(
                    f"file-count invariant broken: seen={summary.files_seen} "
                    f"!= processed+skipped+errors={accounted}"
                )

            # Archive (§6) — gated on a clean landing (error_count == 0 AND the
            # invariant held). Per-file failures leave source files live.
            if summary.error_count == 0:
                self._archive(bc, short_name, run_id, snapshot)
            else:
                logger.warning(
                    "run %s (%s) had %d error(s); leaving %d source file(s) live",
                    run_id, short_name, summary.error_count, len(snapshot),
                )

            logger.info(
                "run %s (%s) landed: seen=%d processed=%d skipped=%d rows=%d errors=%d",
                run_id, short_name, summary.files_seen, summary.files_processed,
                summary.files_skipped, summary.rows_inserted, summary.error_count,
            )
            return {
                "run_id": run_id,
                "short_name": short_name,
                "rows_inserted": summary.rows_inserted,
                "error_count": summary.error_count,
            }
        except Exception as exc:  # noqa: BLE001 — any failure → run failed (F8)
            logger.exception("run %s (%s) landing failed", run_id, short_name)
            await self._mark(
                run_id, "failed", {"error": f"{type(exc).__name__}: {exc}"}
            )
            return None
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
            # Dispose the jobs engine at the end of the run so the next run (or a
            # later poll on a fresh loop) rebinds cleanly — mirrors the CLI.
            await dispose_engine()

    def _archive(
        self,
        bc: Any,
        short_name: str,
        run_id: str,
        snapshot: List[BlobInfo],
    ) -> None:
        """Move snapshot keys to ``processed/<short_name>/<run_id>/<rel>`` (§6).

        Changed-guard: re-list the live prefix once; skip any key whose live
        ``last_modified`` is newer than the snapshot entry's — a mid-run
        re-upload with newer bytes stays live for the next run (never archive
        un-ingested newer content). Per-key try/except so a partial archive
        self-heals next run.
        """
        try:
            current = {b.path: b.last_modified for b in bc.list_files(short_name)}
        except Exception:
            logger.exception(
                "run %s: archive re-list failed; skipping archive", run_id
            )
            return

        for blob in snapshot:
            live_mtime = current.get(blob.path)
            if live_mtime is not None and live_mtime > blob.last_modified:
                logger.info(
                    "run %s: %s re-uploaded mid-run (newer bytes) → left live",
                    run_id, blob.path,
                )
                continue
            from_key = f"{short_name}/{blob.path}"
            to_key = f"processed/{short_name}/{run_id}/{blob.path}"
            try:
                bc.move(from_key, to_key)
            except Exception:
                logger.exception(
                    "run %s: failed to archive %s → %s", run_id, from_key, to_key
                )

    async def _heartbeat_loop(self, run_id: str) -> None:
        """Refresh ``heartbeat_at`` every ``heartbeat_seconds`` while landing."""
        try:
            while True:
                await asyncio.sleep(self.heartbeat_seconds)
                async with session_scope() as session:
                    await IngestionRunRepository(session).heartbeat(
                        run_id, self.worker_id
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("heartbeat loop for run %s errored", run_id)

    # ------------------------------------------------------------------
    # Transform gate (§5) — ONE pass for the batch.
    # ------------------------------------------------------------------

    async def _transform_batch(self, landed: List[Dict[str, Any]]) -> None:
        """Apply the transform gate once, then finalize each landed run.

        On success every clean landed run (error_count == 0) is marked
        ``succeeded``; runs that landed with errors stay ``landed`` (their source
        files were left live). On a transform failure every clean landed run is
        marked ``failed`` and the dirty flag is left set for the reaper/next run.
        """
        # A stable run_id to own the transform (the newest landed run's id — it
        # is the token the dirty flag will be cleared against).
        driver_run_id = landed[-1]["run_id"]
        rows_this_batch = sum(r["rows_inserted"] for r in landed)

        try:
            outcome = await self._run_transform_gate(driver_run_id, rows_this_batch)
        except Exception as exc:  # noqa: BLE001
            logger.exception("transform gate failed for batch (driver %s)", driver_run_id)
            # Every clean landed run in this batch is not durable until transforms
            # apply → fail them all; the dirty flag stays set (self-heals).
            for r in landed:
                if r["error_count"] == 0:
                    await self._mark(
                        r["run_id"],
                        "failed",
                        {"error": f"transform gate: {type(exc).__name__}: {exc}"},
                    )
            return

        # Kill-switch case: transforms are OFF (prod), so a clean landing is NOT
        # yet a `succeeded` run — leave it `landed` (raw is safe; the dirty flag
        # stays set for a later env where transforms are enabled).
        if outcome == "disabled":
            for r in landed:
                logger.info(
                    "run %s left 'landed' (transforms disabled)", r["run_id"]
                )
            return

        # Transforms applied (or skip-clean cleared): promote every clean landing
        # to `succeeded`. Runs that landed WITH errors stay `landed` (their source
        # files were left live for a retry).
        for r in landed:
            if r["error_count"] == 0:
                await self._mark(
                    r["run_id"],
                    "succeeded",
                    {"transforms_applied": outcome == "applied"},
                )
            else:
                logger.info(
                    "run %s left 'landed' (had %d error(s))",
                    r["run_id"], r["error_count"],
                )

    async def _run_transform_gate(self, run_id: str, rows_this_batch: int) -> str:
        """The §5 gate. Returns the outcome:

            * ``"applied"``   — transforms ran and the dirty flag was cleared.
            * ``"skip_clean"``— 0 rows + own token → cleared WITHOUT transforming.
            * ``"disabled"``  — kill-switch OFF; nothing ran, dirty flag left set.

        Raises on the empty-raw floor, a collapse-guard trip, or the §HISTORIC
        invariant inside ``run_all`` refusing to alter a year the raw layer cannot
        regenerate — the caller fails the batch's clean runs and leaves the flag
        dirty.
        """
        # 1. Kill-switch (PRIMARY). Prod stays False → never rebuilds. Leave the
        #    dirty flag set (raw is safe; cubes refresh where enabled).
        if not settings.INGESTION_TRANSFORMS_ENABLED:
            logger.info(
                "transforms DISABLED (kill-switch); leaving warehouse dirty, "
                "runs stay landed"
            )
            return "disabled"

        # NOTE: there is deliberately no environment check here any more. Historic
        # years are protected by the §HISTORIC invariant inside run_all (see
        # app/transformations/runner.py), which fingerprints every (school, session)
        # slice before and after the build and rolls back if one that raw cannot
        # regenerate was touched. That is a property of the DATA, so it holds on
        # this path and on every CLI path identically, with nothing to configure.

        # 5. Skip-clean economics (F27): a batch that landed 0 rows AND owns the
        #    current dirty token clears its own pre-mark WITHOUT transforming. But
        #    0 rows with a PRE-EXISTING dirty flag (from a prior crash) DOES
        #    transform — closing the permanent-staleness hole.
        if rows_this_batch == 0:
            async with session_scope() as session:
                own_token = await self._owns_dirty_token(session, run_id)
                pre_dirty = not own_token  # dirty from something other than us
            if not pre_dirty:
                async with session_scope() as session:
                    await IngestionRunRepository(session).clear_warehouse_dirty(run_id)
                logger.info(
                    "batch landed 0 rows and owns dirty token → skip-clean "
                    "(no transform)"
                )
                return "skip_clean"
            logger.info(
                "batch landed 0 rows but warehouse pre-dirty → running transforms"
            )

        # 2. Empty-raw floor preflight (total-raw guard; catches prod raw=0).
        #    Bounded probe: we only need "≥ floor", so stop counting at the floor
        #    instead of a full count(*) over ~2.6M rows.
        async with session_scope() as session:
            raw_total = await IngestionRunRepository(session).raw_total_count(
                cap=settings.INGESTION_RAW_FLOOR
            )
        if raw_total < settings.INGESTION_RAW_FLOOR:
            raise RuntimeError(
                f"transforms refused: raw layer empty/below floor "
                f"(raw_total={raw_total} < {settings.INGESTION_RAW_FLOOR})"
            )

        # 3 + 4. Global mutex + rebuild + atomic clear, all in ONE txn. A crash
        # mid-transform rolls back the cubes AND the clear together, so the old
        # cubes survive and the dirty flag stays set for the reaper.
        async with self._transform_session() as session:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:k)"), {"k": _TRANSFORM_LOCK_KEY}
            )
            # Long rebuild: uncap statement_timeout on this session (F26). The
            # jobs engine already uses the direct (non-pooler) DATABASE_URL.
            await session.execute(text("SET statement_timeout = 0"))

            fact_pre = await self._fact_count(session)
            await run_transformations(session)
            fact_post = await self._fact_count(session)

            # Collapse-guard: transforms that wipe a previously-populated fact to
            # 0 rows are a bug (e.g. a bad staging join) — RAISE so the txn rolls
            # back and the old cubes survive.
            if fact_pre > 0 and fact_post == 0:
                raise RuntimeError(
                    f"transform collapse-guard: fact_student_submission went "
                    f"{fact_pre} → 0; rolling back to preserve old cubes"
                )

            # Clear the dirty flag in the SAME txn as the rebuild → new cubes AND
            # a clean flag commit atomically.
            await IngestionRunRepository(session).clear_warehouse_dirty(run_id)

        logger.info(
            "transforms applied (driver run %s): fact %d rows", run_id, fact_post
        )
        return "applied"

    @staticmethod
    async def _owns_dirty_token(session: AsyncSession, run_id: str) -> bool:
        row = (
            await session.execute(
                text("SELECT dirty_token::text FROM warehouse_state WHERE id = 1")
            )
        ).first()
        return bool(row) and row[0] == run_id

    @staticmethod
    async def _fact_count(session: AsyncSession) -> int:
        return int(
            (
                await session.execute(text("SELECT count(*) FROM fact_student_submission"))
            ).scalar_one()
        )

    def _transform_session(self):
        """Session context for the transform txn. Overridable in tests. Uses the
        jobs engine's ``session_scope`` (its own connection, direct URL)."""
        return session_scope()

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    async def _short_name_for(self, run: Dict[str, Any]) -> Optional[str]:
        """Resolve the run's target school ``short_name`` from its ``school_id``.

        The worker lands one school per run (the endpoints enqueue per-school),
        so a run must carry a ``school_id`` that maps to an active school.
        Returns ``None`` when it does not (→ F9 fail).
        """
        school_id = run.get("school_id")
        if not school_id:
            return None
        async with session_scope() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT short_name FROM schools "
                        "WHERE school_id = CAST(:sid AS UUID) AND is_active = TRUE "
                        "LIMIT 1"
                    ),
                    {"sid": school_id},
                )
            ).first()
        return row[0] if row else None

    async def _locked_target_session(self, run: Dict[str, Any]) -> Optional[str]:
        """Return the run's target session IF it is locked, else ``None``.

        The target session is the year this run is about to (re)build. There is
        no explicit per-run session column today, so we resolve it from the
        school's ``current_session`` (the year the scraper files into and the
        parser stamps onto raw.session — see §ROUTING). An explicit ``session``
        on the run dict is honored first if a future caller supplies one.

        Returns the session label when ``(school_id, session)`` is locked, so
        the caller can name it in the failure. Returns ``None`` when nothing is
        locked (the inert common path) or when no target session can be
        resolved (nothing to guard — landing proceeds and F9-style checks
        elsewhere handle empties).
        """
        school_id = run.get("school_id")
        if not school_id:
            return None
        target = run.get("session") or run.get("target_session")
        async with session_scope() as session:
            if not target:
                row = (
                    await session.execute(
                        text(
                            "SELECT current_session FROM schools "
                            "WHERE school_id = CAST(:sid AS UUID) LIMIT 1"
                        ),
                        {"sid": school_id},
                    )
                ).first()
                target = row[0] if row else None
            if not target:
                return None
            is_locked = await LockedSessionsRepository(session).is_locked(
                str(school_id), str(target)
            )
        return str(target) if is_locked else None

    async def _mark(
        self, run_id: str, status: str, details: Optional[Dict[str, Any]] = None
    ) -> None:
        async with session_scope() as session:
            await IngestionRunRepository(session).mark(run_id, status, details)
