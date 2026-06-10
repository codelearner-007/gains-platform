#!/usr/bin/env python3
"""Idempotent, transactional cleanup of synthetic / demo tenants + demo users.

Removes the demo data that was seeded for multi-tenant demos so the platform
contains only real tenants:

  * schools whose ``schoology_building_id`` matches ``synth-%`` (25) or
    ``phase5-test-%`` (5), plus ALL rows scoped to those ``school_id``s in every
    ``public.*`` table that has a ``school_id`` column;
  * six named demo / test ``auth.users`` and their app rows
    (user_roles / user_schools / user_profiles / lti_user_identity / audit_logs).

KEEPS: Athenian Academy (schoology_building_id='186370968') and ALL its data;
keeps user super.admin@gains.demo.

Safety:
  * Runs inside a single BEGIN/COMMIT transaction.
  * Captures the Athenian KPI anchor BEFORE and AFTER deletes; if any anchor
    moved it ROLLS BACK and exits non-zero (Athenian rows are never touched).
  * Discovers school_id tables dynamically and deletes in FK-safe order
    (NO ACTION / raw / sync tables first, then user_schools, then schools).
  * Idempotent: a second run finds nothing to delete and is a no-op (0 rows).

Usage:
    backend/venv/bin/python supabase/seeds/cleanup_synthetic.py
    backend/venv/bin/python supabase/seeds/cleanup_synthetic.py --dry-run
"""
from __future__ import annotations

import argparse
import sys

import psycopg2
import psycopg2.extras

PG = "postgresql://postgres:postgres@127.0.0.1:56322/postgres"

ATHENIAN_BUILDING_ID = "186370968"

# Tenants to remove (matched on schoology_building_id prefix).
SYNTH_SCHOOL_PREDICATE = (
    "schoology_building_id LIKE 'synth-%' "
    "OR schoology_building_id LIKE 'phase5-test-%'"
)

# Demo / test users to remove (exact emails). super.admin@gains.demo is NOT here.
DEMO_USER_EMAILS = (
    "admin.riverside@gains.demo",
    "student.oakwood@gains.demo",
    "teacher.lincoln@gains.demo",
    "teacher.oakwood@gains.demo",
    "learner-9@school.test",
    "user-sub-1@school.test",
)

# Anchor item for the Athenian QSR grade-average baseline (65.4% / 18 questions).
ANCHOR_ITEM_ID = "8359960427"

# Tables whose school_id FK is NOT ON DELETE CASCADE — must be deleted before the
# schools rows. Everything else cascades from schools, but we delete explicitly
# for determinism + idempotency regardless.
NON_CASCADE_FIRST = (
    "ingestion_runs",
    "raw_question_data",
    "raw_student_submission",
    "raw_submission_summary",
    "raw_user",
    "tenant_config_sync_runs",
    "user_sync_runs",
)


