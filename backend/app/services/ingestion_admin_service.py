"""Service for the admin/ingestion endpoints."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.repositories.school_repository import SchoolRepository
from app.schemas.admin import (
    IngestionRunResponse,
    TriggerIngestionRequest,
    TriggerIngestionResponse,
)
from app.services.ingestion_dispatch import enqueue


class IngestionAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = IngestionRunRepository(session)
        self.schools = SchoolRepository(session)

    async def list_runs(
        self, school_id: Optional[str] = None, limit: int = 100
    ) -> List[IngestionRunResponse]:
        rows = await self.repo.list_runs(school_id=school_id, limit=limit)
        return [IngestionRunResponse.model_validate(r) for r in rows]

    async def get_run(self, run_id: str) -> IngestionRunResponse:
        row = await self.repo.get(run_id)
        if not row:
            raise ResourceNotFoundError("IngestionRun", run_id)
        return IngestionRunResponse.model_validate(row)

    async def resolve_short_name(self, school_id: Optional[str]) -> Optional[str]:
        """Resolve a school UUID to its ``short_name`` for dispatch (R10).

        ``run_ingestion``'s ``school_filter`` matches on
        ``short_name``/``schoology_building_id``/``name`` only — a bare UUID never
        matches — so we translate ``TriggerIngestionRequest.school_id`` (a UUID)
        to the school's ``short_name`` before dispatching. ``None`` (no school
        selected) passes through as ``None`` → an all-schools run.
        """
        if school_id is None:
            return None
        school = await self.schools.get(school_id)
        if not school:
            raise ResourceNotFoundError("School", school_id)
        return school["short_name"]

    async def trigger_run(
        self, payload: TriggerIngestionRequest
    ) -> TriggerIngestionResponse:
        """Enqueue a run for the durable worker (coalescing on an existing pending).

        Routes through ``enqueue`` so a second trigger for a school that already
        has a queued run returns that run instead of creating a duplicate
        (HARDENING_PLAN §4). The caller commits.
        """
        row = await enqueue(
            self.repo, school_id=payload.school_id, note=payload.note
        )
        return TriggerIngestionResponse(
            run_id=row["run_id"],
            status=row["status"],
            started_at=row["started_at"],
        )
