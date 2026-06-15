#!/usr/bin/env python3
"""Faithful 1:1 loader: legacy stage3_cubes parquet → cube_* / dim_* tables.

Unlike ``seed_synthetic_schools.py`` (which SAMPLES a subset of items and
fabricates ids to fan out demo tenants), this loader is a **faithful, no-
sampling** importer for the REAL backup schools. For each target school it:

* reads the school's School_ID-partitioned cubes (Cube_School_Summary,
  Cube_Grade_Summary, Cube_User_Summary, Cube_Question_Summary) — ALL rows,
* slices the four flat cubes (Cube_Standard_Summary, Cube_OverallPerformance_
  Summary, Cube_QuestionIncorrectChoice_Summary, Cube_Question_Summary_Overall)
  — which carry NO School_ID column — by the school's join keys
  (Item_ID / Question_ID / uKey) recovered from the school's question cube,
* re-keys every id with ``sha256(school_uuid + ':' + original_id)`` the SAME
  way ``seed_synthetic_schools.py`` does, so the cubes join internally,
* stamps ``school_id`` = the school's REAL UUID (from the ``schools`` row,
  matched on ``schoology_building_id``) and ``school_id_csv`` = the building id,
* derives the dims the report endpoints need (dim_item / dim_subject /
  dim_section / dim_question_data), populating ``standard`` + ``identifier``
  so the canonical-KPI and strand/standard rollup queries resolve,
* APPENDS per-school: it deletes only THIS school's prior rows first (idempotent
  re-run), never truncating other schools' data,
* drops the ``__HIVE_DEFAULT_PARTITION__`` (read_partition filters on an exact
  School_ID, so the null partition is never selected).

dim_standard / dim_strand are global (already seeded) and untouched.

NOTE: the backup parquet is already pseudonymized — StudentName_Hash /
TeacherName_Hash render as "Student_Name N" / "Teacher_Name N", not real names.

Usage:
    DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:56322/scratch_rebuild \
      python3 supabase/seeds/load_real_schools.py \
      --schools 554425139,7368546879,7440430446,7448280461
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
import pyarrow.dataset as ds

CUBES = Path(
    "/Users/mac/Desktop/PS_P/legacy-backup-20260529/synapse/stage3_cubes"
)

DEFAULT_PG = "postgresql://postgres:postgres@127.0.0.1:56322/postgres"

# Cubes that ARE Hive-partitioned by School_ID.
PARTITIONED_CUBES = (
    "Cube_School_Summary",
    "Cube_Grade_Summary",
    "Cube_User_Summary",
    "Cube_Question_Summary",
)
# Cubes stored flat (no School_ID column) — sliced by join keys per school.
FLAT_CUBES = (
    "Cube_Standard_Summary",
    "Cube_OverallPerformance_Summary",
    "Cube_QuestionIncorrectChoice_Summary",
    "Cube_Question_Summary_Overall",
)

# Cube tables we re-key + load (used for the per-school DELETE on re-run).
CUBE_TABLES = (
    "cube_question_summary",
    "cube_user_summary",
    "cube_school_summary",
    "cube_grade_summary",
    "cube_standard_summary",
    "cube_overallperformance_summary",
    "cube_questionincorrectchoice_summary",
    "cube_question_summary_overall",
)
DIM_TABLES = ("dim_item", "dim_subject", "dim_section", "dim_question_data",
              "dim_grade", "dim_session")

# ── column-name normalisation (backup PascalCase -> target snake_case) ──
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
    return SPECIAL.get(col, col.lower())


# Target columns per cube (must exist in the DB DDL). Columns absent from the
# backup are filled NULL; backup columns absent here are dropped. Identical to
# seed_synthetic_schools.CUBE_TARGETS so the re-key + projection stay in lockstep.
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


def _cube_dir(cube: str) -> Path:
    """The backup nests each cube one level: ``Cube_X/Cube_X/``."""
    return CUBES / cube / cube


def read_partition(cube: str, school_id: str, columns=None) -> pd.DataFrame:
    """Read ONE School_ID partition (Hive). Never returns the null partition."""
    d = ds.dataset(str(_cube_dir(cube)), partitioning="hive", format="parquet")
    tbl = d.to_table(filter=ds.field("School_ID") == school_id, columns=columns)
    return tbl.to_pandas()


def read_flat(cube: str) -> pd.DataFrame:
    """Read a flat (un-partitioned) cube in full — contains all schools mixed."""
    files = [str(f) for f in _cube_dir(cube).rglob("*.parquet")]
    return ds.dataset(files, format="parquet").to_table().to_pandas()


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
    for c in target_cols:
        if c not in df.columns:
            df[c] = None
    return df.loc[:, sorted(target_cols)]


def _lookup_school(cur, building_id: str) -> str:
    cur.execute(
        "SELECT school_id FROM schools WHERE schoology_building_id = %s",
        (building_id,),
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit(
            f"No schools row for schoology_building_id={building_id!r}. "
            "Seed the school first."
        )
    return str(row[0])


def _delete_existing(cur, school_uuid: str) -> None:
    """Remove only THIS school's prior cube + dim rows (idempotent re-run)."""
    for tbl in CUBE_TABLES + DIM_TABLES:
        cur.execute(f"DELETE FROM {tbl} WHERE school_id = %s", (school_uuid,))


