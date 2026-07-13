"""Repository for the dimension lookup tables.

dim_standard / dim_strand are global lookups (no school_id, no RLS); the
remaining dim_* tables are per-tenant and read through the RLS-enabled
session.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repository import row_to_dict


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
            -- F-F4: order grades K -> 1..8 -> Regular 9-12 -> Higher-Ed, not
            -- alphabetically (which put 'Grade K' after 'Grade 8').
            ORDER BY
              CASE
                WHEN grade = 'Grade K' THEN 0
                WHEN grade ~ '^Grade [0-9]+$' THEN split_part(grade, ' ', 2)::int
                WHEN grade = 'Regular 9–12' THEN 90
                WHEN grade = 'Higher-Ed' THEN 100
                ELSE 999
              END NULLS LAST,
              subject NULLS LAST
            """
        )
        result = await self.session.execute(sql)
        return [dict(r._mapping) for r in result.all()]

    async def list_grades(self) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT grade_id, grade
            FROM dim_grade
            -- F-F4: canonical grade order (see list_subjects).
            ORDER BY
              CASE
                WHEN grade = 'Grade K' THEN 0
                WHEN grade ~ '^Grade [0-9]+$' THEN split_part(grade, ' ', 2)::int
                WHEN grade = 'Regular 9–12' THEN 90
                WHEN grade = 'Higher-Ed' THEN 100
                ELSE 999
              END NULLS LAST
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

    async def list_assessment_types(self) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT DISTINCT assessment_type
            FROM dim_subject
            WHERE assessment_type IS NOT NULL AND assessment_type <> ''
            ORDER BY assessment_type
            """
        )
        result = await self.session.execute(sql)
        return [dict(r._mapping) for r in result.all()]

    async def list_instructors(self) -> List[Dict[str, Any]]:
        """DISTINCT classroom instructors, parsed from the comma-joined
        ``section_instructors`` strings on dim_item + dim_section. Comma is the
        canonical delimiter (full ``First Last`` names, no intra-name commas) —
        the same split the frontend filter helper applies.
        """
        sql = text(
            """
            SELECT DISTINCT btrim(part) AS instructor
            FROM (
                SELECT unnest(string_to_array(section_instructors, ',')) AS part
                FROM dim_item
                WHERE section_instructors IS NOT NULL AND section_instructors <> ''
                UNION ALL
                SELECT unnest(string_to_array(section_instructors, ',')) AS part
                FROM dim_section
                WHERE section_instructors IS NOT NULL AND section_instructors <> ''
            ) parts
            WHERE btrim(part) <> ''
              -- F-F3: platform/admin accounts are enrolled as section admins in
              -- Schoology and leak into the teacher filter. Exclude the clear
              -- platform account (the observer 'Sitara' identity is gated on
              -- customer confirmation, DG-4, and is left in for now).
              AND btrim(part) NOT IN ('GAINS Admin')
            ORDER BY instructor
            """
        )
        result = await self.session.execute(sql)
        return [dict(r._mapping) for r in result.all()]

    # ────── dim_item (assessment lookup) ──────

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
        return row_to_dict(row) if row else None