def discover_school_id_tables(cur) -> list[str]:
    """Every public table (except `schools` itself) carrying a school_id column."""
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND column_name = 'school_id'
          AND table_name <> 'schools'
        ORDER BY table_name
        """
    )
    return [r[0] for r in cur.fetchall()]


def capture_athenian_anchor(cur) -> dict:
    """Snapshot the protected Athenian KPI numbers."""
    cur.execute(
        "SELECT school_id FROM schools WHERE schoology_building_id = %s",
        (ATHENIAN_BUILDING_ID,),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Athenian school not found — refusing to run.")
    ath = row[0]

    cur.execute(
        "SELECT count(*) FROM fact_student_submission WHERE school_id = %s", (ath,)
    )
    fss = cur.fetchone()[0]

    cur.execute(
        "SELECT count(*) FROM cube_question_summary WHERE school_id = %s", (ath,)
    )
    cqs = cur.fetchone()[0]

    cur.execute(
        """
        WITH q AS (
            SELECT DISTINCT question_no, grade_average
            FROM cube_question_summary
            WHERE school_id = %s AND item_id = %s
        )
        SELECT count(*), round(coalesce(avg(grade_average), 0) * 100, 1)
        FROM q
        """,
        (ath, ANCHOR_ITEM_ID),
    )
    anchor_q, anchor_pct = cur.fetchone()

    return {
        "school_id": str(ath),
        "fss": fss,
        "cqs": cqs,
        "anchor_questions": anchor_q,
        "anchor_pct": str(anchor_pct),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all deletes inside the transaction, report counts, then ROLLBACK.",
    )
    args = parser.parse_args()

    conn = psycopg2.connect(PG)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        before = capture_athenian_anchor(cur)
        print("Athenian baseline BEFORE:")
        print(f"  fact_student_submission = {before['fss']}")
        print(f"  cube_question_summary   = {before['cqs']}")
        print(
            f"  anchor {ANCHOR_ITEM_ID}    = {before['anchor_pct']}% "
            f"/ {before['anchor_questions']}q"
        )

        # Resolve the target synthetic school_ids up front.
        cur.execute(
            f"SELECT school_id::text FROM schools WHERE {SYNTH_SCHOOL_PREDICATE}"
        )
        synth_ids = [r[0] for r in cur.fetchall()]
        print(f"\nSynthetic/phase5 schools matched: {len(synth_ids)}")

        deleted: dict[str, int] = {}

        if synth_ids:
            tables = discover_school_id_tables(cur)
            # FK-safe order: non-cascade + raw/sync first, then everything else,
            # then user_schools, then schools (handled separately below).
            others = [
                t
                for t in tables
                if t not in NON_CASCADE_FIRST and t != "user_schools"
            ]
            ordered = list(NON_CASCADE_FIRST) + others + ["user_schools"]
            # Keep only tables that actually exist / have school_id.
            ordered = [t for t in ordered if t in tables]

            for table in ordered:
                cur.execute(
                    f"DELETE FROM {table} WHERE school_id::text = ANY(%s)",
                    (synth_ids,),
                )
                if cur.rowcount:
                    deleted[table] = cur.rowcount

            # Finally the schools rows themselves.
            cur.execute(
                f"DELETE FROM schools WHERE {SYNTH_SCHOOL_PREDICATE}"
            )
            if cur.rowcount:
                deleted["schools"] = cur.rowcount

        # ---- Demo / test users -------------------------------------------------
        cur.execute(
            "SELECT id::text, email FROM auth.users WHERE email = ANY(%s)",
            (list(DEMO_USER_EMAILS),),
        )
        demo_users = cur.fetchall()
        demo_user_ids = [u[0] for u in demo_users]
        print(f"Demo/test users matched: {len(demo_user_ids)}")

        if demo_user_ids:
            # Explicit child deletes (audit_logs is NO ACTION; the rest cascade
            # from auth.users but we delete for determinism + idempotency).
            for table in (
                "audit_logs",
                "lti_user_identity",
                "user_schools",
                "user_roles",
                "user_profiles",
            ):
                cur.execute(
                    f"DELETE FROM {table} WHERE user_id::text = ANY(%s)",
                    (demo_user_ids,),
                )
                if cur.rowcount:
                    deleted[f"{table} (users)"] = cur.rowcount

            # auth.users cascades remaining auth.* rows (identities, sessions, ...).
            cur.execute(
                "DELETE FROM auth.users WHERE id::text = ANY(%s)", (demo_user_ids,)
            )
            if cur.rowcount:
                deleted["auth.users"] = cur.rowcount

        print("\nRows deleted:")
        if deleted:
            for table, n in sorted(deleted.items()):
                print(f"  {table:<32} {n}")
        else:
            print("  (none — already clean)")

        # ---- Guard: Athenian must be byte-for-byte unchanged -------------------
        after = capture_athenian_anchor(cur)
        if (
            after["fss"] != before["fss"]
            or after["cqs"] != before["cqs"]
            or after["anchor_questions"] != before["anchor_questions"]
            or after["anchor_pct"] != before["anchor_pct"]
        ):
            conn.rollback()
            print("\nABORTED: Athenian KPI anchor changed — rolled back.", file=sys.stderr)
            print(f"  before={before}\n  after ={after}", file=sys.stderr)
            return 2

        # ---- Verification (inside txn, before commit) --------------------------
        cur.execute(
            f"SELECT count(*) FROM schools WHERE {SYNTH_SCHOOL_PREDICATE}"
        )
        remaining_synth = cur.fetchone()[0]

        cur.execute(
            "SELECT count(*) FROM auth.users WHERE email = ANY(%s)",
            (list(DEMO_USER_EMAILS),),
        )
        remaining_demo = cur.fetchone()[0]

        cur.execute(
            "SELECT count(*) FROM auth.users WHERE email = 'super.admin@gains.demo'"
        )
        superadmin = cur.fetchone()[0]

        print("\nVerification (pre-commit):")
        print(f"  synth/phase5 schools remaining = {remaining_synth}")
        print(f"  demo/test users remaining      = {remaining_demo}")
        print(f"  super.admin@gains.demo present  = {superadmin}")

        if remaining_synth != 0 or remaining_demo != 0 or superadmin != 1:
            conn.rollback()
            print("\nABORTED: post-delete invariants failed — rolled back.", file=sys.stderr)
            return 3

        if args.dry_run:
            conn.rollback()
            print("\nDRY-RUN: rolled back (no changes committed).")
            return 0

        conn.commit()
        print("\nCOMMITTED.")
        return 0

    except Exception as exc:  # noqa: BLE001 — surface + rollback any failure
        conn.rollback()
        print(f"\nERROR: {exc} — rolled back.", file=sys.stderr)
        return 1
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
