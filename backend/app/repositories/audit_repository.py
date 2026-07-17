"""Audit log repository."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, distinct, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.repositories.base_repository import BaseRepository


class AuditRepository(BaseRepository[AuditLog]):
    """Repository for AuditLog model."""

    def __init__(self, session: AsyncSession):
        super().__init__(AuditLog, session)

    def _apply_filters(
        self,
        query,
        module: Optional[str] = None,
        action: Optional[str] = None,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        q: Optional[str] = None,
    ):
        if module:
            query = query.where(AuditLog.module == module)
        if action:
            query = query.where(AuditLog.action == action)
        if user_id:
            query = query.where(AuditLog.user_id == user_id)
        if start_date:
            query = query.where(AuditLog.created_at >= start_date)
        if end_date:
            query = query.where(AuditLog.created_at <= end_date)
        if q:
            pattern = f"%{q}%"
            query = query.where(
                or_(
                    AuditLog.action.ilike(pattern),
                    AuditLog.resource_id.ilike(pattern),
                    func.cast(AuditLog.details, String).ilike(pattern),
                )
            )
        return query

    async def count_filtered(
        self,
        module: Optional[str] = None,
        action: Optional[str] = None,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        q: Optional[str] = None,
    ) -> int:
        query = self._apply_filters(
            select(func.count()).select_from(AuditLog),
            module, action, user_id, start_date, end_date, q,
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def list_filtered(
        self,
        offset: int = 0,
        limit: int = 20,
        module: Optional[str] = None,
        action: Optional[str] = None,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        q: Optional[str] = None,
    ) -> List[AuditLog]:
        query = self._apply_filters(
            select(AuditLog),
            module, action, user_id, start_date, end_date, q,
        )
        query = query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_distinct_modules(self) -> List[str]:
        query = select(distinct(AuditLog.module)).order_by(AuditLog.module)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_distinct_actions(self) -> List[str]:
        query = select(distinct(AuditLog.action)).order_by(AuditLog.action)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def emails_for_user_ids(self, user_ids: List[str]) -> dict[str, str]:
        """Bulk-map user_id → email from auth.users (for actor display)."""
        if not user_ids:
            return {}
        rows = await self.session.execute(
            text(
                "SELECT id::text AS id, email FROM auth.users "
                "WHERE id::text = ANY(:ids)"
            ),
            {"ids": list(user_ids)},
        )
        return {r.id: r.email for r in rows.all()}

    async def create_log(
        self,
        user_id: Optional[str],
        action: str,
        module: str,
        resource_id: Optional[str] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            module=module,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return await self.create(audit_log)
