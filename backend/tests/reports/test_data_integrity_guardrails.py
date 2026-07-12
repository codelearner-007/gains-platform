"""Data-integrity guardrails (2026-07 audit, workstream G).

Structural invariants that must hold after the remediation, so the corruption
classes cannot silently return on a future rebuild/ingest. These run as the
service-role superuser (no RLS scoping needed) and are read-only.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# The 9 genuine parent/cluster codes that legitimately map to >1 child benchmark
# (left untouched by dim_standard_cleanup.sql; not a defect).
MAX_PARENT_COLLISIONS = 9


async def _scalar(db: AsyncSession, sql: str) -> int:
    return int((await db.execute(text(sql))).scalar() or 0)


async def test_g2_subject_id_hash_consistent(db: AsyncSession):
    """Every fact row's subject_id equals uuid_6(labels): the corrected state is
    fully pipeline-reproducible (durability proof; was 9,153 before Phase 1.9)."""
    n = await _scalar(
        db,
        """
        SELECT count(*) FROM fact_student_submission f
        WHERE f.subject_id IS DISTINCT FROM
          uuid_6(f.school_id::text, f.subject, f.assessment_type,
                 f.grade, f.session, f.item_name)
        """,
    )
    assert n == 0, f"{n} fact rows have a non-reproducible subject_id"


# Known residual orphans (2026-07): F-C1 dim_reconcile points dim_item at the
# dominant subject_id, so an item that legitimately spans two subject_ids leaves
# the minority one orphaned. The 4 remaining are 1 legitimate cross-session twin
# (Crestwell "Chapter 1 Test", same test in 2024-25 AND 2025-26; DG-3) + 3 tiny
# item_name-variant fragments (Phase-4 case-by-case). The guardrail catches any
# NEW regression above this baseline.
MAX_ORPHAN_SUBJECT_IDS = 4


async def test_g2_no_orphan_subject_ids(db: AsyncSession):
    """Every subject_id present in fact has a dim_item row — no assessment is
    invisible in the dashboard grid (F-C1 dim_reconcile). Was 53 pre-fix."""
    n = await _scalar(
        db,
        """
        SELECT count(DISTINCT f.subject_id)
        FROM fact_student_submission f
        LEFT JOIN dim_item di
          ON di.school_id = f.school_id AND di.subject_id = f.subject_id
         AND di.item_id = f.item_id
        WHERE di.item_id IS NULL
        """,
    )
    assert n <= MAX_ORPHAN_SUBJECT_IDS, f"{n} orphan subject_ids (> {MAX_ORPHAN_SUBJECT_IDS} baseline)"


async def test_g2_no_phantom_dim_subject(db: AsyncSession):
    """No dim_subject row with zero fact rows (phantom 0-student report cards)."""
    n = await _scalar(
        db,
        """
        SELECT count(*) FROM dim_subject ds
        WHERE NOT EXISTS (
          SELECT 1 FROM fact_student_submission f
          WHERE f.school_id = ds.school_id AND f.subject_id = ds.subject_id)
        """,
    )
    assert n == 0, f"{n} phantom dim_subject cards"


async def test_g2_standards_no_unexpected_collisions(db: AsyncSession):
    """No schoology_standard maps to >1 identifier except the known parent codes
    (substring-pollution purged by dim_standard_cleanup.sql)."""
    n = await _scalar(
        db,
        """
        SELECT count(*) FROM (
          SELECT schoology_standard FROM dim_standard
          WHERE schoology_standard IS NOT NULL AND btrim(schoology_standard) <> ''
          GROUP BY 1 HAVING count(DISTINCT identifier) > 1) x
        """,
    )
    assert n <= MAX_PARENT_COLLISIONS, f"{n} colliding codes (> {MAX_PARENT_COLLISIONS} parents)"


async def test_g2_fact_identifiers_resolve(db: AsyncSession):
    """Every fact.identifier exists in dim_standard (no broken standards join)."""
    n = await _scalar(
        db,
        """
        SELECT count(*) FROM fact_student_submission f
        WHERE f.identifier IS NOT NULL AND f.identifier <> ''
          AND NOT EXISTS (SELECT 1 FROM dim_standard d WHERE d.identifier = f.identifier)
        """,
    )
    assert n == 0, f"{n} fact rows reference a missing dim_standard identifier"


async def test_g2_no_junk_numeric_standards(db: AsyncSession):
    """No numeric-only junk codes remain in dim_standard (F-E5)."""
    n = await _scalar(
        db, r"SELECT count(*) FROM dim_standard WHERE schoology_standard ~ '^[0-9]+(\.[0-9]+)?$'"
    )
    assert n == 0, f"{n} junk numeric standard codes remain"


async def test_g2_no_multilabel_fact_slots(db: AsyncSession):
    """No (user,item,question,position) fact slot carries >1 grade/subject/session
    (F-C2 tripwire, per advisory): the latest_export prune must keep exactly one
    export vintage per physical response slot. A regression here = cross-label
    duplicate exports leaking through, which would double-count and make slicer
    membership non-deterministic."""
    n = await _scalar(
        db,
        """
        SELECT count(*) FROM (
          SELECT school_id, user_uid, item_id, question_id, position_number
          FROM fact_student_submission
          GROUP BY 1,2,3,4,5
          HAVING count(DISTINCT grade) > 1 OR count(DISTINCT subject) > 1
              OR count(DISTINCT session) > 1
        ) x
        """,
    )
    assert n == 0, f"{n} fact slots carry >1 label (cross-label export dupes leaked through)"


async def test_g2_dqd_one_ukey_per_question(db: AsyncSession):
    """dim_question_data has one ukey vintage per physical question slot
    (school, question, position, sub_question) — the F-C3 latest-export dedup.
    >1 means stale label/answer vintages survived and the incorrect-choice cube
    would fan out (doubled distractor counts). NOTE the grain includes
    sub_question: a multi-part question legitimately has one ukey per part."""
    n = await _scalar(
        db,
        """
        SELECT count(*) FROM (
          SELECT school_id, question_id, position_number, COALESCE(sub_question, '')
          FROM dim_question_data
          GROUP BY 1,2,3,4 HAVING count(DISTINCT ukey) > 1
        ) x
        """,
    )
    assert n == 0, f"{n} question slots have >1 ukey vintage in dqd (stale vintage survived)"


async def test_g5_all_cubes_rls_enabled(db: AsyncSession):
    """Every cube_* table has RLS enabled with a tenant policy (no cross-tenant
    read leak; guards F-B1 recurrence)."""
    rows = (
        await db.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity,
                       (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) n_pol
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname LIKE 'cube_%'
                """
            )
        )
    ).all()
    bad = [r[0] for r in rows if not r[1] or r[2] < 1]
    assert not bad, f"cubes without RLS+policy: {bad}"


