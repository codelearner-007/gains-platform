"""Repository for the schools (tenant) table.

This repo bypasses RLS and is intended to be used only from admin endpoints
that gate on the ``schools:*`` permissions. Reads / writes go through the
service-role connection (the FastAPI worker connects as ``postgres`` which
bypasses RLS by default; we deliberately do NOT switch role here).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SchoolRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT
                school_id::text AS school_id,
                schoology_building_id, schoology_school_id, edvance_tenant_id,
                name, short_name, logo_url, category_regex, due_date_window_days,
                course_page_limit, download_index, item_filter_expression,
                category_folder_override, current_session, timezone, is_active,
                created_at, updated_at
            FROM public.schools
            ORDER BY name
            """
        )
        result = await self.session.execute(sql)
        return [dict(r._mapping) for r in result.all()]

    async def list_accessible(
        self, *, all_active: bool, school_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Lightweight list for the school switcher.

        ``all_active=True`` (super-admin) returns every active school; otherwise
        only the schools in ``school_ids`` (the member's memberships).
        """
        if all_active:
            sql = text(
                """
                SELECT school_id::text AS school_id, name, short_name, is_active
                FROM public.schools
                WHERE is_active = TRUE
                ORDER BY name
                """
            )
            result = await self.session.execute(sql)
            return [dict(r._mapping) for r in result.all()]

        if not school_ids:
            return []
        sql = text(
            """
            SELECT school_id::text AS school_id, name, short_name, is_active
            FROM public.schools
            WHERE school_id = ANY(CAST(:ids AS uuid[]))
            ORDER BY name
            """
        )
        result = await self.session.execute(sql, {"ids": school_ids})
        return [dict(r._mapping) for r in result.all()]

    async def get(self, school_id: str) -> Optional[Dict[str, Any]]:
        sql = text(
            """
            SELECT
                school_id::text AS school_id,
                schoology_building_id, schoology_school_id, edvance_tenant_id,
                name, short_name, logo_url, category_regex, due_date_window_days,
                course_page_limit, download_index, item_filter_expression,
                category_folder_override, current_session, timezone, is_active,
                created_at, updated_at
            FROM public.schools
            WHERE school_id = :sid
            LIMIT 1
            """
        )
        result = await self.session.execute(sql, {"sid": school_id})
        row = result.first()
        return dict(row._mapping) if row else None

    async def get_by_building_id(self, building_id: str) -> Optional[Dict[str, Any]]:
        sql = text(
            """
            SELECT school_id::text AS school_id, schoology_building_id, name
            FROM public.schools
            WHERE schoology_building_id = :bid
            LIMIT 1
            """
        )
        result = await self.session.execute(sql, {"bid": building_id})
        row = result.first()
        return dict(row._mapping) if row else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Build the column list dynamically from supplied keys to honour table
        # defaults for fields the caller omitted.
        columns = list(data.keys())
        placeholders = ", ".join(f":{c}" for c in columns)
        col_list = ", ".join(columns)

        sql = text(
            f"""
            INSERT INTO public.schools ({col_list})
            VALUES ({placeholders})
            RETURNING
                school_id::text AS school_id,
                schoology_building_id, schoology_school_id, edvance_tenant_id,
                name, short_name, logo_url, category_regex, due_date_window_days,
                course_page_limit, download_index, item_filter_expression,
                category_folder_override, current_session, timezone, is_active,
                created_at, updated_at
            """
        )
        result = await self.session.execute(sql, data)
        row = result.first()
        return dict(row._mapping)

    async def update(
        self, school_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        if not data:
            return await self.get(school_id)
        data = dict(data)
        data["sid"] = school_id
        data["updated_at"] = datetime.now(timezone.utc)
        set_clause = ", ".join(f"{k} = :{k}" for k in data.keys() if k != "sid")
        sql = text(
            f"""
            UPDATE public.schools
               SET {set_clause}
             WHERE school_id = :sid
            RETURNING
                school_id::text AS school_id,
                schoology_building_id, schoology_school_id, edvance_tenant_id,
                name, short_name, logo_url, category_regex, due_date_window_days,
                course_page_limit, download_index, item_filter_expression,
                category_folder_override, current_session, timezone, is_active,
                created_at, updated_at
            """
        )
        result = await self.session.execute(sql, data)
        row = result.first()
        return dict(row._mapping) if row else None
