"""Repository for the dimension lookup tables.

dim_standard / dim_strand are global lookups (no school_id, no RLS); the
remaining dim_* tables are per-tenant and read through the RLS-enabled
session.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class DimRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ────── Global lookups (no RLS) ──────

    async def list_standards(self, limit: int = 10000) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT
                uniques_id, identifier, schoology_standard, standard_new,
                strand, subject, cluster, description
            FROM dim_standard
            ORDER BY identifier
            LIMIT :lim
            """
        )
        result = await self.session.execute(sql, {"lim": limit})
        return [dict(r._mapping) for r in result.all()]

    async def list_strands(self) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT identifier, strand, strand_id
            FROM dim_strand
            ORDER BY strand NULLS LAST, identifier
            """
        )
        result = await self.session.execute(sql)
        return [dict(r._mapping) for r in result.all()]

    # ────── Per-school lookups (RLS) ──────

    async def list_subjects(self) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT subject_id, subject, grade, session, assessment_type
            FROM dim_subject
            ORDER BY grade NULLS LAST, subject NULLS LAST
            """
        )
        result = await self.session.execute(sql)
        return [dict(r._mapping) for r in result.all()]

    async def list_grades(self) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT grade_id, grade
            FROM dim_grade
            ORDER BY grade NULLS LAST
            """
        )
        result = await self.session.execute(sql)
        return [dict(r._mapping) for r in result.all()]

    async def list_sections(self) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT section_nid, section_code, section_name, section_instructors
            FROM dim_section
            ORDER BY section_name NULLS LAST
            """
        )
        result = await self.session.execute(sql)
        return [dict(r._mapping) for r in result.all()]

    async def list_sessions(self) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT session_id, session
            FROM dim_session
            ORDER BY session NULLS LAST
            """
        )
        result = await self.session.execute(sql)
        return [dict(r._mapping) for r in result.all()]

    # ────── dim_item (assessment list) ──────

    async def list_items(
        self,
        session_filter: Optional[str] = None,
        category: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[str] = None,
        section: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List dim_items joined to dim_subject for filtering.

        Filters are matched case-insensitively against the joined fields.
        """
        sql = text(
            """
            SELECT
                di.item_id,
                di.item_name,
                di.item_type,
                di.subject_id,
                ds.subject,
                ds.grade,
                ds.session,
                ds.assessment_type,
                di.section_name,
                di.section_instructors,
                di.assessment_date
            FROM dim_item di
            LEFT JOIN dim_subject ds
              ON ds.school_id = di.school_id AND ds.subject_id = di.subject_id
            WHERE (CAST(:session_filter AS TEXT) IS NULL OR ds.session = CAST(:session_filter AS TEXT))
              AND (CAST(:category AS TEXT) IS NULL OR ds.assessment_type = CAST(:category AS TEXT))
              AND (CAST(:subject AS TEXT)  IS NULL OR ds.subject         = CAST(:subject AS TEXT))
              AND (CAST(:grade AS TEXT)    IS NULL OR ds.grade           = CAST(:grade AS TEXT))
              AND (CAST(:section AS TEXT)  IS NULL OR di.section_name    = CAST(:section AS TEXT))
            ORDER BY di.assessment_date DESC NULLS LAST, di.item_name NULLS LAST
            """
        )
        result = await self.session.execute(
            sql,
            {
                "session_filter": session_filter,
                "category": category,
                "subject": subject,
                "grade": grade,
                "section": section,
            },
        )
        return [dict(r._mapping) for r in result.all()]

    async def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        sql = text(
            """
            SELECT
                di.item_id,
                di.item_name,
                di.item_type,
                di.subject_id,
                ds.subject,
                ds.grade,
                ds.session,
                ds.assessment_type,
                di.section_name,
                di.section_instructors,
                di.assessment_date,
                di.school_id::text AS school_id
            FROM dim_item di
            LEFT JOIN dim_subject ds
              ON ds.school_id = di.school_id AND ds.subject_id = di.subject_id
            WHERE di.item_id = :item_id
            LIMIT 1
            """
        )
        result = await self.session.execute(sql, {"item_id": item_id})
        row = result.first()
        return dict(row._mapping) if row else None
