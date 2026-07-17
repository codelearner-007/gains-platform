"""Role service with business logic."""

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MAX_CUSTOM_ROLES
from app.core.exceptions import (
    DuplicateResourceError,
    ImmutableResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from app.models.role import Role
from app.repositories.permission_repository import PermissionRepository
from app.repositories.role_repository import RoleRepository
from app.schemas.auth import CurrentUser
from app.schemas.request.role import CreateRoleRequest, UpdateRoleRequest
from app.services.user_role_service import validate_hierarchy


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

        # Rank changes only via create / reorder / delete. A new role appends as
        # the MOST-JUNIOR custom role (rank = custom_count + 1); the admin then
        # drags it up. Serialized with reorder/delete via an advisory lock so
        # concurrent mutations can't corrupt the contiguous 1..N invariant.
        await self.repository.acquire_rank_lock()
        custom_count = await self.repository.count_custom_roles()
        if custom_count >= MAX_CUSTOM_ROLES:
            raise ValidationError(
                f"Maximum of {MAX_CUSTOM_ROLES} custom roles reached.", field="name"
            )
        new_rank = custom_count + 1

        # The actor must strictly outrank the new role's position (bottom-insert
        # is legal for any actor who can create roles at all).
        validate_hierarchy(current_user.hierarchy_rank, new_rank)

        role = Role(
            name=role_data.name,
            description=role_data.description,
            hierarchy_rank=new_rank,
        )
        return await self.repository.create(role)

    async def reorder_roles(
        self, ordered_role_ids: List[str], current_user: CurrentUser
    ) -> List[Role]:
        """Reassign contiguous ranks (1..N) from a drag-and-drop order.

        ``ordered_role_ids`` = the custom roles the actor may manage, most-senior
        first. It must be EXACTLY the set of manageable (strictly-junior) custom
        roles — no more, no less. Roles the actor cannot manage (the senior
        prefix, ranks 1..k) keep their positions bit-identically; the listed
        roles take ranks k+1..N in the given order. System roles never change.
        """
        await self.repository.acquire_rank_lock()
        roles = await self.repository.list()
        by_id = {r.id: r for r in roles}
        customs = [r for r in roles if not r.is_system]

        for role_id in ordered_role_ids:
            role = by_id.get(role_id)
            if role is None:
                raise ResourceNotFoundError("Role", role_id)
            if role.is_system:
                raise ValidationError(
                    "System roles cannot be reordered.", field="ordered_role_ids"
                )

        # The actor may only reorder roles strictly junior to itself; the request
        # must list all and only those. Seniors stay frozen at their leading ranks.
        manageable = [
            r for r in customs if r.hierarchy_rank > current_user.hierarchy_rank
        ]
        if set(ordered_role_ids) != {r.id for r in manageable}:
            raise ValidationError(
                "The reorder must list exactly the roles you can manage.",
                field="ordered_role_ids",
            )

        frozen = sorted(
            (r for r in customs if r.hierarchy_rank <= current_user.hierarchy_rank),
            key=lambda r: r.hierarchy_rank,
        )
        final_order = [r.id for r in frozen] + list(ordered_role_ids)
        updates = {rid: i + 1 for i, rid in enumerate(final_order)}
        await self.repository.set_hierarchy_ranks(updates)
        return await self.repository.list()

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

        # The actor must strictly outrank the role being updated.
        validate_hierarchy(current_user.hierarchy_rank, role.hierarchy_rank)

        # Check name uniqueness if name is being changed
        if role_data.name and role_data.name != role.name:
            existing = await self.repository.get_by_name(role_data.name)
            if existing:
                raise DuplicateResourceError("Role", "name", role_data.name)

        # Rank is never set here — it changes only via create/reorder/delete.
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

        # The actor must strictly outrank the role being deleted.
        validate_hierarchy(current_user.hierarchy_rank, role.hierarchy_rank)

        # Delete then re-close the rank gap so customs stay contiguous 1..N.
        await self.repository.acquire_rank_lock()
        await self.repository.delete(role)
        await self.repository.renumber_custom_ranks()

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

        # The actor must strictly outrank the role whose permissions change.
        validate_hierarchy(current_user.hierarchy_rank, role.hierarchy_rank)

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
