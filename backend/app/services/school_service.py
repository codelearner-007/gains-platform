"""Service for the admin/schools endpoints."""

from __future__ import annotations

from typing import List, Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import Client, create_client

from app.core.config import settings
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

LOGO_BUCKET = "school-logos"
MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2MB

# content-type -> file extension (matches the bucket's allowed_mime_types)
_LOGO_EXT_MAP = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}

_supabase_client: Optional[Client] = None


def _get_supabase_client() -> Client:
    """Get or create the Supabase service-role client (lazy singleton)."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY
        )
    return _supabase_client


# Optional columns under a UNIQUE constraint: a blank string ('') is not a
# meaningful value and would collide with any other blank on the second insert
# (e.g. schools_schoology_school_id_key). Coerce blank/whitespace-only input to
# NULL so multiple "unset" rows coexist.
_NULLABLE_UNIQUE_FIELDS = ("schoology_school_id", "edvance_tenant_id")


def _blank_to_none(data: dict) -> dict:
    """Coerce blank/whitespace-only optional-unique fields to None in place."""
    for field in _NULLABLE_UNIQUE_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and value.strip() == "":
            data[field] = None
    return data


class SchoolService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SchoolRepository(session)

    async def list_schools(self) -> List[SchoolResponse]:
        rows = await self.repo.list_all()
        return [SchoolResponse.model_validate(r) for r in rows]

    async def list_accessible(
        self, *, is_super_admin: bool, school_ids: List[str]
    ) -> List[dict]:
        """Schools the caller may scope to (drives the switcher).

        Super-admins get every active school; members get only their own.
        """
        return await self.repo.list_accessible(
            all_active=is_super_admin, school_ids=school_ids
        )

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
        data = _blank_to_none(payload.model_dump(exclude_unset=True))
        data = {k: v for k, v in data.items() if v is not None}
        row = await self.repo.create(data)
        return SchoolResponse.model_validate(row)

    async def update_school(
        self, school_id: str, payload: UpdateSchoolRequest
    ) -> SchoolResponse:
        existing = await self.repo.get(school_id)
        if not existing:
            raise ResourceNotFoundError("School", school_id)

        raw = _blank_to_none(payload.model_dump(exclude_unset=True))
        # Keep explicit NULLs for the optional-unique fields (so a user can clear
        # a previously-set Schoology School ID); drop other unset/None values.
        data = {
            k: v
            for k, v in raw.items()
            if v is not None or k in _NULLABLE_UNIQUE_FIELDS
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

    async def upload_logo(self, school_id: str, file: UploadFile) -> SchoolResponse:
        """Upload a school logo to Supabase Storage and persist its public URL.

        Mirrors ProfileService.upload_avatar: the file is written server-side with
        the service-role client (which bypasses storage RLS), and schools.logo_url
        is updated with the resulting public URL.
        """
        existing = await self.repo.get(school_id)
        if not existing:
            raise ResourceNotFoundError("School", school_id)

        if not file.content_type or file.content_type not in _LOGO_EXT_MAP:
            raise HTTPException(
                status_code=400,
                detail="Logo must be a JPEG, PNG, GIF, or WebP image",
            )

        content = await file.read()
        if len(content) > MAX_LOGO_SIZE:
            raise HTTPException(status_code=400, detail="Logo must be smaller than 2MB")

        ext = _LOGO_EXT_MAP[file.content_type]
        storage_path = f"{school_id}/logo.{ext}"

        client = _get_supabase_client()
        storage = client.storage.from_(LOGO_BUCKET)

        # Remove any prior logo (any extension) so a format change leaves no orphan.
        for prior_ext in set(_LOGO_EXT_MAP.values()):
            try:
                storage.remove([f"{school_id}/logo.{prior_ext}"])
            except Exception:
                pass

        storage.upload(
            storage_path,
            content,
            {"content-type": file.content_type, "upsert": "true"},
        )

        public_url = storage.get_public_url(storage_path)

        row = await self.repo.update(school_id, {"logo_url": public_url})
        if not row:
            raise ResourceNotFoundError("School", school_id)
        return SchoolResponse.model_validate(row)
