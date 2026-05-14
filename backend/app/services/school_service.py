"""Service for the admin/schools endpoints."""

from __future__ import annotations

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DuplicateResourceError,
    ResourceNotFoundError,
)
from app.repositories.school_repository import SchoolRepository
from app.schemas.admin import (
    CreateSchoolRequest,
    SchoolResponse,
    UpdateSchoolRequest,
)


class SchoolService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SchoolRepository(session)

    async def list_schools(self) -> List[SchoolResponse]:
        rows = await self.repo.list_all()
        return [SchoolResponse.model_validate(r) for r in rows]

    async def get_school(self, school_id: str) -> SchoolResponse:
        row = await self.repo.get(school_id)
        if not row:
            raise ResourceNotFoundError("School", school_id)
        return SchoolResponse.model_validate(row)

    async def create_school(self, payload: CreateSchoolRequest) -> SchoolResponse:
        existing = await self.repo.get_by_building_id(payload.schoology_building_id)
        if existing:
            raise DuplicateResourceError(
                "School", "schoology_building_id", payload.schoology_building_id
            )
        data = {
            k: v
            for k, v in payload.model_dump(exclude_unset=True).items()
            if v is not None
        }
        row = await self.repo.create(data)
        return SchoolResponse.model_validate(row)

    async def update_school(
        self, school_id: str, payload: UpdateSchoolRequest
    ) -> SchoolResponse:
        existing = await self.repo.get(school_id)
        if not existing:
            raise ResourceNotFoundError("School", school_id)

        data = {
            k: v
            for k, v in payload.model_dump(exclude_unset=True).items()
            if v is not None
        }
        # If building_id is being changed, ensure no collision
        new_building_id = data.get("schoology_building_id")
        if new_building_id and new_building_id != existing["schoology_building_id"]:
            collision = await self.repo.get_by_building_id(new_building_id)
            if collision and collision["school_id"] != school_id:
                raise DuplicateResourceError(
                    "School", "schoology_building_id", new_building_id
                )

        row = await self.repo.update(school_id, data)
        if not row:
            raise ResourceNotFoundError("School", school_id)
        return SchoolResponse.model_validate(row)