def _seed_dims(cur, school_uuid, csv, qs_s, totals):
    """Derive dim_item / dim_subject / dim_section / dim_question_data.

    Mirrors seed_synthetic_schools._seed_dims, but dim_question_data here
    also carries ``standard`` + ``identifier`` (singular) so the canonical
    KPI (COUNT DISTINCT standard) and the strand/standard rollups resolve.
    """
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

    # dim_grade / dim_session — distinct values that power the Grade/Session
    # filter dropdowns. The list filter itself matches dim_subject.grade/session;
    # without these option rows the dropdowns are empty and parquet schools look
    # un-filterable on grade/session even though the data is there.
    dg = dsub[["grade"]].dropna().drop_duplicates()
    dg = dg[dg["grade"].astype(str).str.strip() != ""]
    if not dg.empty:
        dg["school_id"] = school_uuid
        dg["school_id_csv"] = csv
        dg["grade_id"] = dg["grade"].map(lambda g: rehash(school_uuid, f"grade:{g}"))
        totals["dim_grade"] = totals.get("dim_grade", 0) + copy_df(
            cur, "dim_grade", dg[["grade_id", "school_id", "school_id_csv", "grade"]])

    dse = dsub[["session"]].dropna().drop_duplicates()
    dse = dse[dse["session"].astype(str).str.strip() != ""]
    if not dse.empty:
        dse["school_id"] = school_uuid
        dse["school_id_csv"] = csv
        dse["session_id"] = dse["session"].map(lambda s: rehash(school_uuid, f"session:{s}"))
        totals["dim_session"] = totals.get("dim_session", 0) + copy_df(
            cur, "dim_session", dse[["session_id", "school_id", "school_id_csv", "session"]])

    # dim_section — keyed by Section name as the synthetic section_nid.
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

    # dim_question_data — one row per Qkey. Carries standard + identifier so the
    # report rollups / canonical-KPI joins resolve (NOT just the standards list).
    #
    # The real backup ``Qkey`` is the concatenation key Spark used and can run
    # to thousands of characters (up to ~7.5 KB) — far over the btree PK limit
    # (2704 B on ``dim_question_data_pkey (school_id, qkey)``). ``qkey`` is the
    # table's PK ONLY; no report query joins on it across tables (verified), so
    # we re-key it with the SAME sha256(school_uuid + ':' + original) used for
    # the cube ``id`` PKs. This keeps it bounded + unique-per-original-qkey
    # without changing any report output.
    dq = (qs_s.dropna(subset=["Qkey"]).drop_duplicates("Qkey").copy())
    dq = dq.rename(columns={c: norm(c) for c in dq.columns})
    dq["qkey"] = dq["qkey"].map(lambda x: rehash(school_uuid, x))
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