def test_g1_retake_read_paths_have_submission_desc():
    """The three cube_repository fact_dedup CTEs must tie-break on submission DESC
    so retake students get the latest attempt (guards F-A1/A2). A regression that
    drops the tie-break would re-introduce non-deterministic mixed-attempt scores.
    """
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "app" / "repositories" / "cube_repository.py"
    text_src = src.read_text(encoding="utf-8")
    # Each fact_dedup CTE ends with an ORDER BY … <keys>; every one must carry a
    # submission-DESC tie-break.
    dedup_blocks = re.findall(r"fact_dedup AS \((.*?)\n\s*\),", text_src, re.DOTALL)
    assert len(dedup_blocks) >= 3, f"expected >=3 fact_dedup CTEs, found {len(dedup_blocks)}"
    missing = [i for i, b in enumerate(dedup_blocks) if "submission DESC" not in b]
    assert not missing, f"fact_dedup CTE(s) {missing} missing 'submission DESC' tie-break"


async def test_g5_no_backup_grants_to_anon(db: AsyncSession):
    """No *_bak / fix* table grants SELECT to anon/authenticated (PII lockdown)."""
    n = await _scalar(
        db,
        """
        SELECT count(*) FROM information_schema.table_privileges
        WHERE grantee IN ('anon', 'authenticated')
          AND (table_name LIKE '%bak%' OR table_name LIKE 'fix%'
               OR table_name LIKE 'mrg_bak%' OR table_name LIKE 'clean_bak%')
        """,
    )
    assert n == 0, f"{n} backup-table grants still exposed to anon/authenticated"
