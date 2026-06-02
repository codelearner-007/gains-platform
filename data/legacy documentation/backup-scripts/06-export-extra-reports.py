#!/usr/bin/env python3
"""06-export-extra-reports.py — export the report types beyond QSR + QRA.

The original 05 run exported 2 of the 10 legacy paginated reports (Question
Summary Report + Question Response Analysis). This exports the remaining
deliverable types into a SEPARATE folder so they can be merged into the
original tree later (report-type is in the filename, so no collisions).

Report types covered (validated against live PBI 2026-06-02):

  Per-assessment (one file per assessment, parameterised by Item_ID):
    * Question Summary Report - color
    * Question Summary Report - Teacher
    * Question Response Analysis By Teacher
    * Question Response Analysis By Standard And Teacher

  Aggregate YTD (one file per grade x subject x session, all assessment types):
    * YTD Longitudinal
    * YTD Longitudinal 2
    * YTD Longitudinal 3

EXCLUDED: "Question Summary Report - Teacher Subtotal" — broken at the source
(consistent Analysis Services Connection_Error_General on every attempt; it is
also the only report with no sample in legacy `sample reports/`, i.e. it never
rendered in legacy either).

Reuses 05's token mgmt / http_with_retry / DAX inventory / worker pool.
Resumable: skips files already on disk.

Usage:
    .delta-venv/bin/python 06-export-extra-reports.py \
        --schools 554425139 7440430446 --sessions 2024-25 2025-26 --workers 10
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

# ── import 05's machinery ──────────────────────────────────────────────────
_SPEC = importlib.util.spec_from_file_location(
    "exp05",
    str(Path(__file__).with_name("05-export-reports.py")),
)
exp = importlib.util.module_from_spec(_SPEC)
sys.modules["exp05"] = exp
_SPEC.loader.exec_module(exp)

OUT_ROOT = Path.home() / "Desktop/PS_P/historical-reports-newtypes"
PBI_API = exp.PBI_API
WORKSPACE = exp.WORKSPACE
SCHOOL_NAMES = exp.SCHOOL_NAMES
sanitize = exp.sanitize

# ── report registry ────────────────────────────────────────────────────────
# Per-assessment reports: (label, report_id, format, param_prefix)
PER_ASSESSMENT = [
    ("Question Summary Report - color",
     "15fcb757-465e-4037-b414-72a23ea578eb", "PDF", "cubeuserssummary"),
    ("Question Summary Report - Teacher",
     "93233571-b9e5-423b-9170-69184c5c2708", "PDF", "cubeuserssummary"),
    ("Question Response Analysis By Teacher",
     "43a35555-38c4-4b20-85e7-1f9784889cad", "PDF", "cubequestionsummary"),
    ("Question Response Analysis By Standard And Teacher",
     "0ffc8105-9687-4175-b14a-599466c1627e", "PDF", "cubequestionsummary"),
]

# YTD aggregate reports: (label, report_id, format)
YTD = [
    ("YTD Longitudinal", "665d1328-773d-4625-a3d4-e86c048c027d", "PDF"),
    ("YTD Longitudinal 2", "4fc3a563-6992-4235-8523-124251b1ed42", "PDF"),
    ("YTD Longitudinal 3", "f446cf28-0ecd-4c3c-8de3-c82fcf5263d5", "PDF"),
]


@dataclass
class Job:
    report_id: str
    report_label: str
    fmt: str
    params: list
    out_path: Path
    report_kind: str = field(default="")

    def __post_init__(self):
        self.report_kind = self.report_label

    def body(self) -> dict:
        return {
            "format": self.fmt,
            "paginatedReportConfiguration": {"parameterValues": self.params},
        }


def per_assessment_params(prefix: str, a: dict) -> list:
    return [
        {"name": f"{prefix}ItemID", "value": str(a["item_id"])},
        {"name": f"{prefix}ItemName", "value": str(a["item_name"])},
        {"name": f"{prefix}Grade", "value": str(a["grade"] or "")},
        {"name": f"{prefix}Subject", "value": str(a["subject"] or "")},
        {"name": f"{prefix}Session", "value": str(a["session"] or "")},
        {"name": f"{prefix}Assessmenttype", "value": str(a["atype"] or "")},
    ]


def ytd_params(grade: str, subject: str, session: str, atype: str,
               school_csv: str) -> list:
    # Single-value Assessmenttype: the PBI ExportTo API rejects repeated-name
    # multi-value here (rsParametersNotSpecified), and one report per
    # (grade, subject, atype) is itself a valid longitudinal unit.
    p = "cubeuserssummary"
    return [
        {"name": f"{p}Grade", "value": grade or ""},
        {"name": f"{p}Subject", "value": subject or ""},
        {"name": f"{p}Session", "value": session or ""},
        {"name": f"{p}Assessmenttype", "value": atype or ""},
        {"name": f"{p}SchoolID", "value": school_csv},
    ]


def build_jobs(schools: list[str], sessions: list[str]) -> list[Job]:
    jobs: list[Job] = []
    for session in sessions:
        # fresh DAX inventory per session (cached by 05 under a per-session file)
        exp.DAX_CACHE = Path(
            exp.DAX_CACHE_TMPL.format(session=session)
        )
        df = exp.load_assessments(schools, session)
        if df.empty:
            print(f"  [{session}] no assessments")
            continue

        # ---- per-assessment jobs ----
        for _, r in df.iterrows():
            school_id = r["__school_id"]
            school = SCHOOL_NAMES.get(school_id, f"School-{school_id}")
            grade = sanitize(str(r.get("Grade") or "Unknown-Grade"))
            subj = sanitize(str(r.get("Subject") or "Unknown-Subject"))
            a = {
                "item_id": r["Item_ID"], "item_name": r["Item_Name"],
                "grade": r.get("Grade"), "subject": r.get("Subject"),
                "session": r.get("Session"), "atype": r.get("Assessment_type"),
            }
            out_dir = OUT_ROOT / session / school / grade / subj
            for label, rid, fmt, prefix in PER_ASSESSMENT:
                ext = "xlsx" if fmt == "XLSX" else "pdf"
                fn = f"{sanitize(str(r['Item_Name']))} [{r['Item_ID']}]-{label}.{ext}"
                jobs.append(Job(rid, label, fmt,
                                per_assessment_params(prefix, a),
                                out_dir / fn))

        # ---- YTD jobs: one per (school, grade, subject, assessment_type) ----
        combos: set[tuple] = set()
        for _, r in df.iterrows():
            combos.add((r["__school_id"], str(r.get("Grade") or ""),
                        str(r.get("Subject") or ""),
                        str(r.get("Assessment_type") or "")))
        for (school_id, grade, subject, atype) in combos:
            school = SCHOOL_NAMES.get(school_id, f"School-{school_id}")
            g, s = sanitize(grade or "Unknown-Grade"), sanitize(subject or "Unknown-Subject")
            at = sanitize(atype or "Unknown-Type")
            out_dir = OUT_ROOT / session / school / g / s / "_YTD"
            for label, rid, fmt in YTD:
                fn = f"{g}-{s}-{at}-{label}.pdf"
                jobs.append(Job(rid, label, fmt,
                                ytd_params(grade, subject, session, atype,
                                           school_id),
                                out_dir / fn))
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schools", nargs="+",
                    default=["554425139", "7440430446"])
    ap.add_argument("--sessions", nargs="+", default=["2024-25", "2025-26"])
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    print(f"Schools:  {args.schools}")
    print(f"Sessions: {args.sessions}")
    print(f"Output:   {OUT_ROOT}")
    print(f"Reports:  {len(PER_ASSESSMENT)} per-assessment + {len(YTD)} YTD")
    print()

    jobs = build_jobs(args.schools, args.sessions)
    if args.limit:
        jobs = jobs[: args.limit]
    print(f"Total report jobs: {len(jobs)}")

    todo = [j for j in jobs
            if not (j.out_path.exists() and j.out_path.stat().st_size > 0)]
    print(f"Already on disk:   {len(jobs) - len(todo)}")
    print(f"Remaining:         {len(todo)}\n")
    if not todo:
        print("Nothing to do.")
        return 0

    ok = fail = 0
    start = time.time()
    log_lock = Lock()
    log_path = OUT_ROOT / "export-log.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(line: str):
        with log_lock:
            print(line, flush=True)
            with log_path.open("a") as f:
                f.write(line + "\n")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(exp.run_export, j): j for j in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                job, status, msg = fut.result()
            except Exception as e:
                job, status, msg = futures[fut], "FAIL", f"exception: {e}"
            if status == "OK":
                ok += 1
                log(f"[{i}/{len(todo)}] OK    {job.out_path.name}  ({msg})")
            elif status == "SKIP":
                log(f"[{i}/{len(todo)}] SKIP  {job.out_path.name}")
            else:
                fail += 1
                log(f"[{i}/{len(todo)}] FAIL  {job.out_path.name}  ({msg})")
            if i % 25 == 0:
                el = time.time() - start
                rate = i / el if el else 0
                eta = (len(todo) - i) / rate / 60 if rate else 0
                print(f"  … {i}/{len(todo)} rate={rate:.2f}/s ETA={eta:.1f}min",
                      flush=True)

    print(f"\nDONE in {(time.time()-start)/60:.1f} min.  OK={ok}  FAIL={fail}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
