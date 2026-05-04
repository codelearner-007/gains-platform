"""Role repository."""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.role import Role
from app.models.role_permission import RolePermission
from app.repositories.base_repository import BaseRepository


class RoleRepository(BaseRepository[Role]):
    """Repository for Role model."""

    def __init__(self, session: AsyncSession):
        super().__init__(Role, session)

    async def get_with_permissions(self, role_id: str) -> Optional[Role]:
        """
        Get role with permissions eagerly loaded.

        Args:
            role_id: Role ID

        Returns:
            Role instance with permissions or None
        """
        result = await self.session.execute(
            select(Role)
            .where(Role.id == role_id)
            .options(selectinload(Role.role_permissions).selectinload(RolePermission.permission))
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Role]:
        """
        Get role by name.

        Args:
            name: Role name

        Returns:
            Role instance or None
        """
        return await self.get_by_field("name", name)

    async def assign_permissions(
        self, role_id: str, permission_ids: List[str]
    ) -> None:
        """
        Bulk assign permissions to a role (replaces existing).

        Args:
            role_id: Role ID
            permission_ids: List of permission IDs to assign
        """
        # Delete existing permissions
        await self.session.execute(
            RolePermission.__table__.delete().where(RolePermission.role_id == role_id)
        )

        # Insert new permissions
        if permission_ids:
            role_permissions = [
                RolePermission(role_id=role_id, permission_id=perm_id)
                for perm_id in permission_ids
            ]
            self.session.add_all(role_permissions)

        await self.session.flush()
