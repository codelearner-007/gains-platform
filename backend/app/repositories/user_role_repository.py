"""User role repository."""

from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user_role import UserRole
from app.repositories.base_repository import BaseRepository


class UserRoleRepository(BaseRepository[UserRole]):
    """Repository for UserRole model."""

    def __init__(self, session: AsyncSession):
        super().__init__(UserRole, session)

    async def list_by_user(self, user_id: str) -> List[UserRole]:
        """
        List all roles for a user.

        Args:
            user_id: User ID

        Returns:
            List of UserRole instances with role details
        """
        result = await self.session.execute(
            select(UserRole)
            .where(UserRole.user_id == user_id)
            .options(selectinload(UserRole.role))
        )
        return list(result.scalars().all())

    async def list_by_users(self, user_ids: List[str]) -> Dict[str, List[UserRole]]:
        """
        Bulk fetch roles for multiple users (prevents N+1 query problem).

        Args:
            user_ids: List of user IDs

        Returns:
            Dict mapping user_id to list of UserRole instances
        """
        # Single query with eager loading
        result = await self.session.execute(
            select(UserRole)
            .where(UserRole.user_id.in_(user_ids))
            .options(selectinload(UserRole.role))  # Eager load role data
        )

        user_roles = result.scalars().all()

        # Group by user_id
        grouped: Dict[str, List[UserRole]] = {}
        for ur in user_roles:
            if ur.user_id not in grouped:
                grouped[ur.user_id] = []
            grouped[ur.user_id].append(ur)

        return grouped

    async def get_by_user_and_role(
        self, user_id: str, role_id: str
    ) -> UserRole | None:
        """
        Get user role assignment by user and role.

        Args:
            user_id: User ID
            role_id: Role ID

        Returns:
            UserRole instance or None
        """
        result = await self.session.execute(
            select(UserRole).where(
                UserRole.user_id == user_id, UserRole.role_id == role_id
            )
        )
        return result.scalar_one_or_none()

    async def delete_by_user_and_role(
        self, user_id: str, role_id: str
    ) -> bool:
        """
        Delete user role assignment.

        Args:
            user_id: User ID
            role_id: Role ID

        Returns:
            True if deleted, False if not found
        """
        user_role = await self.get_by_user_and_role(user_id, role_id)
        if user_role:
            await self.delete(user_role)
            return True
        return False
