"""Enqueue-only dispatch for scraper/admin-triggered ingestion runs.

**This module was rewritten for the durability hardening (HARDENING_PLAN §4).**
Execution no longer happens in a fire-and-forget ``BackgroundTask``. The
``ingestion_runs`` table is now a durable queue and a single in-process worker
(``app.services.ingestion_worker.IngestionWorker``, started in the FastAPI
lifespan) claims pending runs, lands their raw rows, runs the transform gate,
and marks them terminal — surviving restarts/redeploys via a lease + reaper.

So the endpoints' job is reduced to: pre-create a ``pending`` row (coalescing on
an existing pending run for the same school) and commit it. The worker does the
rest. ``enqueue(...)`` is the new entrypoint.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.repositories.ingestion_run_repository import IngestionRunRepository

logger = logging.getLogger("ingestion_dispatch")


async def enqueue(
    repo: IngestionRunRepository,
    *,
    school_id: Optional[str],
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Enqueue a run for the durable worker, coalescing on an existing pending.

    If a ``pending`` run already exists for this school (``school_id`` matched
    with ``IS NOT DISTINCT FROM`` so an all-schools ``NULL`` coalesces with other
    all-schools requests), return it instead of creating a duplicate. Otherwise
    create a fresh ``pending`` row. The CALLER commits — the row must be durable
    before the worker can claim it, and the caller owns the request transaction
    (and any sibling writes, e.g. an audit-log row).
    """
    existing = await repo.pending_for_school(school_id)
    if existing is not None:
        logger.info(
            "coalescing enqueue for school_id=%s onto pending run %s",
            school_id, existing["run_id"],
        )
        return existing
    created = await repo.create_pending(school_id=school_id, note=note)
    logger.info(
        "enqueued ingestion run %s for school_id=%s", created["run_id"], school_id
    )
    return created
