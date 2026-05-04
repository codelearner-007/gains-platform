"""Dashboard statistics repository."""

from datetime import datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.permission import Permission
from app.models.role import Role
from app.models.user_role import UserRole


class DashboardRepository:
    """Repository for dashboard aggregate queries."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def count_roles(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Role)
        )
        return result.scalar() or 0

    async def count_permissions(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Permission)
        )
        return result.scalar() or 0

    async def count_users_with_roles(self) -> int:
        result = await self.session.execute(
            select(func.count(distinct(UserRole.user_id))).select_from(UserRole)
        )
        return result.scalar() or 0

    async def count_audit_logs(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(AuditLog)
        )
        return result.scalar() or 0

    async def count_audit_logs_since(self, since: datetime) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.created_at >= since
            )
        )
        return result.scalar() or 0
