"""User role service with business logic."""

from typing import List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import NO_ROLE_RANK
from app.core.exceptions import (
    HierarchyViolationError,
    ImmutableResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from app.models.user_role import UserRole
from app.repositories.role_repository import RoleRepository
from app.repositories.user_role_repository import UserRoleRepository
from app.schemas.auth import CurrentUser


def validate_hierarchy(actor_rank: int, target_rank: int) -> None:
    """An actor may act only on a STRICTLY more-junior target.

    Ranks are ordinals where LOWER = more senior. The actor's rank must be
    strictly less than the target's; equal ranks (peers) cannot manage each
    other. super_admin (rank 0) outranks everything structurally, so there is no
    numeric special case — its *protections* stay name/is_system-based elsewhere.
    """
    if target_rank <= actor_rank:
        raise HierarchyViolationError(actor_rank, target_rank)


class UserRoleService:
    """Service for user role management."""

    def __init__(self, session: AsyncSession):
        self.repository = UserRoleRepository(session)
        self.role_repository = RoleRepository(session)

    async def _get_target_user_info(self, user_id: str) -> Tuple[int, bool]:
        """Return the target user's EFFECTIVE rank and superadmin status.

        Effective rank = MIN(rank) over the user's roles (their most senior
        role). No roles → ``NO_ROLE_RANK`` (most junior — fail-closed, so a
        role-less user is manageable by any admin, never treated as senior).
        """
        user_roles = await self.repository.list_by_user(user_id)
        if not user_roles:
            return NO_ROLE_RANK, False
        effective_rank = min(ur.role.hierarchy_rank for ur in user_roles)
        is_super = any(ur.role.name == "super_admin" for ur in user_roles)
        return effective_rank, is_super

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

        If the user already has the role, the existing assignment is returned
        unchanged (idempotent).

        Raises:
            ResourceNotFoundError: If role not found
            HierarchyViolationError: If attempting to assign higher privilege role or modify higher hierarchy user
            ImmutableResourceError: If attempting to assign super_admin role
        """
        role = await self.role_repository.get(role_id)
        if not role:
            raise ResourceNotFoundError("Role", role_id)

        target_user_rank, target_is_superadmin = await self._get_target_user_info(user_id)

        if target_is_superadmin:
            raise ImmutableResourceError(
                "User",
                user_id,
                "Superadmin users cannot be modified through the system",
            )

        # The actor must strictly outrank the target user.
        validate_hierarchy(current_user.hierarchy_rank, target_user_rank)

        # Explicit super_admin block (string-based, never numeric).
        if role.name == "super_admin":
            raise ImmutableResourceError(
                "Role",
                "super_admin",
                "Cannot manually assign super_admin role. It is auto-assigned to the first registered user only.",
            )

        # ...and strictly outrank the role being assigned.
        validate_hierarchy(current_user.hierarchy_rank, role.hierarchy_rank)

        # Idempotent: if the user already has this role (e.g. the default 'user'
        # role auto-assigned by the handle_new_user trigger), return the existing
        # assignment instead of raising 409. This lets the invite flow re-assert
        # the role harmlessly and proceed to grant school memberships.
        existing = await self.repository.get_by_user_and_role(user_id, role_id)
        if existing:
            return existing

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
        target_user_rank, target_is_superadmin = await self._get_target_user_info(user_id)

        if target_is_superadmin:
            raise ImmutableResourceError(
                "User",
                user_id,
                "Superadmin users cannot be modified through the system",
            )

        validate_hierarchy(current_user.hierarchy_rank, target_user_rank)

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
                # Most senior = lowest rank.
                most_senior_rank = min(ur.role.hierarchy_rank for ur in user_roles)
                if role_to_remove.hierarchy_rank == most_senior_rank:
                    raise ValidationError(
                        "Cannot remove your most senior role. This would demote you and you may lose access.",
                        field="role_id",
                    )

        # Check role hierarchy
        role = await self.role_repository.get(role_id)
        if role:
            validate_hierarchy(current_user.hierarchy_rank, role.hierarchy_rank)

        return await self.repository.delete_by_user_and_role(user_id, role_id)
