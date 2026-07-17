"""Cross-school aggregate queries for the admin overview.

Uses the plain ``get_db`` session: the backend connects as the ``postgres`` role
which is ``BYPASSRLS`` and the per-tenant tables are not ``FORCE`` RLS, so a
straight ``GROUP BY school_id`` aggregate sees every school — no per-school
``SET LOCAL`` loop and no service_role client (see R5 overview-SQL probe).

All queries are read-only. SQL and predicates are the ones the R5 probe
EXPLAIN-verified as correct + fast (people ~0.1ms, coverage ~9ms via LATERAL).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class AdminStatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def people(self) -> Dict[str, int]:
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT
                      count(*) FILTER (WHERE deleted_at IS NULL) AS total,
                      count(*) FILTER (WHERE deleted_at IS NULL
                        AND last_sign_in_at >= now() - interval '7 days')  AS active_7d,
                      count(*) FILTER (WHERE deleted_at IS NULL
                        AND last_sign_in_at >= now() - interval '30 days') AS active_30d,
                      count(*) FILTER (WHERE deleted_at IS NULL
                        AND invited_at IS NOT NULL
                        AND email_confirmed_at IS NULL) AS pending_invites,
                      count(*) FILTER (WHERE deleted_at IS NULL
                        AND banned_until IS NOT NULL
                        AND banned_until > now()) AS banned
                    FROM auth.users
                    """
                )
            )
        ).one()
        return {
            "total": row.total or 0,
            "active_7d": row.active_7d or 0,
            "active_30d": row.active_30d or 0,
            "pending_invites": row.pending_invites or 0,
            "banned": row.banned or 0,
        }

    async def pending_invites(self) -> List[Dict[str, Any]]:
        rows = await self.session.execute(
            text(
                """
                SELECT id::text AS id, email, invited_at
                FROM auth.users
                WHERE invited_at IS NOT NULL
                  AND email_confirmed_at IS NULL
                  AND deleted_at IS NULL
                ORDER BY invited_at DESC
                LIMIT 25
                """
            )
        )
        return [dict(r._mapping) for r in rows.all()]

    async def users_per_role(self) -> List[Dict[str, Any]]:
        rows = await self.session.execute(
            text(
                """
                SELECT r.id::text AS role_id, r.name,
                       count(ur.user_id) AS users
                FROM roles r
                LEFT JOIN user_roles ur ON ur.role_id = r.id
                GROUP BY r.id, r.name, r.hierarchy_rank
                ORDER BY r.hierarchy_rank ASC
                """
            )
        )
        return [dict(r._mapping) for r in rows.all()]

    async def users_per_school(self) -> List[Dict[str, Any]]:
        rows = await self.session.execute(
            text(
                """
                SELECT s.school_id::text AS school_id, s.name, s.short_name,
                       count(us.user_id) AS users
                FROM schools s
                LEFT JOIN user_schools us ON us.school_id = s.school_id
                GROUP BY s.school_id, s.name, s.short_name
                ORDER BY s.name
                """
            )
        )
        return [dict(r._mapping) for r in rows.all()]

    async def coverage(self) -> List[Dict[str, Any]]:
        # LATERAL per-school sub-aggregates (a flat multi-join Cartesian-explodes;
        # see R5 W-DATA). Each LATERAL is a small index-only scan.
        rows = await self.session.execute(
            text(
                """
                SELECT s.school_id::text AS school_id, s.name, s.short_name,
                       s.logo_url, s.is_active, s.current_session,
                       a.assessments, a.last_assessment_date,
                       st.students, css.subjects, sess.sessions_covered
                FROM schools s
                LEFT JOIN LATERAL (
                    SELECT count(DISTINCT item_id) AS assessments,
                           max(assessment_date)    AS last_assessment_date
                    FROM dim_item WHERE school_id = s.school_id) a ON true
                LEFT JOIN LATERAL (
                    SELECT count(*) AS students
                    FROM dim_student WHERE school_id = s.school_id) st ON true
                LEFT JOIN LATERAL (
                    SELECT count(DISTINCT subject_id) AS subjects
                    FROM cube_school_summary WHERE school_id = s.school_id) css ON true
                LEFT JOIN LATERAL (
                    SELECT count(DISTINCT session) AS sessions_covered
                    FROM dim_subject WHERE school_id = s.school_id) sess ON true
                ORDER BY s.name
                """
            )
        )
        return [dict(r._mapping) for r in rows.all()]

    async def recent_activity(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows = await self.session.execute(
            text(
                """
                SELECT al.id::text AS id, al.created_at, al.action, al.module,
                       al.resource_id, al.details, u.email AS actor_email
                FROM audit_logs al
                LEFT JOIN auth.users u ON u.id = al.user_id
                ORDER BY al.created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        return [dict(r._mapping) for r in rows.all()]

    async def latest_ingestion(self) -> Optional[Dict[str, Any]]:
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT run_id::text AS run_id, school_id::text AS school_id,
                           status, started_at, finished_at,
                           files_processed, rows_inserted, error_count
                    FROM ingestion_runs
                    ORDER BY started_at DESC
                    LIMIT 1
                    """
                )
            )
        ).first()
        return dict(row._mapping) if row else None
