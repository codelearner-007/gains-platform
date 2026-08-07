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
    dirty flag is cleared in the SAME txn as the cube rebuild. Turning
    ``INGESTION_TRANSFORMS_ENABLED`` ON is the sanctioned way to run the SCOPED
    incremental transform (+ the ``INGESTION_PURGE_TRANSFORMED_RAW`` raw purge)
    on a serving box: the scoped path writes only the batch's subjects behind
    the §HISTORIC guard, so a lean prod box (raw≈20) rebuilds just those slices
    rather than the whole warehouse. With the flag OFF (the default) nothing
    rebuilds.

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
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.jobs.blob_client import BlobInfo, SupabaseStorageBlobClient
from app.jobs.db import dispose_engine, get_engine, session_scope
from app.jobs.ingest_schoology import IngestSummary, run_ingestion
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.repositories.locked_sessions_repository import LockedSessionsRepository
from app.transformations import run_all as run_transformations
from app.transformations.runner import _TRANSFORM_LOCK_KEY

logger = logging.getLogger("ingestion_worker")

# GLOBAL transform mutex key (§5 step 3): imported from the runner as the single
# source of truth so the worker's transform session and run_all agree on it. The
# worker acquires it BEFORE calling run_all, so run_all's re-acquire on the same
# session is a re-entrant no-op. A fixed int64 unrelated to any per-school key.

# Scoped-touched tables VACUUM(ANALYZE)ed post-commit after an applied transform:
# the subject-scoped DELETE+INSERT leaves dead tuples that are not auto-reclaimed
# (and TRUNCATE/COPY-loaded tables have zeroed stats). VACUUM(ANALYZE) takes only
# SHARE UPDATE EXCLUSIVE — it never blocks serving. A table absent on a given box
# (prod drops the twin cube) is skipped and logged, not fatal.
_SCOPED_TOUCHED_TABLES: tuple[str, ...] = (
    "fact_student_submission",
    "dim_subject",
    "dim_question_data",
    "dim_item",
    "dim_unit_lesson",
    "dim_section",
    # Upserted / TRUNCATE+INSERT dims the scoped pass also writes (ON CONFLICT DO
    # UPDATE leaves dead tuples; hash/strand rebuilds zero reltuples → the
    # immediately-following in-txn cube joins want fresh stats). #19.
    "dim_student",
    "dim_teacher",
    "dim_parent",
    "dim_course",
    "dim_school",
    "dim_session",
    "dim_grade",
    "dim_assessment_type",
    "dim_strand",
    # Pseudonymization hash tables (rebuilt TRUNCATE+INSERT). Prod dropped these
    # in cleanup — the absent-table skip in the VACUUM loop handles that. #19.
    "dim_student_hash",
    "dim_section_hash",
    "fact_student_submissions_hash",
    "cube_question_summary",
    "cube_question_summary_overall",
    "cube_question_summary_overall_by_item",
    "cube_user_summary",
    "cube_school_summary",
    "cube_grade_summary",
    "cube_standard_summary",
    "cube_questionincorrectchoice_summary",
)
# Raw tables the self-healing purge sweeps (and then VACUUMs) when
# INGESTION_PURGE_TRANSFORMED_RAW is enabled. All carry ingestion_run_id.
_RAW_TABLES: tuple[str, ...] = (
    "raw_student_submission",
    "raw_question_data",
    "raw_submission_summary",
)
# Chunk size for the purge DELETE so each statement stays well under any timeout.
_PURGE_CHUNK = 50_000

# Persisted error strings for the two non-success terminal outcomes of an applied
# scoped transform. Kept as module constants so the worker and its tests agree.
_PARTIAL_PRUNE_ERROR = (
    "≥1 contributed subject pruned (partial batch; surviving subjects applied); "
    "raw retained — re-scrape the full assessment to correct the pruned subject"
)
_QD_ONLY_ERROR = (
    "QD-only batch: no student submissions — scoped path cannot apply "
    "question-data alone; raw retained. Re-scrape with submissions or run a "
    "full rebuild."
)


