#!/usr/bin/env python3
"""
05-export-reports.py — parallel PBI ExportToFile for the historical reports.

For each (school, 2025-26 assessment) pair:
  * Question Summary Report  (XLSX)
  * Question Response Analysis (PDF)

Reads the assessment inventory from the local Cube_User_Summary parquet
backup (no live Synapse queries needed). Posts to PBI ReportWithCube
workspace, polls, downloads. ~10 parallel workers.

Resumable: skips files that already exist on disk. Re-running picks up
where it left off.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Optional

import pyarrow.parquet as pq
import pandas as pd
import requests

# ── Constants ────────────────────────────────────────────────────────────
BACKUP_DIR = Path.home() / "Desktop/PS_P/legacy-backup-20260529"
CUBE_ROOT  = BACKUP_DIR / "synapse/stage3_cubes"
OUT_BASE   = Path.home() / "Desktop/PS_P/historical-reports"
OUT_ROOT   = OUT_BASE / "2025-26"  # set per-session in main()

PBI_API    = "https://api.powerbi.com/v1.0/myorg"
WORKSPACE  = "8215049c-ebd6-4a9b-bb98-5b5fdb7d3da4"     # ReportWithCube
REPORT_QSR = "c037c229-e9d1-46cb-bd01-8dcc946be065"     # Question Summary Report
REPORT_QRA = "2019f225-26d9-478f-bf0f-9d6f67b45ecd"     # Question Response Analysis

# School_ID → friendly folder name. Verified 2026-05-29 via Power BI dataset
# parameters API (each per-school workspace exposes School_Name + SchoolID).
SCHOOL_NAMES = {
    "186370968":  "Athenian Academy",
    "7368546879": "South Prep Scholars Academy",
    "7440430446": "CrestWell School",
    "554425139":  "Central Florida Preparatory",
    "7448280461": "Brightview (no 2025-26 data)",
}

# Default: only the two priority schools (CFP + CrestWell) per user.
DEFAULT_SCHOOLS = ["554425139", "7440430446"]

MAX_WORKERS    = 10
POLL_MIN_SEC   = 3
POLL_MAX_MIN   = 5
TOKEN_REFRESH  = 2400   # refresh token every 40 min (safer than 45)

_token_lock = Lock()
_token: dict = {"value": None, "expires": 0.0}

# ── Helpers ──────────────────────────────────────────────────────────────
def get_token() -> str:
    """Acquire (and refresh) the PBI access token."""
    with _token_lock:
        now = time.time()
        if _token["value"] and now < _token["expires"]:
            return _token["value"]
        out = subprocess.check_output(
            ["az", "account", "get-access-token",
             "--resource", "https://analysis.windows.net/powerbi/api",
             "--query", "accessToken", "-o", "tsv"],
            text=True,
        ).strip()
        _token["value"] = out
        _token["expires"] = now + TOKEN_REFRESH
        return out

def auth_headers() -> dict:
    return {"Authorization": f"Bearer {get_token()}"}

def sanitize(s: str) -> str:
    """Clean a string for filesystem use."""
    s = re.sub(r"[\/\\:*?\"<>|]", "-", str(s))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:140]

def build_filename(grade: str, item: str, report_kind: str, ext: str) -> str:
    return f"{sanitize(grade)}-{sanitize(item)}-{report_kind}.{ext}"

# ── Inventory ────────────────────────────────────────────────────────────
PBI_API_WS  = "8215049c-ebd6-4a9b-bb98-5b5fdb7d3da4"        # ReportWithCube
PBI_API_DS  = "3a869059-de30-4f2e-8a96-d45abff3c7e0"        # Assessment Analysis Dashboard
DAX_CACHE_TMPL = "/tmp/05-export-dax-cache-{session}.json"
DAX_CACHE   = Path("/tmp/05-export-dax-cache.json")  # set per-session in main()

def fetch_authoritative_inventory(schools: list[str], session: str) -> list[dict]:
    """Pull (Item_ID, Item_Name, Grade, Subject, Assessment_type,
    Section_Instructors, Subject_ID) from the live PBI dataset via DAX.
    Every value returned is guaranteed valid for ExportToFile (the same
    semantic model backs the RDLs we'll call).
    """
    # Build the FILTER predicate dynamically.
    sql = (' || '.join(f'cube_users_summary[School_ID] = "{s}"' for s in schools))
    query = (
        'EVALUATE SUMMARIZECOLUMNS('
        'cube_users_summary[School_ID],'
        'cube_users_summary[Item_ID],'
        'cube_users_summary[Item_Name],'
        'cube_users_summary[Grade],'
        'cube_users_summary[Subject],'
        'cube_users_summary[Assessment_type],'
        'cube_users_summary[Session],'
        'cube_users_summary[Section_Instructors],'
        'cube_question_summary_overall[Subject_ID],'
        f'FILTER(cube_users_summary, cube_users_summary[Session] = "{session}" && ({sql})))'
    )
    url = f"{PBI_API}/groups/{PBI_API_WS}/datasets/{PBI_API_DS}/executeQueries"
    r = http_with_retry("POST", url, json={"queries": [{"query": query}]})
    if r.status_code != 200:
        raise RuntimeError(f"DAX query failed: {r.status_code} {r.text[:300]}")
    rows = r.json()["results"][0]["tables"][0]["rows"]
    return rows

def load_assessments(schools: list[str], session: str) -> pd.DataFrame:
    """One row per Item_ID per school with PBI-canonical parameter values."""
    if DAX_CACHE.exists() and DAX_CACHE.stat().st_size > 1000:
        print(f"Using cached DAX inventory from {DAX_CACHE}")
        rows = json.loads(DAX_CACHE.read_text())
    else:
        print("Querying PBI for authoritative assessment inventory…")
        rows = fetch_authoritative_inventory(schools, session)
        DAX_CACHE.write_text(json.dumps(rows))
        print(f"  cached {len(rows)} rows to {DAX_CACHE}")

    if not rows:
        return pd.DataFrame()

    # Strip DAX column-name prefix (e.g. "cube_users_summary[Item_ID]" → "Item_ID")
    def strip_prefix(k: str) -> str:
        return k.split("[", 1)[1].rstrip("]") if "[" in k else k

    df = pd.DataFrame([{strip_prefix(k): v for k, v in r.items()} for r in rows])
    # Filter to requested schools (defence-in-depth)
    df = df[df["School_ID"].isin(schools)].copy()
    df["__school_id"] = df["School_ID"]

    # Multiple rows per Item_ID can occur when an assessment legitimately spans
    # multiple subjects / grades (PBI returns each distinct combo). Dedup
    # deterministically: prefer "Summative" atype, then alphabetic order of
    # Subject_ID (stable, reproducible).
    df["__atype_rank"] = (df["Assessment_type"] == "Summative").astype(int)
    df = df.sort_values(["Item_ID", "__atype_rank", "Subject_ID"],
                        ascending=[True, False, True])
    df = df.drop_duplicates(subset=["__school_id", "Item_ID"], keep="first")

    return df[["__school_id", "Item_ID", "Item_Name", "Grade", "Subject",
               "Assessment_type", "Session", "Section_Instructors", "Subject_ID"]]

# ── Export pipeline ──────────────────────────────────────────────────────
@dataclass
class ExportJob:
    school_id: str
    item_id: str
    item_name: str
    grade: str
    subject: str
    atype: str
    session: str
    instructor: str
    subject_id: str
    report_kind: str        # "Question Summary Report" or "Question Response Analysis"

    @property
    def out_dir(self) -> Path:
        # Nested: {school}/{grade}/{subject}/
        school = SCHOOL_NAMES.get(self.school_id, f"School-{self.school_id}")
        grade  = sanitize(self.grade or "Unknown-Grade")
        subj   = sanitize(self.subject or "Unknown-Subject")
        return OUT_ROOT / school / grade / subj

    @property
    def out_path(self) -> Path:
        ext = "xlsx" if self.report_kind == "Question Summary Report" else "pdf"
        # File: {item_name} [{item_id}]-{report-type}.{ext}
        # Item_ID suffix prevents collisions when 2 assessments in the same
        # (school, grade, subject) share an Item_Name (different sections /
        # dates). It also keeps the listing sorted by name.
        fn = f"{sanitize(self.item_name)} [{self.item_id}]-{self.report_kind}.{ext}"
        return self.out_dir / fn

    def body(self) -> dict:
        if self.report_kind == "Question Summary Report":
            return {
                "format": "XLSX",
                "paginatedReportConfiguration": {
                    "parameterValues": [
                        {"name": "cubeuserssummaryItemID",         "value": self.item_id},
                        {"name": "cubeuserssummaryItemName",       "value": self.item_name},
                        {"name": "cubeuserssummaryGrade",          "value": self.grade or ""},
                        {"name": "cubeuserssummarySubject",        "value": self.subject or ""},
                        {"name": "cubeuserssummaryAssessmenttype", "value": self.atype or ""},
                        {"name": "cubeuserssummarySession",        "value": self.session or ""},
                    ]
                },
            }
        else:
            return {
                "format": "PDF",
                "paginatedReportConfiguration": {
                    "parameterValues": [
                        {"name": "cubequestionsummaryoverallSubjectID", "value": self.subject_id or ""},
                        {"name": "Subject",          "value": self.subject or ""},
                        {"name": "Grade",            "value": self.grade or ""},
                        {"name": "AssessmentType",   "value": self.atype or ""},
                        {"name": "Item_Name",        "value": self.item_name},
                        {"name": "H3_Teacher",       "value": self.instructor or "n/a"},
                        {"name": "H3_AssessmentDate","value": "2025-09-01"},  # display-only label
                    ]
                },
            }

    @property
    def report_id(self) -> str:
        return REPORT_QSR if self.report_kind == "Question Summary Report" else REPORT_QRA

def _is_token_expired(r) -> bool:
    """PBI returns 401 or 403 with body code='TokenExpired' when token expires."""
    if r.status_code == 401:
        return True
    if r.status_code == 403:
        try:
            return r.json().get("error", {}).get("code") == "TokenExpired"
        except Exception:
            return False
    return False

def http_with_retry(method: str, url: str, **kw):
    """HTTP with 429/503 backoff, token refresh on 401/403-TokenExpired,
    and DNS / connection retry on transient network failures.
    macOS resolver has a habit of flaking out for ~30s; we keep retrying
    instead of failing the job."""
    import requests.exceptions as rxe
    last_exc = None
    for attempt in range(15):
        kw.setdefault("headers", {}).update(auth_headers())
        try:
            r = requests.request(method, url, timeout=60, **kw)
        except (rxe.ConnectionError, rxe.Timeout) as e:
            last_exc = e
            wait = min(60, 5 * (attempt + 1))   # 5, 10, 15, … 60s backoff
            print(f"   net-retry {attempt+1}/15 after {wait}s: {type(e).__name__}", flush=True)
            time.sleep(wait)
            continue
        if _is_token_expired(r):
            with _token_lock:
                _token["value"] = None
                _token["expires"] = 0
            time.sleep(1)
            continue
        if r.status_code in (429, 503):
            wait = int(r.headers.get("Retry-After", "10"))
            print(f"   {r.status_code} {url[-60:]} — waiting {wait}s", flush=True)
            time.sleep(wait + 1)
            continue
        return r
    # All retries exhausted
    if last_exc is not None:
        raise last_exc
    return r

def run_export(job: ExportJob) -> tuple[ExportJob, str, Optional[str]]:
    """Returns (job, status, message). status in {'OK','SKIP','FAIL'}."""
    out = job.out_path
    if out.exists() and out.stat().st_size > 0:
        return job, "SKIP", f"already on disk: {out.name}"

    out.parent.mkdir(parents=True, exist_ok=True)
    url = f"{PBI_API}/groups/{WORKSPACE}/reports/{job.report_id}/ExportTo"
    r = http_with_retry("POST", url, json=job.body())
    if r.status_code != 202:
        return job, "FAIL", f"POST {r.status_code}: {r.text[:200]}"
    export_id = r.json()["id"]

    # Poll
    poll_url = f"{PBI_API}/groups/{WORKSPACE}/reports/{job.report_id}/exports/{export_id}"
    deadline = time.time() + POLL_MAX_MIN * 60
    state = None
    while time.time() < deadline:
        r = http_with_retry("GET", poll_url)
        if r.status_code not in (200, 202):
            return job, "FAIL", f"poll {r.status_code}: {r.text[:200]}"
        body = r.json()
        state = body["status"]
        if state in ("Succeeded", "Failed"):
            break
        ra = r.headers.get("Retry-After")
        time.sleep(max(POLL_MIN_SEC, int(ra) if ra and ra.isdigit() else POLL_MIN_SEC))
    if state != "Succeeded":
        err = body.get("error", {}).get("message", "(timeout)") if body else "(no body)"
        return job, "FAIL", f"export {state}: {err[:200]}"

    # Download
    file_url = f"{poll_url}/file"
    r = http_with_retry("GET", file_url, stream=True)
    if r.status_code != 200:
        return job, "FAIL", f"download {r.status_code}"
    tmp = out.with_suffix(out.suffix + ".part")
    with tmp.open("wb") as f:
        for chunk in r.iter_content(chunk_size=64 * 1024):
            f.write(chunk)
    tmp.rename(out)
    return job, "OK", f"{out.stat().st_size // 1024} KB"

# ── Main ─────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schools", nargs="+", default=DEFAULT_SCHOOLS)
    ap.add_argument("--session", default="2025-26")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--limit", type=int, default=0, help="limit total exports (0=all)")
    args = ap.parse_args()

    global OUT_ROOT, DAX_CACHE
    OUT_ROOT = OUT_BASE / args.session
    DAX_CACHE = Path(DAX_CACHE_TMPL.format(session=args.session))

    print(f"Schools:  {args.schools}")
    print(f"Session:  {args.session}")
    print(f"Workers:  {args.workers}")
    print(f"Output:   {OUT_ROOT}")
    print()

    asmts = load_assessments(args.schools, args.session)
    if asmts.empty:
        print("No assessments found.")
        return 1
    print(f"Assessments: {len(asmts)}")
    for sid, grp in asmts.groupby("__school_id"):
        print(f"  School_ID={sid} → {len(grp)} assessments")
    print()

    jobs: list[ExportJob] = []
    for _, r in asmts.iterrows():
        common = dict(
            school_id=r["__school_id"],
            item_id=str(r["Item_ID"]),
            item_name=str(r["Item_Name"]),
            grade=str(r.get("Grade") or ""),
            subject=str(r.get("Subject") or ""),
            atype=str(r.get("Assessment_type") or ""),
            session=str(r.get("Session") or ""),
            instructor=str(r.get("Section_Instructors") or ""),
            subject_id=str(r.get("Subject_ID") or ""),
        )
        for kind in ("Question Summary Report", "Question Response Analysis"):
            jobs.append(ExportJob(**common, report_kind=kind))
    if args.limit:
        jobs = jobs[: args.limit]
    print(f"Total exports to attempt: {len(jobs)}")
    print()

    # Pre-skip files already on disk (compute fast)
    todo = [j for j in jobs if not (j.out_path.exists() and j.out_path.stat().st_size > 0)]
    print(f"Already on disk (skip): {len(jobs) - len(todo)}")
    print(f"Remaining to export:    {len(todo)}")
    print()
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
        futures = {pool.submit(run_export, j): j for j in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                job, status, msg = fut.result()
            except Exception as e:
                job = futures[fut]
                status, msg = "FAIL", f"exception: {e}"
            if status == "OK":
                ok += 1
                log(f"[{i}/{len(todo)}] OK    {job.out_path.name}  ({msg})")
            elif status == "SKIP":
                log(f"[{i}/{len(todo)}] SKIP  {job.out_path.name}  ({msg})")
            else:
                fail += 1
                log(f"[{i}/{len(todo)}] FAIL  {job.out_path.name}  ({msg})")
            if i % 25 == 0:
                elapsed = time.time() - start
                rate = i / elapsed
                eta = (len(todo) - i) / rate if rate > 0 else 0
                print(f"  … {i}/{len(todo)}  rate={rate:.2f}/s  ETA={eta/60:.1f}min", flush=True)

    elapsed = time.time() - start
    print()
    print(f"DONE in {elapsed/60:.1f} min.  OK={ok}  FAIL={fail}")
    return 0 if fail == 0 else 2

if __name__ == "__main__":
    sys.exit(main())
