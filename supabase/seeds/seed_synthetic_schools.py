#!/usr/bin/env python3
"""Seed N synthetic tenant schools by cloning/fanning-out real cube data.

The backup has real assessment data for only ~4 schools (Athenian dominant,
5,303 assessments across all subjects/grades). To demonstrate multi-tenancy at
scale we synthesize ~25 schools, each given a grade-band *profile* (elementary /
middle / high), sample a varied subset of real assessments matching that band,
slice the matching rows from all 8 cubes, and **re-key** them onto a fresh
synthetic school:

    school_id      <- synthetic UUID (uuid_generate_v7 in the schools row)
    school_id_csv  <- synthetic numeric building id
    id (PK)        <- sha256(school_uuid + ':' + original_id)   (collision-free)

Derived dims (dim_item / dim_section / dim_subject / dim_question_data) are
built from the sliced question/user rows so the report endpoints render.
dim_standard / dim_strand are global (already seeded) and untouched.

This ADDS tenants alongside the real Athenian data (which backs KPI baselines
and parity tests) — it never mutates Athenian rows.

Usage:
    .delta-venv/bin/python supabase/seeds/seed_synthetic_schools.py [--schools N] [--reset]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import random
import re
import sys
from pathlib import Path

import pandas as pd
import psycopg2
import pyarrow.dataset as ds

PG = "postgresql://postgres:postgres@127.0.0.1:56322/postgres"

# ── DEMO-ONLY SEED — DISABLED BY DEFAULT ──────────────────────────────────────
# This script fabricates synthetic multi-tenant schools by re-keying Athenian
# cube data. The platform is now invite-only and these synthetic tenants have
# been removed (see cleanup_synthetic.py). Running this again would repopulate
# them, so it refuses to run unless you explicitly opt in:
#   GAINS_SEED_DEMO=i-understand   (or pass --i-understand)
SEED_OPT_IN_ENV = "GAINS_SEED_DEMO"
SEED_OPT_IN_VALUE = "i-understand"


def _require_demo_seed_optin() -> None:
    opted_in = (
        os.environ.get(SEED_OPT_IN_ENV) == SEED_OPT_IN_VALUE
        or "--i-understand" in sys.argv
    )
    if not opted_in:
        print(
            "REFUSING TO RUN: synthetic-school seeding is disabled (invite-only platform).\n"
            "These tenants were intentionally removed by cleanup_synthetic.py.\n"
            f"To override, set {SEED_OPT_IN_ENV}={SEED_OPT_IN_VALUE} or pass --i-understand.",
            file=sys.stderr,
        )
        raise SystemExit(1)
CUBES = Path("/Users/mac/Desktop/PS_P/legacy-backup-20260529/synapse/stage3_cubes")
DONOR_SCHOOL = "186370968"  # Athenian — largest, all subjects/grades

# Synthetic-tenant marker so --reset only ever removes seeded rows, never real.
SYNTH_PREFIX = "synth-"

# ---- column-name normalisation (backup PascalCase -> target snake_case) ----
SPECIAL = {
    "Total_Possible_Point_By_OverallYear": "total_possible_point_by_overall_year",
    "Total_Score_By_OverallYear": "total_score_by_overall_year",
    "Sub-Question": "sub_question",
    "Percentage_InCorrect_Answers": "percentage_incorrect_answers",
    "Question_no_url": "question_no_url",
    "Total_Student": "total_student",
    "Ukey": "ukey", "uKey": "ukey", "UKey": "ukey",
    "ID": "id", "Subject_ID": "subject_id", "Strand_ID": "strand_id",
    "Section_NID": "section_nid", "User_UID": "user_uid",
}


def norm(col: str) -> str:
    if col in SPECIAL:
        return SPECIAL[col]
    return col.lower()


# Target columns per cube (must exist in the DB DDL). Columns absent from the
# backup are filled NULL; backup columns absent here are dropped.
CUBE_TARGETS = {
    "cube_user_summary": {
        "id", "school_id", "school_id_csv", "section_nid", "section_instructors",
        "session", "grade", "subject", "assessment_type", "user_uid", "user_name",
        "item_id", "item_name", "question_id", "question_no", "standards",
        "total_possible_point", "total_score", "total_possible_point_by_question",
        "total_score_by_question", "total_possible_point_by_overall",
        "total_score_by_overall", "total_possible_point_by_overall_year",
        "total_score_by_overall_year", "total_possible_point_by_item",
        "total_score_by_item", "total_possible_point_by_section",
        "total_score_by_section", "total_possible_point_by_standard",
        "total_score_by_standard", "student_name_hash", "teacher_name_hash",
    },
    "cube_question_summary": {
        "id", "school_id", "school_id_csv", "question_id", "item_id", "item_name",
        "subject_id", "position_number", "question", "question_no", "question_no_url",
        "question_type", "associated_question_id", "total_points",
        "total_possible_point", "total_score", "grade_average",
        "percentage_incorrect_answers", "least_points_earned", "most_points_earned",
        "average_points_earned", "correct_answer", "correctly_answered",
        "sub_question", "session", "assessment_type", "subject", "grade", "section",
        "identifier", "standard", "standards", "qkey", "ukey", "assessment_date",
        "section_name", "section_instructors", "item_type",
        "incorrect_choice_details", "incorrect_details_name",
        "incorrect_choice_details_hash", "incorrect_details_name_hash",
        "teacher_name_hash",
    },
    "cube_school_summary": {
        "id", "school_id", "school_id_csv", "subject_id", "item_id",
        "total_questions", "total_standards", "total_students",
        "total_possible_point", "total_score", "grade_average",
        "percentage_incorrect_answers",
    },
    "cube_grade_summary": {
        "id", "school_id", "school_id_csv", "subject_id", "item_id",
        "grade_average", "percentage_incorrect_answers", "grade_min", "grade_max",
    },
    "cube_standard_summary": {
        "id", "school_id", "item_id", "strand_id", "identifier", "total_questions",
        "total_standards", "total_possible_point", "total_score", "grade_average",
        "percentage_incorrect_answers",
    },
    "cube_overallperformance_summary": {
        "id", "school_id", "identifier", "item_id", "item_name", "question_id",
        "question_no", "standards", "total_possible_point", "total_score",
        "grade_average", "percentage_incorrect_answers",
    },
    "cube_questionincorrectchoice_summary": {
        "id", "school_id", "question_id", "ukey", "answer_submission",
        "total_student", "total_possible_point", "total_score", "grade_average",
        "percentage_incorrect_answers",
    },
    "cube_question_summary_overall": {
        "id", "school_id", "subject_id", "ukey", "question_no", "question",
        "question_no_url", "position_number", "correct_answer",
        "total_possible_point", "total_score", "grade_average",
        "percentage_incorrect_answers", "standards", "description",
        "section_instructors", "incorrect_choice_details", "incorrect_details_name",
        "incorrect_choice_details_hash", "incorrect_details_name_hash",
        "teacher_name_hash",
    },
}


def rehash(school_uuid: str, original_id) -> str:
    return hashlib.sha256(f"{school_uuid}:{original_id}".encode()).hexdigest()


def grade_band(grade: str) -> str | None:
    """Bucket a messy Grade string into elementary/middle/high, or None."""
    if not isinstance(grade, str):
        return None
    g = grade.strip()
    if re.search(r"\bK\b|Kinder", g, re.I):
        return "elementary"
    m = re.search(r"(\d{1,2})", g)
    if not m:
        if g.upper().startswith("HS"):
            return "high"
        return None
    n = int(m.group(1))
    if n <= 5:
        return "elementary"
    if n <= 8:
        return "middle"
    if n <= 12:
        return "high"
    return None


def read_partition(cube: str, school_id: str, columns=None) -> pd.DataFrame:
    d = ds.dataset(str(CUBES / cube), partitioning="hive", format="parquet")
    tbl = d.to_table(filter=ds.field("School_ID") == school_id, columns=columns)
    return tbl.to_pandas()


def read_flat(cube: str) -> pd.DataFrame:
    files = [str(f) for f in (CUBES / cube).rglob("*.parquet")]
    return ds.dataset(files, format="parquet").to_table().to_pandas()


def make_profiles(n: int) -> list[dict]:
    bands = ["elementary", "middle", "high"]
    cities = [
        "Riverside", "Oakwood", "Summit", "Lincoln", "Jefferson", "Maple",
        "Harborview", "Pinecrest", "Lakeside", "Fairmont", "Westfield",
        "Brookhaven", "Stonebridge", "Cedar Park", "Northgate", "Sunnyvale",
        "Glenwood", "Easton", "Kingsley", "Ashford", "Meadowbrook", "Clearwater",
        "Ridgeline", "Bayshore", "Hillcrest", "Crestmont", "Fox Valley",
        "Silverlake", "Thornton", "Whitman",
    ]
    kinds = {"elementary": "Elementary", "middle": "Middle", "high": "High"}
    out = []
    for i in range(n):
        band = bands[i % 3]
        city = cities[i % len(cities)]
        out.append({
            "idx": i,
            "band": band,
            "name": f"{city} {kinds[band]} School",
            "short_name": f"{city[:4].upper()}{kinds[band][0]}",
            "building_id": f"{SYNTH_PREFIX}{i:03d}",
            "school_csv": f"99{i:05d}",  # synthetic numeric building id
        })
    return out


def copy_df(cur, table: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = list(df.columns)
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    cur.copy_expert(
        f"COPY {table} ({','.join(cols)}) FROM STDIN WITH (FORMAT csv, NULL '\\N')",
        buf,
    )
    return len(df)


def project(df: pd.DataFrame, target_cols: set[str], school_uuid: str,
            school_csv: str) -> pd.DataFrame:
    """Normalise columns, re-key id/school, keep only target columns."""
    df = df.rename(columns={c: norm(c) for c in df.columns})
    df = df.loc[:, [c for c in df.columns if c in target_cols]].copy()
    df["id"] = df["id"].map(lambda x: rehash(school_uuid, x))
    df["school_id"] = school_uuid
    if "school_id_csv" in target_cols:
        df["school_id_csv"] = school_csv
    # ensure every target column exists (NULL-fill the rest)
    for c in target_cols:
        if c not in df.columns:
            df[c] = None
    return df.loc[:, sorted(target_cols)]


def main() -> int:
    _require_demo_seed_optin()

    ap = argparse.ArgumentParser()
    ap.add_argument("--schools", type=int, default=25)
    ap.add_argument("--items-min", type=int, default=8)
    ap.add_argument("--items-max", type=int, default=14)
    ap.add_argument("--reset", action="store_true",
                    help="delete previously-seeded synthetic schools first")
    ap.add_argument("--i-understand", action="store_true",
                    help="opt in to re-seeding synthetic demo tenants (disabled by default)")
    args = ap.parse_args()

    print("Loading donor cube data (Athenian)…", flush=True)
    qs = read_partition("Cube_Question_Summary", DONOR_SCHOOL)
    print(f"  question_summary: {len(qs):,} rows", flush=True)

    # Item index: distinct items with grade band + subject for profile sampling.
    items = (qs[["Item_ID", "Grade", "Subject", "Subject_ID"]]
             .dropna(subset=["Item_ID"]).drop_duplicates("Item_ID").copy())
    items["band"] = items["Grade"].map(grade_band)
    by_band: dict[str, list[str]] = {b: items[items.band == b]["Item_ID"].tolist()
                                     for b in ("elementary", "middle", "high")}
    # Fallback pool: any item (used when a band is thin).
    all_items = items["Item_ID"].tolist()
    print({b: len(v) for b, v in by_band.items()}, f"(total {len(all_items)})",
          flush=True)

    us = read_partition("Cube_User_Summary", DONOR_SCHOOL)
    print(f"  user_summary: {len(us):,} rows", flush=True)
    std = read_flat("Cube_Standard_Summary")
    ovp = read_flat("Cube_OverallPerformance_Summary")
    qic = read_flat("Cube_QuestionIncorrectChoice_Summary")
    qso = read_flat("Cube_Question_Summary_Overall")
    ssum = read_partition("Cube_School_Summary", DONOR_SCHOOL)
    gsum = read_partition("Cube_Grade_Summary", DONOR_SCHOOL)
    print("  loaded school/grade/flat cubes", flush=True)

    conn = psycopg2.connect(PG)
    conn.autocommit = False
    cur = conn.cursor()

    if args.reset:
        cur.execute(
            "DELETE FROM schools WHERE schoology_building_id LIKE %s",
            (SYNTH_PREFIX + "%",),
        )
        print(f"  reset: removed prior synthetic schools ({cur.rowcount})",
              flush=True)

    profiles = make_profiles(args.schools)
    totals: dict[str, int] = {}
    rng = random.Random(20260601)

    for prof in profiles:
        # create the school row, get its UUID
        cur.execute(
            """INSERT INTO schools (schoology_building_id, schoology_school_id,
                   name, short_name, current_session, is_active)
               VALUES (%s, %s, %s, %s, '2025-26', true)
               RETURNING school_id""",
            (prof["building_id"], prof["school_csv"], prof["name"],
             prof["short_name"]),
        )
        school_uuid = str(cur.fetchone()[0])
        csv = prof["school_csv"]

        pool = by_band.get(prof["band"]) or []
        if len(pool) < args.items_max:
            pool = pool + all_items
        k = rng.randint(args.items_min, args.items_max)
        chosen = rng.sample(pool, min(k, len(pool)))
        chosen_set = set(chosen)

        # slice donor rows for the chosen items
        qs_s = qs[qs["Item_ID"].isin(chosen_set)]
        us_s = us[us["Item_ID"].isin(chosen_set)]
        ssum_s = ssum[ssum["Item_ID"].isin(chosen_set)]
        gsum_s = gsum[gsum["Item_ID"].isin(chosen_set)]
        std_s = std[std["Item_ID"].isin(chosen_set)]
        ovp_s = ovp[ovp["Item_ID"].isin(chosen_set)]
        qids = set(qs_s["Question_ID"].dropna())
        ukeys = set(qs_s["Ukey"].dropna())
        qic_s = qic[qic["Question_ID"].isin(qids)]
        qso_s = qso[qso["uKey"].isin(ukeys)]

        def load(table, frame):
            n = copy_df(cur, table, project(frame, CUBE_TARGETS[table],
                                            school_uuid, csv))
            totals[table] = totals.get(table, 0) + n

        load("cube_question_summary", qs_s)
        load("cube_user_summary", us_s)
        load("cube_school_summary", ssum_s)
        load("cube_grade_summary", gsum_s)
        load("cube_standard_summary", std_s)
        load("cube_overallperformance_summary", ovp_s)
        load("cube_questionincorrectchoice_summary", qic_s)
        load("cube_question_summary_overall", qso_s)

        # ---- derived dims (from the question/user slices) ----
        _seed_dims(cur, school_uuid, csv, qs_s, totals)
        conn.commit()
        print(f"  [{prof['idx']+1}/{len(profiles)}] {prof['name']:32s} "
              f"band={prof['band']:10s} items={len(chosen):2d}", flush=True)

    cur.close()
    conn.close()
    print("\nDONE. Row totals across synthetic schools:")
    for t in sorted(totals):
        print(f"  {t:42s} {totals[t]:,}")
    return 0


def _seed_dims(cur, school_uuid, csv, qs_s, totals):
    """Derive dim_item / dim_section / dim_subject / dim_question_data."""
    # dim_item
    di = (qs_s.groupby("Item_ID", as_index=False)
          .agg(subject_id=("Subject_ID", "first"), item_type=("Item_Type", "first"),
               item_name=("Item_Name", "first"), section_name=("Section_Name", "first"),
               section_instructors=("Section_Instructors", "first"),
               assessment_date=("assessment_date", "first")))
    di = di.rename(columns={"Item_ID": "item_id"})
    di["school_id"] = school_uuid
    di["school_id_csv"] = csv
    di["assessment_date"] = pd.to_datetime(di["assessment_date"], errors="coerce").dt.date
    totals["dim_item"] = totals.get("dim_item", 0) + copy_df(
        cur, "dim_item", di[["item_id", "school_id", "subject_id", "item_type",
                             "item_name", "school_id_csv", "section_name",
                             "section_instructors", "assessment_date"]])

    # dim_subject (one row per Subject_ID)
    dsub = (qs_s.dropna(subset=["Subject_ID"]).groupby("Subject_ID", as_index=False)
            .agg(subject=("Subject", "first"), assessment_type=("Assessment_type", "first"),
                 grade=("Grade", "first"), session=("Session", "first"),
                 item_name=("Item_Name", "first")))
    dsub = dsub.rename(columns={"Subject_ID": "subject_id"})
    dsub["school_id"] = school_uuid
    dsub["school_id_csv"] = csv
    for c in ("grade_sort", "show_history_subject", "grade_no"):
        dsub[c] = None
    totals["dim_subject"] = totals.get("dim_subject", 0) + copy_df(
        cur, "dim_subject", dsub[["subject_id", "school_id", "school_id_csv",
                                  "subject", "assessment_type", "grade", "session",
                                  "item_name", "grade_sort", "show_history_subject",
                                  "grade_no"]])

    # dim_section — keyed by a synthetic section_nid (Section name as id).
    dsec = (qs_s.dropna(subset=["Section"]).groupby("Section", as_index=False)
            .agg(item_id=("Item_ID", "first"), section_name=("Section_Name", "first"),
                 section_instructors=("Section_Instructors", "first")))
    dsec = dsec.rename(columns={"Section": "section_nid"})
    dsec["school_id"] = school_uuid
    dsec["school_id_csv"] = csv
    dsec["section_code"] = dsec["section_nid"]
    totals["dim_section"] = totals.get("dim_section", 0) + copy_df(
        cur, "dim_section", dsec[["section_nid", "school_id", "section_code",
                                  "item_id", "section_name", "section_instructors",
                                  "school_id_csv"]])

    # dim_question_data — one row per Qkey.
    dq = (qs_s.dropna(subset=["Qkey"]).drop_duplicates("Qkey").copy())
    dq = dq.rename(columns={c: norm(c) for c in dq.columns})
    dq["school_id"] = school_uuid
    dq["school_id_csv"] = csv
    qd_cols = ["qkey", "school_id", "ukey", "question", "position_number", "item_id",
               "item_name", "school_id_csv", "standards", "question_id", "question_no",
               "least_points_earned", "correct_answer", "question_type",
               "average_points_earned", "associated_question_id", "total_points",
               "most_points_earned", "correctly_answered", "sub_question", "session",
               "assessment_type", "subject", "grade", "section", "standard",
               "identifier"]
    for c in qd_cols:
        if c not in dq.columns:
            dq[c] = None
    totals["dim_question_data"] = totals.get("dim_question_data", 0) + copy_df(
        cur, "dim_question_data", dq[qd_cols])


if __name__ == "__main__":
    raise SystemExit(main())
