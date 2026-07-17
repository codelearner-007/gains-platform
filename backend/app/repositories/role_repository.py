"""Role repository."""

from typing import Dict, List, Optional

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.role import Role
from app.models.role_permission import RolePermission
from app.repositories.base_repository import BaseRepository

# Advisory-lock key serializing all rank mutations (create/reorder/delete) so
# concurrent admins can't corrupt the contiguous 1..N custom-rank invariant.
ROLES_RANK_LOCK = 918_273_645


class RoleRepository(BaseRepository[Role]):
    """Repository for Role model."""

    def __init__(self, session: AsyncSession):
        super().__init__(Role, session)

    async def acquire_rank_lock(self) -> None:
        """Take the transaction-scoped advisory lock for rank mutations."""
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:k)"), {"k": ROLES_RANK_LOCK}
        )

    async def count_custom_roles(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Role).where(Role.is_system.is_(False))
        )
        return result.scalar() or 0

    async def set_hierarchy_ranks(self, updates: Dict[str, int]) -> None:
        """Bulk-assign ``hierarchy_rank`` to non-system roles (for reorder).

        The ``is_system`` guard is belt-and-suspenders — the DB trigger already
        blocks changing a system role's rank — so a system id in the map is a
        silent no-op rather than an error.
        """
        for role_id, rank in updates.items():
            await self.session.execute(
                update(Role)
                .where(Role.id == role_id, Role.is_system.is_(False))
                .values(hierarchy_rank=rank)
            )

    async def renumber_custom_ranks(self) -> None:
        """Restore the contiguous 1..N custom-rank invariant (senior-first).

        The universal invariant-restorer: a single ROW_NUMBER pass over the
        non-system roles ordered by current rank. Idempotent — a no-op when the
        ranks are already contiguous. Called after delete (gap close); safe to
        call anytime.
        """
        await self.session.execute(
            text(
                """
                UPDATE public.roles r SET hierarchy_rank = t.rn
                FROM (
                    SELECT id, ROW_NUMBER() OVER (ORDER BY hierarchy_rank) AS rn
                    FROM public.roles WHERE is_system = FALSE
                ) t
                WHERE r.id = t.id AND r.hierarchy_rank <> t.rn
                """
            )
        )
        # The raw UPDATE bypasses the identity map — expire cached Role objects so
        # any subsequent ORM read in this session returns the fresh ranks.
        self.session.expire_all()

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
