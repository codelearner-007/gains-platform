"""Scoped section options + comma-joined section filter — READ-ONLY.

Same discipline as ``test_forward_view.py``: open a session, scope it to a
school via the RLS GUC exactly as a request does (``SET LOCAL ROLE
authenticated`` + ``app.current_school_id``), call the repository / service,
assert, and roll back (the dev DB is never mutated).

Covers two landed changes:

* ``dim/sections`` is now sourced from ``cube_user_summary`` and grouped by
  ``(section_name, section_instructors)`` — a classroom split across several
  Schoology shells collapses to ONE option whose value is the comma-joined
  ``section_nids`` list (VERIFIED anchors: Athenian · 2024-25 · Math G3 →
  Leiva/Rossi/Vaughn, one nid each; ELA G1 → Almendinger/Reeder/Sedlak, two
  nids each).
* the report section filter accepts that CSV via
  ``section_nid = ANY(string_to_array(:section, ','))`` — a merged option
  equals the UNION of its constituent shells, and a single nid still filters.

Run (safe — never truncates):
    cd backend && ./venv/bin/python -m pytest tests/reports/test_sections.py -q

NEVER run pytest outside ``tests/reports`` — the pipeline/ingestion conftests
TRUNCATE the dev DB.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.cube_repository import CubeRepository
from app.schemas.reports import ForwardViewFilters
from app.services.dim_service import DimService
from app.services.reports import ReportService

# ── School ids (BASELINE.md) ────────────────────────────────────────────────
ATHENIAN = "019eb11c-410a-7ffb-86e6-a0294c669670"

SESSION = "2024-25"
THRESHOLD = 0.7


async def scope(session: AsyncSession, school_id: str) -> None:
    """Scope EXACTLY as ``get_db_with_rls`` does: drop to ``authenticated`` (so
    RLS is enforced) and set the tenant GUC (SET LOCAL — rolled back with the
    surrounding transaction)."""
    await session.execute(text("SET LOCAL ROLE authenticated"))
    await session.execute(
        text("SELECT set_config('app.current_school_id', :s, true)"),
        {"s": school_id},
    )


# ════════════════════════════════════════════════════════════════════════════
# Grouped scoped section options (dim/sections over cube_user_summary).
# ════════════════════════════════════════════════════════════════════════════
class TestScopedSectionOptions:
    async def test_math_g3_three_single_nid_sections(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        rows = await DimService(db).list_sections(
            session=SESSION, subject="Math", grade="Grade 3"
        )
        # One option per classroom, ordered by section_name.
        assert len(rows) == 3
        assert [r.section_name for r in rows] == ["Leiva", "Rossi", "Vaughn"]
        assert {r.section_instructors for r in rows} == {
            "Ana Leiva",
            "Pattie Rossi",
            "Mary Vaughn",
        }
        # Each Math G3 classroom is a single Schoology shell.
        assert all(len(r.section_nids) == 1 for r in rows)
        # VERIFIED anchor (PLAN §7): Vaughn → 7325370917.
        vaughn = next(r for r in rows if r.section_name == "Vaughn")
        assert vaughn.section_nids == ["7325370917"]

    async def test_ela_g1_three_two_nid_sections(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        rows = await DimService(db).list_sections(
            session=SESSION, subject="ELA", grade="Grade 1"
        )
        # Three classrooms, each split into exactly TWO Schoology shells that
        # collapse into one merged option (the whole point of the grouping).
        assert len(rows) == 3
        assert [r.section_name for r in rows] == [
            "Almendinger",
            "Reeder",
            "Sedlak",
        ]
        assert all(len(r.section_nids) == 2 for r in rows)
        # array_agg(DISTINCT …) yields a sorted, deterministic nid list.
        sedlak = next(r for r in rows if r.section_name == "Sedlak")
        assert sedlak.section_nids == ["7325344053", "7325443634"]


# ════════════════════════════════════════════════════════════════════════════
# Comma-joined section filter (D4) on the exact Forward-View SQL path.
# ════════════════════════════════════════════════════════════════════════════
class TestSectionCsvFilter:
    # Two POPULATED Math G3 sections (Leiva, Vaughn — both carry rollup rows).
    # A merged same-name option's value is exactly this kind of comma-joined nid
    # set, so this exercises `section_nid = ANY(string_to_array(:section))` on
    # two NON-EMPTY shells (not a degenerate empty duplicate that would make the
    # union/additivity checks pass vacuously).
    LEIVA = "7325368955"
    VAUGHN = "7325370917"

    @staticmethod
    def _keys(rows) -> set:
        return {(r["period"], r["unit"], r["schoology_standard"]) for r in rows}

    @staticmethod
    def _score(rows) -> float:
        return sum(r["total_score"] for r in rows)

    @staticmethod
    def _poss(rows) -> float:
        return sum(r["total_possible_point"] for r in rows)

    async def _math_g3(self, db: AsyncSession, section):
        return await CubeRepository(db).get_forward_view_rollup(
            session_filter=SESSION,
            subject="Math",
            grade="Grade 3",
            category=None,
            section=section,
        )

    async def test_two_nid_csv_equals_union_of_shells(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        a, b = self.LEIVA, self.VAUGHN
        rows_a = await self._math_g3(db, a)
        rows_b = await self._math_g3(db, b)
        rows_csv = await self._math_g3(db, f"{a},{b}")

        # Guard against a degenerate anchor: BOTH shells must carry rows, or the
        # union / additivity assertions below would pass vacuously.
        assert rows_a and rows_b, "both section shells must carry rollup rows"

        # The 2-nid CSV's (period, unit, standard) cell set == the UNION of the
        # two shells' cell sets; each shell is a subset of the merge.
        assert self._keys(rows_csv) == self._keys(rows_a) | self._keys(rows_b)
        assert self._keys(rows_a) <= self._keys(rows_csv)
        assert self._keys(rows_b) <= self._keys(rows_csv)

        # Pooled points are additive across the shells: each cube_user_summary
        # row carries exactly one section_nid, so the CSV membership filter
        # (section_nid = ANY(...)) double-counts nothing.
        assert abs(
            self._score(rows_csv) - (self._score(rows_a) + self._score(rows_b))
        ) <= 1e-6
        assert abs(
            self._poss(rows_csv) - (self._poss(rows_a) + self._poss(rows_b))
        ) <= 1e-6

    async def test_single_nid_section_still_filters(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        repo = CubeRepository(db)
        # Vaughn is a single-shell Math G3 section (one nid, PLAN §7 anchor).
        vaughn = await repo.get_forward_view_rollup(
            session_filter=SESSION,
            subject="Math",
            grade="Grade 3",
            category=None,
            section="7325370917",
        )
        assert vaughn, "a single-nid section must return its scoped rows"
        unscoped = await repo.get_forward_view_rollup(
            session_filter=SESSION,
            subject="Math",
            grade="Grade 3",
            category=None,
            section=None,
        )
        # One section is a strict subset of the whole Math G3 scope.
        assert 0 < self._poss(vaughn) < self._poss(unscoped)

    async def test_csv_and_single_nid_flow_through_service(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        a, b = self.LEIVA, self.VAUGHN
        svc = ReportService(db)
        csv_payload = await svc.build_forward_view(
            ForwardViewFilters(
                session=SESSION,
                subject="Math",
                grade="Grade 3",
                section=f"{a},{b}",
                threshold=THRESHOLD,
            )
        )
        single_payload = await svc.build_forward_view(
            ForwardViewFilters(
                session=SESSION,
                subject="Math",
                grade="Grade 3",
                section=b,
                threshold=THRESHOLD,
            )
        )
        # Both the CSV and a single nid flow end-to-end through the service and
        # echo the section they were filtered by.
        assert csv_payload.filters_applied.section == f"{a},{b}"
        assert single_payload.filters_applied.section == b
        # The subset must be non-empty (both shells populated), and the 2-section
        # CSV covers at least as much as either single section (union ⊇ subset).
        assert single_payload.kpis.standards_assessed > 0
        assert (
            csv_payload.kpis.standards_assessed
            >= single_payload.kpis.standards_assessed
        )
