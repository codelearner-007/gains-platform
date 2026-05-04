"""Dashboard statistics service."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.dashboard_repository import DashboardRepository
from app.schemas.response.dashboard import DashboardStatsResponse


class DashboardService:
    """Service for dashboard statistics."""

    def __init__(self, session: AsyncSession):
        self.repository = DashboardRepository(session)

    async def get_stats(self) -> DashboardStatsResponse:
        total_roles = await self.repository.count_roles()
        total_permissions = await self.repository.count_permissions()
        total_users = await self.repository.count_users_with_roles()
        total_audit_logs = await self.repository.count_audit_logs()

        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        recent_activity_24h = await self.repository.count_audit_logs_since(yesterday)

        return DashboardStatsResponse(
            total_roles=total_roles,
            total_permissions=total_permissions,
            total_users=total_users,
            total_audit_logs=total_audit_logs,
            recent_activity_24h=recent_activity_24h,
        )
