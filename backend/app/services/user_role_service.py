"""User role service with business logic."""

from typing import List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DuplicateResourceError,
    HierarchyViolationError,
    ImmutableResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from app.models.user_role import UserRole
from app.repositories.role_repository import RoleRepository
from app.repositories.user_role_repository import UserRoleRepository
from app.schemas.auth import CurrentUser


def validate_hierarchy(
    actor_hierarchy: int, target_hierarchy: int, actor_is_super: bool
) -> None:
    """Validate that an actor can operate on a target based on hierarchy levels."""
    if actor_is_super:
        if target_hierarchy > actor_hierarchy:
            raise HierarchyViolationError(actor_hierarchy, target_hierarchy)
    else:
        if target_hierarchy >= actor_hierarchy:
            raise HierarchyViolationError(actor_hierarchy, target_hierarchy)


class UserRoleService:
    """Service for user role management."""

    def __init__(self, session: AsyncSession):
        self.repository = UserRoleRepository(session)
        self.role_repository = RoleRepository(session)

    async def _get_target_user_info(self, user_id: str) -> Tuple[int, bool]:
        """
        Get target user's highest hierarchy level and superadmin status in a single query.

        Args:
            user_id: User ID

        Returns:
            Tuple of (highest_hierarchy_level, is_superadmin)
        """
        user_roles = await self.repository.list_by_user(user_id)
        if not user_roles:
            return 0, False
        highest = max(ur.role.hierarchy_level for ur in user_roles)
        is_super = any(ur.role.name == "super_admin" for ur in user_roles)
        return highest, is_super

    async def list_user_roles(self, user_id: str) -> List[UserRole]:
        """
        List all roles for a user.

        Args:
            user_id: User ID

        Returns:
            List of UserRole instances with role details
        """
        return await self.repository.list_by_user(user_id)

    async def assign_role(
        self, user_id: str, role_id: str, current_user: CurrentUser
    ) -> UserRole:
        """
        Assign a role to a user.

        Args:
            user_id: User ID
            role_id: Role ID to assign
            current_user: Current authenticated user

        Returns:
            Created UserRole instance

        Raises:
            ResourceNotFoundError: If role not found
            DuplicateResourceError: If user already has this role
            HierarchyViolationError: If attempting to assign higher privilege role or modify higher hierarchy user
            ImmutableResourceError: If attempting to assign super_admin role
        """
        role = await self.role_repository.get(role_id)
        if not role:
            raise ResourceNotFoundError("Role", role_id)

        target_user_hierarchy, target_is_superadmin = await self._get_target_user_info(user_id)

        if target_is_superadmin:
            raise ImmutableResourceError(
                "User",
                user_id,
                "Superadmin users cannot be modified through the system",
            )

        if current_user.user_role != "super_admin":
            if target_user_hierarchy >= current_user.hierarchy_level:
                raise HierarchyViolationError(
                    current_user.hierarchy_level,
                    target_user_hierarchy,
                    message=f"Cannot modify roles for user with hierarchy {target_user_hierarchy}. Your hierarchy: {current_user.hierarchy_level}",
                )

        # Explicit super_admin block
        if role.name == "super_admin":
            raise ImmutableResourceError(
                "Role",
                "super_admin",
                "Cannot manually assign super_admin role. It is auto-assigned to the first registered user only.",
            )

        # Hierarchy check: Can't assign role with higher/equal hierarchy than own (except super_admin)
        if current_user.user_role != "super_admin":
            if role.hierarchy_level >= current_user.hierarchy_level:
                raise HierarchyViolationError(
                    current_user.hierarchy_level, role.hierarchy_level
                )
        else:
            # Super admin still cannot assign roles higher than themselves (shouldn't exist, but defense in depth)
            if role.hierarchy_level > current_user.hierarchy_level:
                raise HierarchyViolationError(
                    current_user.hierarchy_level, role.hierarchy_level
                )

        # Check if user already has this role
        existing = await self.repository.get_by_user_and_role(user_id, role_id)
        if existing:
            raise DuplicateResourceError("UserRole", "role_id", role_id)

        # Create user role assignment
        user_role = UserRole(user_id=user_id, role_id=role_id)
        return await self.repository.create(user_role)

    async def remove_role(
        self, user_id: str, role_id: str, current_user: CurrentUser
    ) -> bool:
        """
        Remove a role from a user.

        Args:
            user_id: User ID
            role_id: Role ID to remove
            current_user: Current authenticated user

        Returns:
            True if deleted, False if not found

        Raises:
            HierarchyViolationError: If attempting to remove higher privilege role or modify higher hierarchy user
            ValidationError: If attempting to remove own only/highest role
        """
        target_user_hierarchy, target_is_superadmin = await self._get_target_user_info(user_id)

        if target_is_superadmin:
            raise ImmutableResourceError(
                "User",
                user_id,
                "Superadmin users cannot be modified through the system",
            )

        if current_user.user_role != "super_admin":
            if target_user_hierarchy >= current_user.hierarchy_level:
                raise HierarchyViolationError(
                    current_user.hierarchy_level,
                    target_user_hierarchy,
                    message=f"Cannot modify roles for user with hierarchy {target_user_hierarchy}. Your hierarchy: {current_user.hierarchy_level}",
                )

        # Self-demotion protection: prevent users from removing their own roles
        if user_id == current_user.user_id:
            user_roles = await self.repository.list_by_user(user_id)

            if len(user_roles) == 1:
                raise ValidationError(
                    "Cannot remove your only role. Assign a new role first.",
                    field="role_id",
                )

            role_to_remove = await self.role_repository.get(role_id)
            if role_to_remove:
                highest_hierarchy = max(ur.role.hierarchy_level for ur in user_roles)
                if role_to_remove.hierarchy_level == highest_hierarchy:
                    raise ValidationError(
                        "Cannot remove your highest role. This would demote you and you may lose access.",
                        field="role_id",
                    )

        # Check role hierarchy
        role = await self.role_repository.get(role_id)
        if role:
            is_super = current_user.user_role == "super_admin"
            validate_hierarchy(current_user.hierarchy_level, role.hierarchy_level, is_super)

        return await self.repository.delete_by_user_and_role(user_id, role_id)
