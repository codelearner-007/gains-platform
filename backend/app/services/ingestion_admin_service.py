"""Service for the admin/ingestion endpoints."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.schemas.admin import (
    IngestionRunResponse,
    TriggerIngestionRequest,
    TriggerIngestionResponse,
)


class IngestionAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = IngestionRunRepository(session)

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

    async def trigger_run(
        self, payload: TriggerIngestionRequest
    ) -> TriggerIngestionResponse:
        row = await self.repo.create_pending(
            school_id=payload.school_id, note=payload.note
        )
        return TriggerIngestionResponse(
            run_id=row["run_id"],
            status=row["status"],
            started_at=row["started_at"],
        )