@dataclass(frozen=True)
class _GateOutcome:
    """Result of ``_run_transform_gate`` — the marking plan for the batch.

    ``outcome`` is one of ``"applied"`` / ``"skip_clean"`` / ``"disabled"``.
    The remaining fields are only meaningful on ``"applied"``:

      * ``failed_run_ids`` — runs the roster gate pruned (≥1 subject dropped);
        the caller marks them ``failed`` and retains their raw.
      * ``qd_only_noop`` — the batch carried question-data raw and ZERO student
        submissions, so the scoped path built nothing (``run_all`` returned the
        QD-only sentinel). Every folded run is failed + raw retained.
      * ``pruned_subjects`` — run_id → the subject_ids of that run that were
        pruned, surfaced in ``error_details`` so the operator knows which
        assessment to re-scrape.
    """

    outcome: str
    failed_run_ids: tuple[str, ...] = ()
    qd_only_noop: bool = False
    pruned_subjects: Dict[str, List[str]] = field(default_factory=dict)


def _extract_failed_run_ids(xform_result: object) -> list[str]:
    """Pull the roster-gate failed-run set out of ``run_all``'s return value.

    CONTRACT with the runner (R1 owns runner.py): in SCOPED mode ``run_all``
    returns a ``TransformResult`` (a ``model→rowcount`` dict subclass) whose
    ``.scope`` attribute is a ``ScopeReport`` carrying ``run_subjects``
    (run_id → the subject_ids that run produced), ``survivors`` and
    ``failed_subjects``. A run FAILED iff any subject it produced was pruned by
    the roster gate — i.e. ``run_subjects[run]`` is not a subset of
    ``survivors``. In full/empty-scope mode ``.scope`` is ``None``, so this
    returns ``[]`` and every clean run is promoted (byte-identical to today).
    Defensive: any unrecognized/absent shape also yields ``[]`` (no run wrongly
    failed).

    A run is failed iff it has ≥1 pruned subject, so this delegates to
    ``_extract_pruned_subjects`` and returns its keys (insertion-stable dict
    order == the previous list order).
    """
    return list(_extract_pruned_subjects(xform_result))


