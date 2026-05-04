"""Permission service with business logic."""

from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateResourceError, ResourceNotFoundError
from app.models.permission import Permission
from app.repositories.permission_repository import PermissionRepository
from app.schemas.request.permission import CreatePermissionRequest


class PermissionService:
    """Service for permission management."""

    def __init__(self, session: AsyncSession):
        self.repository = PermissionRepository(session)

    async def list_permissions(self) -> List[Permission]:
        """List all permissions."""
        return await self.repository.list()

    async def list_grouped_by_module(self) -> Dict[str, List[Permission]]:
        """List permissions grouped by module."""
        return await self.repository.list_grouped_by_module()

    async def get_permission(self, permission_id: str) -> Permission:
        """
        Get permission by ID.

        Args:
            permission_id: Permission ID

        Returns:
            Permission instance

        Raises:
            ResourceNotFoundError: If permission not found
        """
        permission = await self.repository.get(permission_id)
        if not permission:
            raise ResourceNotFoundError("Permission", permission_id)
        return permission

    async def create_permission(
        self, permission_data: CreatePermissionRequest
    ) -> Permission:
        """
        Create a new permission.

        Args:
            permission_data: Permission creation data (name in module:action format)

        Returns:
            Created permission instance

        Raises:
            DuplicateResourceError: If permission already exists
        """
        # Parse module:action format
        module, action = permission_data.name.split(":")

        # Check if permission already exists
        existing = await self.repository.get_by_module_action(module, action)
        if existing:
            raise DuplicateResourceError("Permission", "name", permission_data.name)

        permission = Permission(
            module=module,
            action=action,
            description=permission_data.description,
        )
        return await self.repository.create(permission)

    async def delete_permission(self, permission_id: str) -> None:
        """
        Delete a permission.

        Args:
            permission_id: Permission ID

        Raises:
            ResourceNotFoundError: If permission not found
        """
        permission = await self.get_permission(permission_id)
        await self.repository.delete(permission)