def load_school(cur, building_id: str, totals: dict[str, int]) -> dict[str, int]:
    """Faithful 1:1 load of one real school from its parquet partition."""
    school_uuid = _lookup_school(cur, building_id)
    csv = building_id
    _delete_existing(cur, school_uuid)

    # Partitioned cubes — ALL rows for this school (no sampling).
    qs = read_partition("Cube_Question_Summary", building_id)
    us = read_partition("Cube_User_Summary", building_id)
    ssum = read_partition("Cube_School_Summary", building_id)
    gsum = read_partition("Cube_Grade_Summary", building_id)

    # Flat cubes — slice by this school's join keys (Item_ID / Question_ID / uKey).
    items = set(qs["Item_ID"].dropna())
    qids = set(qs["Question_ID"].dropna())
    ukeys = set(qs["Ukey"].dropna())

    std = read_flat("Cube_Standard_Summary")
    ovp = read_flat("Cube_OverallPerformance_Summary")
    qic = read_flat("Cube_QuestionIncorrectChoice_Summary")
    qso = read_flat("Cube_Question_Summary_Overall")
    std_s = std[std["Item_ID"].isin(items)]
    ovp_s = ovp[ovp["Item_ID"].isin(items)]
    qic_s = qic[qic["Question_ID"].isin(qids)]
    qso_s = qso[qso["uKey"].isin(ukeys)]

    per_school: dict[str, int] = {}

    def load(table, frame):
        proj = project(frame, CUBE_TARGETS[table], school_uuid, csv)
        # Keep cube_question_summary.qkey consistent with the re-keyed
        # dim_question_data.qkey (sha256). No report joins on it; this only
        # preserves cross-table consistency and bounds the value length.
        if table == "cube_question_summary" and "qkey" in proj.columns:
            proj["qkey"] = proj["qkey"].map(
                lambda x: rehash(school_uuid, x) if pd.notna(x) else None
            )
        n = copy_df(cur, table, proj)
        per_school[table] = n
        totals[table] = totals.get(table, 0) + n

    load("cube_question_summary", qs)
    load("cube_user_summary", us)
    load("cube_school_summary", ssum)
    load("cube_grade_summary", gsum)
    load("cube_standard_summary", std_s)
    load("cube_overallperformance_summary", ovp_s)
    load("cube_questionincorrectchoice_summary", qic_s)
    load("cube_question_summary_overall", qso_s)

    before_dims = {k: totals.get(k, 0) for k in DIM_TABLES}
    _seed_dims(cur, school_uuid, csv, qs, totals)
    for k in DIM_TABLES:
        per_school[k] = totals.get(k, 0) - before_dims[k]

    per_school["school_uuid"] = school_uuid  # type: ignore[assignment]
    return per_school


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--schools", required=True,
        help="comma-separated schoology_building_id list (the real School_IDs).",
    )
    args = ap.parse_args()
    building_ids = [s.strip() for s in args.schools.split(",") if s.strip()]

    pg = os.environ.get("DATABASE_URL", DEFAULT_PG)
    # psycopg2 wants the plain libpq URL, not the asyncpg variant.
    pg = pg.replace("postgresql+asyncpg://", "postgresql://")

    conn = psycopg2.connect(pg)
    conn.autocommit = False
    cur = conn.cursor()

    totals: dict[str, int] = {}
    for bid in building_ids:
        ps = load_school(cur, bid, totals)
        conn.commit()
        suid = ps.pop("school_uuid", "")
        print(f"\n[{bid}] school_id={suid}", flush=True)
        for t in CUBE_TABLES + DIM_TABLES:
            print(f"    {t:42s} {ps.get(t, 0):,}", flush=True)

    cur.close()
    conn.close()

    print("\nDONE. Row totals across loaded real schools:")
    for t in sorted(totals):
        print(f"  {t:42s} {totals[t]:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
