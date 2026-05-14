"""Service for the dimension lookup endpoints."""

from __future__ import annotations

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.dim_repository import DimRepository
from app.schemas.dim import (
    GradeRow,
    SectionRow,
    SessionRow,
    StandardRow,
    StrandRow,
    SubjectRow,
)


class DimService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = DimRepository(session)

    async def list_standards(self) -> List[StandardRow]:
        rows = await self.repo.list_standards()
        return [StandardRow.model_validate(r) for r in rows]

    async def list_strands(self) -> List[StrandRow]:
        rows = await self.repo.list_strands()
        return [StrandRow.model_validate(r) for r in rows]

    async def list_subjects(self) -> List[SubjectRow]:
        rows = await self.repo.list_subjects()
        return [SubjectRow.model_validate(r) for r in rows]

    async def list_grades(self) -> List[GradeRow]:
        rows = await self.repo.list_grades()
        return [GradeRow.model_validate(r) for r in rows]

    async def list_sections(self) -> List[SectionRow]:
        rows = await self.repo.list_sections()
        return [SectionRow.model_validate(r) for r in rows]

    async def list_sessions(self) -> List[SessionRow]:
        rows = await self.repo.list_sessions()
        return [SessionRow.model_validate(r) for r in rows]
