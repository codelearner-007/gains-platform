"""Permission repository."""

from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission import Permission
from app.repositories.base_repository import BaseRepository


class PermissionRepository(BaseRepository[Permission]):
    """Repository for Permission model."""

    def __init__(self, session: AsyncSession):
        super().__init__(Permission, session)

    async def get_by_module_action(
        self, module: str, action: str
    ) -> Optional[Permission]:
        """
        Get permission by module and action.

        Args:
            module: Module name
            action: Action name

        Returns:
            Permission instance or None
        """
        result = await self.session.execute(
            select(Permission).where(
                Permission.module == module, Permission.action == action
            )
        )
        return result.scalar_one_or_none()

    async def list_grouped_by_module(self) -> Dict[str, List[Permission]]:
        """
        List all permissions grouped by module.

        Returns:
            Dictionary mapping module name to list of permissions
        """
        result = await self.session.execute(
            select(Permission).order_by(Permission.module, Permission.action)
        )
        permissions = result.scalars().all()

        grouped: Dict[str, List[Permission]] = {}
        for perm in permissions:
            if perm.module not in grouped:
                grouped[perm.module] = []
            grouped[perm.module].append(perm)

        return grouped

    async def get_by_ids(self, permission_ids: List[str]) -> List[Permission]:
        """
        Get permissions by list of IDs.

        Args:
            permission_ids: List of permission IDs

        Returns:
            List of Permission instances
        """
        result = await self.session.execute(
            select(Permission).where(Permission.id.in_(permission_ids))
        )
        return list(result.scalars().all())
