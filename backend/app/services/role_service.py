"""Role service with business logic."""

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DuplicateResourceError,
    HierarchyViolationError,
    ImmutableResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from app.models.role import Role
from app.repositories.permission_repository import PermissionRepository
from app.repositories.role_repository import RoleRepository
from app.schemas.auth import CurrentUser
from app.schemas.request.role import CreateRoleRequest, UpdateRoleRequest


class RoleService:
    """Service for role management."""

    def __init__(self, session: AsyncSession):
        self.repository = RoleRepository(session)
        self.permission_repository = PermissionRepository(session)

    async def list_roles(self) -> List[Role]:
        """List all roles."""
        return await self.repository.list()

    async def get_role(self, role_id: str) -> Role:
        """
        Get role by ID.

        Args:
            role_id: Role ID

        Returns:
            Role instance

        Raises:
            ResourceNotFoundError: If role not found
        """
        role = await self.repository.get(role_id)
        if not role:
            raise ResourceNotFoundError("Role", role_id)
        return role

    async def get_role_with_permissions(self, role_id: str) -> Role:
        """
        Get role with permissions.

        Args:
            role_id: Role ID

        Returns:
            Role instance with permissions

        Raises:
            ResourceNotFoundError: If role not found
        """
        role = await self.repository.get_with_permissions(role_id)
        if not role:
            raise ResourceNotFoundError("Role", role_id)
        return role

    async def create_role(
        self, role_data: CreateRoleRequest, current_user: CurrentUser
    ) -> Role:
        """
        Create a new role.

        Args:
            role_data: Role creation data
            current_user: Current authenticated user

        Returns:
            Created role instance

        Raises:
            DuplicateResourceError: If role name already exists
            HierarchyViolationError: If creating role with higher hierarchy than current user
        """
        # Check if role name already exists
        existing = await self.repository.get_by_name(role_data.name)
        if existing:
            raise DuplicateResourceError("Role", "name", role_data.name)

        # Hierarchy check: Can't create role with higher/equal hierarchy than own (except super_admin)
        if current_user.user_role != "super_admin":
            if role_data.hierarchy_level >= current_user.hierarchy_level:
                raise HierarchyViolationError(
                    current_user.hierarchy_level, role_data.hierarchy_level
                )
        else:
            # Super admin still cannot create roles higher than themselves (defense in depth)
            if role_data.hierarchy_level > current_user.hierarchy_level:
                raise HierarchyViolationError(
                    current_user.hierarchy_level, role_data.hierarchy_level
                )

        role = Role(
            name=role_data.name,
            description=role_data.description,
            hierarchy_level=role_data.hierarchy_level,
        )
        return await self.repository.create(role)

    async def update_role(
        self,
        role_id: str,
        role_data: UpdateRoleRequest,
        current_user: CurrentUser,
    ) -> Role:
        """
        Update an existing role.

        Args:
            role_id: Role ID
            role_data: Role update data
            current_user: Current authenticated user

        Returns:
            Updated role instance

        Raises:
            ResourceNotFoundError: If role not found
            DuplicateResourceError: If new name conflicts with existing role
            HierarchyViolationError: If attempting to update role with higher hierarchy
            ImmutableResourceError: If attempting to modify system role
        """
        role = await self.get_role(role_id)

        # Block system role modification
        if role.is_system:
            raise ImmutableResourceError(
                "Role", role.name, "System roles cannot be modified"
            )

        # Hierarchy check: Can't update role with higher/equal hierarchy than own (except super_admin)
        if current_user.user_role != "super_admin":
            if role.hierarchy_level >= current_user.hierarchy_level:
                raise HierarchyViolationError(
                    current_user.hierarchy_level, role.hierarchy_level
                )
        else:
            # Super admin still cannot update roles higher than themselves (defense in depth)
            if role.hierarchy_level > current_user.hierarchy_level:
                raise HierarchyViolationError(
                    current_user.hierarchy_level, role.hierarchy_level
                )

        # Check name uniqueness if name is being changed
        if role_data.name and role_data.name != role.name:
            existing = await self.repository.get_by_name(role_data.name)
            if existing:
                raise DuplicateResourceError("Role", "name", role_data.name)

        # Check new hierarchy level
        if role_data.hierarchy_level:
            if current_user.user_role != "super_admin":
                if role_data.hierarchy_level >= current_user.hierarchy_level:
                    raise HierarchyViolationError(
                        current_user.hierarchy_level, role_data.hierarchy_level
                    )
            else:
                # Super admin still cannot set hierarchy higher than themselves (defense in depth)
                if role_data.hierarchy_level > current_user.hierarchy_level:
                    raise HierarchyViolationError(
                        current_user.hierarchy_level, role_data.hierarchy_level
                    )

        update_data = role_data.model_dump(exclude_unset=True)
        return await self.repository.update(role, update_data)

    async def delete_role(self, role_id: str, current_user: CurrentUser) -> None:
        """
        Delete a role.

        Args:
            role_id: Role ID
            current_user: Current authenticated user

        Raises:
            ResourceNotFoundError: If role not found
            HierarchyViolationError: If attempting to delete role with higher hierarchy
            ValidationError: If attempting to delete system roles
        """
        role = await self.get_role(role_id)

        # Prevent deletion of system roles (check before hierarchy to give clearer error)
        if role.is_system:
            raise ValidationError(
                f"Cannot delete system role: {role.name}", field="role_id"
            )

        # Hierarchy check
        if current_user.user_role != "super_admin":
            if role.hierarchy_level >= current_user.hierarchy_level:
                raise HierarchyViolationError(
                    current_user.hierarchy_level, role.hierarchy_level
                )
        else:
            # Super admin still cannot delete roles higher than themselves (defense in depth)
            if role.hierarchy_level > current_user.hierarchy_level:
                raise HierarchyViolationError(
                    current_user.hierarchy_level, role.hierarchy_level
                )

        await self.repository.delete(role)

    async def assign_permissions(
        self,
        role_id: str,
        permission_ids: List[str],
        current_user: CurrentUser,
    ) -> Role:
        """
        Bulk assign permissions to a role.

        Args:
            role_id: Role ID
            permission_ids: List of permission IDs
            current_user: Current authenticated user

        Returns:
            Updated role with permissions

        Raises:
            ResourceNotFoundError: If role or permissions not found
            HierarchyViolationError: If attempting to modify role with higher hierarchy
            ImmutableResourceError: If attempting to modify super_admin permissions
        """
        role = await self.get_role(role_id)

        # Block system role permission modification (super_admin gets all permissions automatically)
        if role.is_system and role.name == "super_admin":
            raise ImmutableResourceError(
                "Role", role.name, "Cannot modify super_admin permissions"
            )

        # Hierarchy check
        if current_user.user_role != "super_admin":
            if role.hierarchy_level >= current_user.hierarchy_level:
                raise HierarchyViolationError(
                    current_user.hierarchy_level, role.hierarchy_level
                )
        else:
            # Super admin still cannot modify permissions of roles higher than themselves (defense in depth)
            if role.hierarchy_level > current_user.hierarchy_level:
                raise HierarchyViolationError(
                    current_user.hierarchy_level, role.hierarchy_level
                )

        # Verify all permissions exist
        permissions = await self.permission_repository.get_by_ids(permission_ids)
        if len(permissions) != len(permission_ids):
            found_ids = {p.id for p in permissions}
            missing_ids = set(permission_ids) - found_ids
            raise ResourceNotFoundError(
                "Permission", ", ".join(missing_ids)
            )

        # Assign permissions
        await self.repository.assign_permissions(role_id, permission_ids)

        # Return role with updated permissions
        return await self.get_role_with_permissions(role_id)