def _extract_pruned_subjects(xform_result: object) -> Dict[str, List[str]]:
    """Map each pruned run_id → the subject_ids it produced that did NOT survive.

    Surfaced into the failed run's ``error_details`` so an operator knows which
    assessment(s) to re-scrape (#11/#20). Same defensive contract as
    ``_extract_failed_run_ids``: no scope / unrecognized shape → ``{}``.
    """
    scope = getattr(xform_result, "scope", None)
    run_subjects = getattr(scope, "run_subjects", None)
    survivors = getattr(scope, "survivors", None)
    if not isinstance(run_subjects, dict) or survivors is None:
        return {}
    survivor_set = frozenset(survivors)
    out: Dict[str, List[str]] = {}
    for run, subs in run_subjects.items():
        pruned = sorted(str(s) for s in subs if s not in survivor_set)
        if pruned:
            out[str(run)] = pruned
    return out


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
        for this batch to ``succeeded``.

        If NOTHING landed this poll we still re-drive a transform when the
        warehouse is dirty AND prior ``landed`` runs remain in scope — a crash
        between landing and the transform-mark leaves those runs orphaned (the
        reaper only touches ``running``/``transforming``, ``claim_next`` only
        ``pending``), so without this they would never be built or made terminal.
        The re-drive runs the SAME transform pass with an empty ``landed`` list
        and the swept scope, on the existing poll (no cron).
        """
        landed: List[Dict[str, Any]] = []
        while not self._stop.is_set():
            claimed = await self._claim_next()
            if claimed is None:
                break
            result = await self._land_run(claimed)
            if result is not None:
                landed.append(result)

        if landed:
            # ONE transform pass for the whole batch. It flips every clean landed
            # run to `succeeded` (or fails them all together on a transform error)
            # AND marks any swept prior-'landed' runs folded into the same scope.
            await self._transform_batch(landed)
            return

        # No new landings. Re-drive only when transforms are enabled (a disabled
        # box stays inert — no per-poll churn), the warehouse is dirty, and the
        # landed sweep is non-empty.
        if not settings.INGESTION_TRANSFORMS_ENABLED:
            return
        async with session_scope() as session:
            dirty = await IngestionRunRepository(session).warehouse_dirty()
        if not dirty:
            return
        swept = await self._scope_run_ids([])
        if not swept:
            return
        logger.info(
            "no new landings, warehouse dirty + %d orphaned 'landed' run(s) → "
            "re-driving transform",
            len(swept),
        )
        await self._transform_batch([], force_transform=True)

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

    async def _transform_batch(
        self, landed: List[Dict[str, Any]], *, force_transform: bool = False
    ) -> None:
        """Apply the transform gate once, then mark the FULL folded run set.

        The transform pass folds this batch's runs ∪ every run still ``landed``
        from a prior crash (``_scope_run_ids``), rebuilding ALL their subjects in
        one scoped pass. So marking must cover that whole folded set, not just the
        current ``landed`` list (#4/#8): each folded run whose subjects survived
        is promoted to ``succeeded`` + ``transforms_applied`` (else it stays
        ``landed`` forever and is re-folded on every future drain), each run with
        ≥1 pruned subject is marked ``failed`` (raw retained for a full
        re-scrape), and a QD-only no-op fails every folded run (raw retained).

        ``force_transform`` (re-drive path, ``landed`` empty) bypasses the 0-row
        skip-clean economics so an orphaned-``landed`` backlog is always built.
        """
        scope_run_ids = await self._scope_run_ids(landed)
        if landed:
            # A stable run_id to own the transform (the newest landed run's id —
            # the token the dirty flag will be cleared against).
            driver_run_id = landed[-1]["run_id"]
        elif scope_run_ids:
            # Re-drive: no new landings, but prior 'landed' runs remain in scope.
            # Drive the pass off a swept run id so they are built + made terminal.
            driver_run_id = scope_run_ids[-1]
        else:
            return  # nothing landed and nothing swept → nothing to transform
        rows_this_batch = sum(r["rows_inserted"] for r in landed)

        try:
            gate = await self._run_transform_gate(
                driver_run_id,
                rows_this_batch,
                scope_run_ids,
                force_transform=force_transform,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("transform gate failed for batch (driver %s)", driver_run_id)
            # Every clean landed run in this batch is not durable until transforms
            # apply → fail them all; the dirty flag stays set (self-heals). Swept
            # prior-'landed' runs stay 'landed' and are retried next drive.
            for r in landed:
                if r["error_count"] == 0:
                    await self._mark(
                        r["run_id"],
                        "failed",
                        {"error": f"transform gate: {type(exc).__name__}: {exc}"},
                    )
            return

        # Kill-switch case: transforms are OFF (prod default), so a clean landing
        # is NOT yet a `succeeded` run — leave it `landed` (raw is safe; the dirty
        # flag stays set for a later env where transforms are enabled).
        if gate.outcome == "disabled":
            for r in landed:
                logger.info("run %s left 'landed' (transforms disabled)", r["run_id"])
            return

        # Skip-clean: a 0-row batch that owned the dirty token cleared it WITHOUT
        # transforming — nothing was built. Mark only THIS batch's clean runs
        # `succeeded` (transforms_applied stays false; a 0-row run has ~no raw).
        # A pre-existing dirty flag routes to a real transform instead, so no
        # prior-'landed' run is silently skipped here.
        if gate.outcome == "skip_clean":
            for r in landed:
                if r["error_count"] == 0:
                    await self._finalize_succeeded(
                        r["run_id"], transforms_applied=False
                    )
                else:
                    logger.info(
                        "run %s left 'landed' (had %d error(s))",
                        r["run_id"], r["error_count"],
                    )
            return

        # outcome == "applied" from here.

        # QD-only no-op: the transform committed (dirty cleared) but nothing was
        # built — the batch carried question-data raw and zero student
        # submissions, so the scoped path had no subjects to apply. Fail every
        # folded run so ``transforms_applied`` stays false and the purge retains
        # their raw for a re-scrape with submissions / full rebuild (#5/#9/#12).
        # No cube/dim was touched → no purge, no VACUUM.
        if gate.qd_only_noop:
            for run_id in scope_run_ids:
                await self._mark(run_id, "failed", {"error": _QD_ONLY_ERROR})
            logger.warning(
                "QD-only batch (%d folded run(s)): no student submissions; "
                "nothing built, raw retained for re-scrape / full rebuild",
                len(scope_run_ids),
            )
            return

        # Real applied transform. Mark the FULL folded set (#4/#8). ``landed``
        # supplies error_count for this batch's runs; swept prior-'landed' runs
        # are outside it and default to a clean success (their subjects were
        # rebuilt in this pass).
        landed_errors = {r["run_id"]: r["error_count"] for r in landed}
        failed = frozenset(gate.failed_run_ids)
        for run_id in scope_run_ids:
            if run_id in failed:
                # ≥1 contributed subject pruned (any-pruned semantics). Surviving
                # subjects of this run were still applied; its raw is retained so
                # the pruned assessment can be re-scraped in full (#11/#20).
                details: Dict[str, Any] = {"error": _PARTIAL_PRUNE_ERROR}
                pruned = gate.pruned_subjects.get(run_id)
                if pruned:
                    details["pruned_subject_ids"] = list(pruned)
                await self._mark(run_id, "failed", details)
                logger.warning(
                    "run %s marked 'failed' (roster-gate pruned %s); surviving "
                    "subjects applied, raw retained for retry",
                    run_id,
                    f"{len(pruned)} subject(s)" if pruned else "a contributed subject",
                )
            else:
                # Subjects survived → durable. Promote to `succeeded`. A run that
                # landed WITH file errors but whose subjects applied is still
                # promoted (else it is re-folded forever), carrying a note.
                err = landed_errors.get(run_id, 0)
                note = (
                    {"landing_note": f"landed with {err} error(s); surviving "
                     "subjects applied"}
                    if err
                    else None
                )
                await self._finalize_succeeded(
                    run_id, transforms_applied=True, details=note
                )

        # POST-COMMIT: on a real transform, run the separate-connection
        # (autocommit) self-healing raw purge + VACUUM. After marking, so the
        # purge sees the freshly-succeeded runs. Fail-open-loud inside the helper.
        await self._post_commit_maintenance(
            purge=settings.INGESTION_PURGE_TRANSFORMED_RAW
        )

    async def _run_transform_gate(
        self,
        run_id: str,
        rows_this_batch: int,
        scope_run_ids: List[str],
        *,
        force_transform: bool = False,
    ) -> "_GateOutcome":
        """The §5 gate. Returns a ``_GateOutcome`` whose ``outcome`` is:

            * ``"applied"``   — transforms ran and the dirty flag was cleared.
            * ``"skip_clean"``— 0 rows + own token → cleared WITHOUT transforming.
            * ``"disabled"``  — kill-switch OFF; nothing ran, dirty flag left set.

        On ``"applied"`` the outcome also carries ``failed_run_ids`` (roster-gate
        pruned runs), ``qd_only_noop`` (batch had QD raw but no submissions →
        nothing built), and ``pruned_subjects`` (run_id → its dropped subjects);
        the caller uses them to mark the folded run set.

        Raises on a collapse-guard trip or the §HISTORIC invariant inside
        ``run_all`` refusing to alter a slice the raw layer cannot regenerate —
        the caller fails the batch's clean runs and leaves the flag dirty.

        ``force_transform`` (re-drive path) skips the 0-row skip-clean economics
        so a swept orphaned-``landed`` backlog is always transformed.

        The empty-raw floor is BYPASSED whenever ``scope_run_ids`` is non-empty:
        the scoped path writes only the batch's subjects and the subject-grain
        §HISTORIC guard (not a global row floor) is the safety mechanism, so the
        floor — which would false-block a lean prod box (raw≈20) — is skipped.
        The floor still applies to a would-be unscoped full rebuild.
        """
        # 1. Kill-switch (PRIMARY). Prod stays False → never rebuilds. Leave the
        #    dirty flag set (raw is safe; cubes refresh where enabled).
        if not settings.INGESTION_TRANSFORMS_ENABLED:
            logger.info(
                "transforms DISABLED (kill-switch); leaving warehouse dirty, "
                "runs stay landed"
            )
            return _GateOutcome("disabled")

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
        if rows_this_batch == 0 and not force_transform:
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
                return _GateOutcome("skip_clean")
            logger.info(
                "batch landed 0 rows but warehouse pre-dirty → running transforms"
            )

        # 2. Empty-raw floor preflight (total-raw guard; catches prod raw=0).
        #    BYPASSED on the scoped path: with a non-empty scope the run writes
        #    only the batch's subjects and safety is the subject-grain §HISTORIC
        #    guard, not a global row floor (a lean prod box has raw≈20 which the
        #    floor would wrongly block). Only a would-be unscoped full rebuild
        #    still hits the floor. Bounded probe: stop counting at the floor.
        if not scope_run_ids:
            async with session_scope() as session:
                raw_total = await IngestionRunRepository(session).raw_total_count(
                    cap=settings.INGESTION_RAW_FLOOR
                )
            if raw_total < settings.INGESTION_RAW_FLOOR:
                raise RuntimeError(
                    f"transforms refused: raw layer empty/below floor "
                    f"(raw_total={raw_total} < {settings.INGESTION_RAW_FLOOR})"
                )

        # 3 + 4. Global mutex + scoped rebuild + atomic clear, all in ONE txn. A
        # crash mid-transform rolls back the cubes AND the clear together, so the
        # old cubes survive and the dirty flag stays set for the reaper.
        async with self._transform_session() as session:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:k)"), {"k": _TRANSFORM_LOCK_KEY}
            )
            # Long rebuild: uncap statement_timeout on this session (F26). The
            # jobs engine already uses the direct (non-pooler) DATABASE_URL.
            await session.execute(text("SET statement_timeout = 0"))

            fact_pre = await self._fact_count(session)
            xform_result = await run_transformations(
                session, scope_run_ids=scope_run_ids
            )
            fact_post = await self._fact_count(session)

            # Collapse-guard (kept): a scoped transform never truncates fact
            # globally (only subject-scoped DELETE), so fact_pre>0 → fact_post==0
            # still means a bug — RAISE so the txn rolls back and old cubes survive.
            if fact_pre > 0 and fact_post == 0:
                raise RuntimeError(
                    f"transform collapse-guard: fact_student_submission went "
                    f"{fact_pre} → 0; rolling back to preserve old cubes"
                )

            # Clear the dirty flag in the SAME txn as the rebuild → new cubes AND
            # a clean flag commit atomically.
            await IngestionRunRepository(session).clear_warehouse_dirty(run_id)

        failed_run_ids = _extract_failed_run_ids(xform_result)
        pruned_subjects = _extract_pruned_subjects(xform_result)
        qd_only_noop = bool(
            getattr(getattr(xform_result, "scope", None), "qd_only_noop", False)
        )
        logger.info(
            "transforms applied (driver run %s): fact %d rows%s%s",
            run_id, fact_post,
            "; QD-only no-op (no submissions, nothing built)" if qd_only_noop else "",
            f"; {len(failed_run_ids)} run(s) roster-pruned" if failed_run_ids else "",
        )
        return _GateOutcome(
            outcome="applied",
            failed_run_ids=tuple(failed_run_ids),
            qd_only_noop=qd_only_noop,
            pruned_subjects=pruned_subjects,
        )

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

    async def _scope_run_ids(self, landed: List[Dict[str, Any]]) -> List[str]:
        """Discovery scope for the scoped transform: this batch's run_ids ∪ every
        run still ``landed`` (a prior crash between landing and transform-mark).
        Their raw is folded idempotently; ``run_all`` derives the touched
        subject set S from it (pass A → pass B)."""
        ids = {str(r["run_id"]) for r in landed}
        async with session_scope() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT run_id::text FROM ingestion_runs "
                        "WHERE status = 'landed'"
                    )
                )
            ).all()
        ids.update(row[0] for row in rows)
        return sorted(ids)

    async def _finalize_succeeded(
        self,
        run_id: str,
        *,
        transforms_applied: bool,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark a run ``succeeded`` AND set the ``transforms_applied`` COLUMN.

        ``mark(..., details)`` only merges into the ``error_details`` jsonb; the
        P6 self-healing purge keys off the ``transforms_applied`` COLUMN, so set
        it explicitly (same txn) — otherwise transformed raw would never be
        swept. ``details`` is ``None`` for a clean success so ``error_details``
        stays error-only (#25 — never write ``transforms_applied`` into it); a
        run that landed with file errors but whose subjects still applied passes
        a small ``landing_note`` (#4/#8)."""
        async with session_scope() as session:
            repo = IngestionRunRepository(session)
            await repo.mark(run_id, "succeeded", details)
            await session.execute(
                text(
                    "UPDATE ingestion_runs SET transforms_applied = :ta "
                    "WHERE run_id = CAST(:rid AS UUID)"
                ),
                {"ta": transforms_applied, "rid": run_id},
            )

    async def _post_commit_maintenance(self, *, purge: bool) -> None:
        """POST-COMMIT (separate AUTOCOMMIT conn): optional self-healing raw purge
        then VACUUM(ANALYZE) of the scoped-touched tables. Runs only AFTER the
        transform txn committed and the runs are marked.

        Fail-open-loud: every error is logged and swallowed so a maintenance
        hiccup never fails an already-applied, already-committed run. VACUUM
        cannot run inside a txn, so this uses an AUTOCOMMIT connection (each
        statement is its own txn)."""
        engine = get_engine()
        try:
            async with engine.connect() as conn:
                conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
                purged = 0
                if purge:
                    purged = await self._purge_transformed_raw(conn)
                tables = list(_SCOPED_TOUCHED_TABLES)
                if purged:
                    tables += list(_RAW_TABLES)
                for tbl in tables:
                    try:
                        # PARALLEL 0 disables parallel index vacuuming, which
                        # allocates dynamic shared-memory segments — those fail
                        # on a container with a small /dev/shm ("could not resize
                        # shared memory segment ... No space left on device") for
                        # the large tables (fact, cube_user_summary). Serial
                        # vacuum is fine here and portable across shm sizes.
                        await conn.execute(text(f"VACUUM (ANALYZE, PARALLEL 0) {tbl}"))
                    except Exception:  # noqa: BLE001 — one absent table must not stop the rest
                        logger.warning(
                            "post-commit VACUUM of %s failed (continuing)",
                            tbl, exc_info=True,
                        )
        except Exception:  # noqa: BLE001 — transform already committed; never fail it
            logger.exception(
                "post-commit maintenance failed (transform already committed; "
                "ignoring)"
            )

    async def _purge_transformed_raw(self, conn: Any) -> int:
        """Self-healing sweep (P6): DELETE raw for EVERY run already folded into
        fact (``status='succeeded' AND transforms_applied=true``) — not just this
        batch, so a previously-orphaned run's raw is reclaimed on the next
        ingest. Failed / pruned / landed runs' raw is RETAINED (retry material).
        Chunked so each DELETE stays well under any statement timeout. Returns
        the total rows deleted."""
        total = 0
        for tbl in _RAW_TABLES:
            while True:
                res = await conn.execute(
                    text(
                        f"""
                        WITH victims AS (
                            SELECT ctid FROM {tbl}
                            WHERE ingestion_run_id IN (
                                SELECT run_id FROM ingestion_runs
                                WHERE status = 'succeeded'
                                  AND transforms_applied = true
                            )
                            LIMIT :chunk
                        )
                        DELETE FROM {tbl} WHERE ctid IN (SELECT ctid FROM victims)
                        """
                    ),
                    {"chunk": _PURGE_CHUNK},
                )
                deleted = res.rowcount or 0
                total += deleted
                if deleted < _PURGE_CHUNK:
                    break
        if total:
            logger.info(
                "post-commit purge: deleted %d transformed raw row(s)", total
            )
        return total

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
