"""Role repository."""

from typing import Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.role import Role
from app.models.role_permission import RolePermission
from app.repositories.base_repository import BaseRepository


class RoleRepository(BaseRepository[Role]):
    """Repository for Role model."""

    def __init__(self, session: AsyncSession):
        super().__init__(Role, session)

    async def set_hierarchy_levels(self, updates: Dict[str, int]) -> None:
        """Bulk-assign ``hierarchy_level`` to non-system roles (for reorder).

        The ``is_system`` guard is belt-and-suspenders — the DB trigger already
        blocks changing a system role's hierarchy — so a system id in the map is
        a silent no-op rather than an error.
        """
        for role_id, level in updates.items():
            await self.session.execute(
                update(Role)
                .where(Role.id == role_id, Role.is_system.is_(False))
                .values(hierarchy_level=level)
            )

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
