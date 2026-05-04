"""Profile repository."""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_profile import UserProfile
from app.repositories.base_repository import BaseRepository


class ProfileRepository(BaseRepository[UserProfile]):
    """Repository for UserProfile model."""

    def __init__(self, session: AsyncSession):
        super().__init__(UserProfile, session)

    async def get_by_user_id(self, user_id: str) -> Optional[UserProfile]:
        """
        Get profile by user_id.

        Args:
            user_id: Auth user UUID

        Returns:
            UserProfile instance or None
        """
        return await self.get_by_field("user_id", user_id)

    async def create_profile(
        self,
        user_id: str,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        department: Optional[str] = None,
    ) -> UserProfile:
        """
        Create a new user profile.

        Args:
            user_id: Auth user UUID
            full_name: Optional full name
            avatar_url: Optional avatar URL
            department: Optional department

        Returns:
            Created UserProfile instance
        """
        profile = UserProfile(
            user_id=user_id,
            full_name=full_name,
            avatar_url=avatar_url,
            department=department,
        )
        return await self.create(profile)

    async def update_profile(self, user_profile: UserProfile, **kwargs: object) -> UserProfile:
        """
        Update profile fields.

        Args:
            user_profile: Existing UserProfile instance
            **kwargs: Fields to update

        Returns:
            Updated UserProfile instance
        """
        return await self.update(user_profile, kwargs)
