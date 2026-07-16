"""Admin overview service — assembles the owner-grade stats payload."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.admin_stats_repository import AdminStatsRepository
from app.schemas.response.admin_stats import (
    ActivityEntry,
    AdminOverviewResponse,
    IngestionHealth,
    PendingInvite,
    PeopleStats,
    RoleDistribution,
    SchoolCoverage,
    SchoolUserDistribution,
)

# A school whose newest assessment is older than this is flagged "stale".
STALE_AFTER_DAYS = 30


class AdminStatsService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = AdminStatsRepository(session)

    async def get_overview(self) -> AdminOverviewResponse:
        now = datetime.now(timezone.utc)
        today = now.date()

        people = await self.repo.people()
        pending = await self.repo.pending_invites()
        roles = await self.repo.users_per_role()
        schools_users = await self.repo.users_per_school()
        coverage = await self.repo.coverage()
        activity = await self.repo.recent_activity()
        ingestion = await self.repo.latest_ingestion()

        coverage_rows = []
        for c in coverage:
            last = c.get("last_assessment_date")
            is_stale = bool(last and (today - last).days > STALE_AFTER_DAYS)
            coverage_rows.append(
                SchoolCoverage(
                    school_id=c["school_id"],
                    name=c["name"],
                    short_name=c.get("short_name"),
                    logo_url=c.get("logo_url"),
                    is_active=bool(c.get("is_active", True)),
                    current_session=c.get("current_session"),
                    assessments=c.get("assessments") or 0,
                    students=c.get("students") or 0,
                    subjects=c.get("subjects") or 0,
                    sessions_covered=c.get("sessions_covered") or 0,
                    last_assessment_date=last,
                    is_stale=is_stale,
                )
            )

        return AdminOverviewResponse(
            people=PeopleStats(**people),
            pending_invites=[PendingInvite(**p) for p in pending],
            roles=[RoleDistribution(**r) for r in roles],
            schools_users=[SchoolUserDistribution(**s) for s in schools_users],
            coverage=coverage_rows,
            recent_activity=[ActivityEntry(**a) for a in activity],
            ingestion=IngestionHealth(**ingestion) if ingestion else None,
            generated_at=now,
        )
