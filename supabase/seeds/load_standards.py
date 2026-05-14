"""
Load supabase/seeds/dim_standard.csv (7,958 rows) and dim_strand.csv (7,071 rows)
into the local Supabase Postgres.

Idempotent: skips if row counts already match the CSVs. Override with --force.

Usage:
    python supabase/seeds/load_standards.py
    python supabase/seeds/load_standards.py --force

Connection: reads $DATABASE_URL, default postgresql://postgres:postgres@127.0.0.1:56322/postgres
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

DEFAULT_DSN = "postgresql://postgres:postgres@127.0.0.1:56322/postgres"

SEEDS_DIR = Path(__file__).parent
DIM_STANDARD_CSV = SEEDS_DIR / "dim_standard.csv"
DIM_STRAND_CSV = SEEDS_DIR / "dim_strand.csv"


def load_dim_standard(conn, force: bool) -> int:
    df = pd.read_csv(DIM_STANDARD_CSV)
    expected = len(df)

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dim_standard")
        current = cur.fetchone()[0]

    if current == expected and not force:
        print(f"[dim_standard] already loaded ({current} rows). Skipping. Use --force to reload.")
        return current

    print(f"[dim_standard] loading {expected} rows (current: {current})...")

    # Map CSV header -> DB column
    column_map = {
        "Cognitive_Complexity_Rating": "cognitive_complexity_rating",
        "Direct_Link": "direct_link",
        "Grader": "grader",
        "Identifier": "identifier",
        "Language": "language",
        "Schoology_Standard": "schoology_standard",
        "Standard_New": "standard_new",
        "Strand": "strand",
        "Subject": "subject",
        "cPalms_Standard": "cpalms_standard",
        "cluster": "cluster",
        "description": "description",
        "lastChangeDateTime": "last_change_date_time",
        "rundate": "rundate",
        "Custom.CleanedDescription": "custom_cleaned_description",
        "uniquesID": "uniques_id",
    }
    df = df.rename(columns=column_map)
    db_cols = [
        "uniques_id", "identifier", "schoology_standard", "standard_new",
        "strand", "subject", "cluster", "description",
        "custom_cleaned_description", "direct_link", "cpalms_standard",
        "cognitive_complexity_rating", "language", "grader",
        "last_change_date_time", "rundate",
    ]
    df = df[db_cols]

    # Normalise lastChangeDateTime: CSV uses 'MM/dd/yyyy h:mm:ss AM/PM' with
    # occasional U+202F (narrow no-break space) instead of regular space.
    # Parse to pandas Timestamp; pandas serialises that to ISO when iterated,
    # which Postgres accepts.
    if "last_change_date_time" in df.columns:
        df["last_change_date_time"] = (
            df["last_change_date_time"]
            .astype("string")
            .str.replace(" ", " ", regex=False)
            .str.replace("\xa0", " ", regex=False)
        )
        df["last_change_date_time"] = pd.to_datetime(
            df["last_change_date_time"], errors="coerce"
        )

    # rundate is YYYY-MM-DD already; coerce to date for safety.
    if "rundate" in df.columns:
        df["rundate"] = pd.to_datetime(df["rundate"], errors="coerce").dt.date

    # Pandas NaN/NaT -> Python None for clean SQL NULLs
    df = df.astype(object).where(pd.notnull(df), None)

    rows = [tuple(r) for r in df.itertuples(index=False, name=None)]

    with conn.cursor() as cur:
        cur.execute("TRUNCATE dim_standard")
        execute_values(
            cur,
            f"INSERT INTO dim_standard ({', '.join(db_cols)}) VALUES %s",
            rows,
            page_size=2000,
        )
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dim_standard")
        loaded = cur.fetchone()[0]

    print(f"[dim_standard] loaded {loaded} rows.")
    return loaded


def load_dim_strand(conn, force: bool) -> int:
    df = pd.read_csv(DIM_STRAND_CSV)
    expected = len(df)

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dim_strand")
        current = cur.fetchone()[0]

    if current == expected and not force:
        print(f"[dim_strand] already loaded ({current} rows). Skipping. Use --force to reload.")
        return current

    print(f"[dim_strand] loading {expected} rows (current: {current})...")

    column_map = {
        "Identifier": "identifier",
        "Strand": "strand",
        "strand_ID": "strand_id",
        "ID": "id",
    }
    df = df.rename(columns=column_map)
    # dim_strand_pk is auto-generated; we insert (id, identifier, strand, strand_id)
    db_cols = ["id", "identifier", "strand", "strand_id"]
    df = df[db_cols]
    df = df.astype(object).where(pd.notnull(df), None)

    rows = [tuple(r) for r in df.itertuples(index=False, name=None)]

    with conn.cursor() as cur:
        cur.execute("TRUNCATE dim_strand")
        execute_values(
            cur,
            f"INSERT INTO dim_strand ({', '.join(db_cols)}) VALUES %s",
            rows,
            page_size=2000,
        )
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dim_strand")
        loaded = cur.fetchone()[0]

    print(f"[dim_strand] loaded {loaded} rows.")
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser(description="Load Schoology standards seeds.")
    parser.add_argument("--force", action="store_true", help="Reload even if row counts match.")
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", DEFAULT_DSN))
    args = parser.parse_args()

    if not DIM_STANDARD_CSV.exists():
        print(f"ERROR: {DIM_STANDARD_CSV} not found.", file=sys.stderr)
        return 1
    if not DIM_STRAND_CSV.exists():
        print(f"ERROR: {DIM_STRAND_CSV} not found.", file=sys.stderr)
        return 1

    print(f"Connecting to {args.dsn}")
    with psycopg2.connect(args.dsn) as conn:
        load_dim_standard(conn, args.force)
        load_dim_strand(conn, args.force)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
