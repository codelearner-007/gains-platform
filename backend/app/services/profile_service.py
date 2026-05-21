"""Profile service with business logic."""

import logging
from typing import Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import Client, create_client

from app.core.config import settings
from app.models.user_profile import UserProfile
from app.repositories.profile_repository import ProfileRepository
from app.schemas.request.profile import UpdateProfileRequest

logger = logging.getLogger(__name__)

AVATAR_BUCKET = "avatars"
MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 2MB

_supabase_client: Optional[Client] = None


def _get_supabase_client() -> Client:
    """Get or create the Supabase service-role client (lazy singleton)."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _supabase_client


class ProfileService:
    """Service for user profile management."""

    def __init__(self, session: AsyncSession):
        self.repository = ProfileRepository(session)

    async def get_or_create_profile(self, user_id: str) -> UserProfile:
        profile = await self.repository.get_by_user_id(user_id)
        if profile:
            return profile
        # Race window: handle_new_user trigger may insert concurrently.
        # If we hit the unique constraint, fetch the row the trigger created.
        try:
            return await self.repository.create_profile(user_id=user_id)
        except IntegrityError:
            existing = await self.repository.get_by_user_id(user_id)
            if existing is None:
                raise
            return existing

    async def update_profile(self, user_id: str, data: UpdateProfileRequest) -> UserProfile:
        profile = await self.get_or_create_profile(user_id)
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return profile
        return await self.repository.update_profile(profile, **update_data)

    async def upload_avatar(self, user_id: str, file: UploadFile) -> str:
        """Upload avatar image to Supabase Storage and update profile."""
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")

        content = await file.read()
        if len(content) > MAX_AVATAR_SIZE:
            raise HTTPException(status_code=400, detail="Avatar must be smaller than 2MB")

        ext_map = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/gif": "gif",
            "image/webp": "webp",
        }
        ext = ext_map.get(file.content_type, "jpg")
        storage_path = f"{user_id}/avatar.{ext}"

        client = _get_supabase_client()
        storage = client.storage.from_(AVATAR_BUCKET)

        try:
            storage.remove([storage_path])
        except Exception:
            pass

        storage.upload(
            storage_path,
            content,
            {"content-type": file.content_type, "upsert": "true"},
        )

        public_url = storage.get_public_url(storage_path)

        profile = await self.get_or_create_profile(user_id)
        await self.repository.update_profile(profile, avatar_url=public_url)

        return public_url
