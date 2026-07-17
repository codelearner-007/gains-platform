#!/usr/bin/env python
"""Golden-master capture harness for behavior-preserving Phase A/B refactors.

Runs the FastAPI app IN-PROCESS (httpx ASGITransport) with a superadmin auth
override, hits every dashboard/report GET endpoint plus every XLSX export across
all active schools, and serialises canonical snapshots so that::

    ./venv/bin/python scripts/capture_goldens.py --out /tmp/goldens/pre
    # ...refactor...
    ./venv/bin/python scripts/capture_goldens.py --out /tmp/goldens/post
    diff -r /tmp/goldens/pre /tmp/goldens/post   # MUST be empty

proves zero behaviour change (identical JSON, identical XLSX cell values + fills,
identical OpenAPI surface).

READ-ONLY: every call is a GET; nothing writes to the DB. The output dir is a
scratchpad path, never committed.

Item-based report routes discover representative ``item_id`` / subject / grade
values per school from ``/assessments/summary-list`` so the same cells are
captured pre and post (selection is deterministic: sorted, first N).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

import httpx

# Make ``app`` importable when run as ``scripts/capture_goldens.py`` from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.dependencies import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas.auth import CurrentUser  # noqa: E402

# ── Active schools (dev DB) ──────────────────────────────────────────────────
SCHOOLS = {
    "athenian": "019eb11c-410a-7ffb-86e6-a0294c669670",
    "cfp": "019eb11c-413b-7a66-a7d8-a18f14736ede",
    "crestwell": "019eb11c-413c-7ed9-872e-0fe5e9a947b6",
}

# How many representative assessments per school to sweep the per-item routes.
ITEMS_PER_SCHOOL = 4

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class _SuperUser(CurrentUser):
    """Superadmin principal that passes every ``require_permission`` gate."""

    def has_permission(self, permission: str) -> bool:  # type: ignore[override]
        return True


def _super_principal() -> _SuperUser:
    return _SuperUser(
        user_id="00000000-0000-0000-0000-000000000000",
        email="golden@insightanalytics.net",
        user_role="super_admin",
        hierarchy_rank=0,
        permissions=[],
        school_ids=list(SCHOOLS.values()),
        primary_school_id=None,
        is_super_admin=True,
    )


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return s[:180] or "root"


def _xlsx_snapshot(content: bytes) -> dict[str, Any]:
    """Serialise an XLSX to {sheet: [[ [value, fill_rgb], ... ], ...]}.

    Compares cell values AND fill colours (the perf-band fills are load-bearing),
    not raw zip bytes (which embed timestamps).
    """
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(content), data_only=False)
    out: dict[str, Any] = {}
    for ws in wb.worksheets:
        rows: list[list[list[Any]]] = []
        for row in ws.iter_rows():
            cells: list[list[Any]] = []
            for c in row:
                fill_rgb: Optional[str] = None
                try:
                    fg = c.fill.fgColor
                    if fg is not None and isinstance(fg.rgb, str):
                        fill_rgb = fg.rgb
                except Exception:
                    fill_rgb = None
                cells.append([c.value, fill_rgb])
            rows.append(cells)
        out[ws.title] = rows
    return out


def _pick(row: dict[str, Any], *names: str) -> Optional[Any]:
    for n in names:
        if n in row and row[n] not in (None, ""):
            return row[n]
    return None


async def _client() -> httpx.AsyncClient:
    app.dependency_overrides[get_current_user] = _super_principal
    # raise_app_exceptions=False so an unhandled 500 is recorded as a response
    # (exactly what uvicorn returns to a real client) rather than propagated —
    # keeps pre/post snapshots stable and comparable.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://harness", timeout=120.0)


async def _capture(
    client: httpx.AsyncClient, out_dir: Path, name: str, path: str, params: dict[str, Any]
) -> None:
    """GET one case and write a canonical snapshot file (JSON or XLSX)."""
    slug = _slug(name)
    try:
        resp = await client.get(path, params=params)
    except Exception as exc:  # noqa: BLE001 — record failures so pre/post diff catches them
        (out_dir / f"{slug}.json").write_text(
            _canon({"__error__": type(exc).__name__, "__msg__": str(exc)})
        )
        return

    ctype = resp.headers.get("content-type", "")
    record: dict[str, Any] = {"__status__": resp.status_code}
    if "spreadsheet" in ctype or XLSX_MEDIA in ctype:
        try:
            record["xlsx"] = _xlsx_snapshot(resp.content)
        except Exception as exc:  # noqa: BLE001
            record["__xlsx_error__"] = f"{type(exc).__name__}: {exc}"
    else:
        try:
            record["json"] = resp.json()
        except Exception:
            record["text"] = resp.text
    (out_dir / f"{slug}.json").write_text(_canon(record))


async def _discover_students(
    client: httpx.AsyncClient, school_id: str, n: int = 3
) -> list[str]:
    """Return up to n student uids for a school (deterministic, sorted)."""
    resp = await client.get(
        "/api/v1/students/browse",
        params={"school_id": school_id, "page": 1, "page_size": 100},
    )
    if resp.status_code != 200:
        return []
    body = resp.json()
    rows = body.get("items") or body.get("rows") or body.get("data") or []
    uids = []
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict):
            uid = _pick(r, "user_uid", "uid", "student_id", "user_id", "id")
            if uid:
                uids.append(str(uid))
    uids = sorted(set(uids))
    return uids[:n]


async def _discover_items(
    client: httpx.AsyncClient, school_id: str
) -> list[dict[str, Any]]:
    """Return up to ITEMS_PER_SCHOOL representative assessment rows for a school.

    Deterministic selection (sorted by item_id) so pre/post pick identical items.
    """
    resp = await client.get(
        "/api/v1/assessments/summary-list",
        params={"school_id": school_id, "page": 1, "page_size": 200},
    )
    if resp.status_code != 200:
        return []
    body = resp.json()
    rows = body.get("items") or body.get("rows") or body.get("data") or []
    if not isinstance(rows, list):
        return []

    def key(r: dict[str, Any]) -> str:
        return str(_pick(r, "item_id", "subject_id", "id") or "")

    rows = [r for r in rows if isinstance(r, dict) and key(r)]
    rows.sort(key=key)
    return rows[:ITEMS_PER_SCHOOL]


# ── Case matrix ──────────────────────────────────────────────────────────────
# Non-item (school-scoped only) GET endpoints — Phase A dashboard family + the
# yearly/summary reports that need no item_id. item-scoped report routes are
# expanded per discovered assessment below.
DIM_ROUTES = [
    "subjects", "grades", "sections", "sessions",
    "assessment-types", "instructors", "standards", "strands",
]

# Per-item report routes: (name, path-template, extra params fn)
ITEM_REPORT_ROUTES = [
    ("qra", "/api/v1/reports/question-response-analysis/{item_id}"),
    ("sdd", "/api/v1/reports/standards-deep-dive/{item_id}"),
    ("qsr_paginated", "/api/v1/reports/question-summary-paginated/{item_id}"),
    ("qra_paginated", "/api/v1/reports/question-response-analysis-paginated/{item_id}"),
    ("qra_by_teacher", "/api/v1/reports/question-response-analysis-by-teacher/{item_id}"),
    ("qra_by_std_teacher",
     "/api/v1/reports/question-response-analysis-by-standard-and-teacher/{item_id}"),
    ("assessment", "/api/v1/assessments/{item_id}"),
    ("assessment_summary", "/api/v1/assessments/{item_id}/summary"),
    ("assessment_questions", "/api/v1/assessments/{item_id}/questions"),
    ("assessment_standards", "/api/v1/assessments/{item_id}/standards"),
    ("assessment_incorrect", "/api/v1/assessments/{item_id}/incorrect-choices"),
]

ITEM_EXPORT_ROUTES = [
    ("qra_xlsx", "/api/v1/reports/question-response-analysis/{item_id}/export.xlsx"),
    ("sdd_xlsx", "/api/v1/reports/standards-deep-dive/{item_id}/export.xlsx"),
    ("qsr_xlsx", "/api/v1/reports/question-summary-paginated/{item_id}/export.xlsx"),
    ("qra_paginated_xlsx",
     "/api/v1/reports/question-response-analysis-paginated/{item_id}/export.xlsx"),
    ("qra_by_teacher_xlsx",
     "/api/v1/reports/question-response-analysis-by-teacher/{item_id}/export.xlsx"),
    ("qra_by_std_teacher_xlsx",
     "/api/v1/reports/question-response-analysis-by-standard-and-teacher/{item_id}/export.xlsx"),
]


async def _capture_school(
    client: httpx.AsyncClient, out_root: Path, school: str, school_id: str
) -> None:
    sdir = out_root / school
    sdir.mkdir(parents=True, exist_ok=True)
    sp = {"school_id": school_id}

    # Dashboard family (Phase A)
    await _capture(client, sdir, "dashboard-overview", "/api/v1/reports/dashboard-overview", sp)
    await _capture(client, sdir, "strand-rows_p1", "/api/v1/reports/strand-rows",
                   {**sp, "page": 1, "page_size": 50})
    await _capture(client, sdir, "standard-summary_cards",
                   "/api/v1/reports/standard-summary", {**sp, "cards_only": "true"})
    await _capture(client, sdir, "summary-list_p1", "/api/v1/assessments/summary-list",
                   {**sp, "page": 1, "page_size": 50})
    await _capture(client, sdir, "summary-list_p2_sorted", "/api/v1/assessments/summary-list",
                   {**sp, "page": 2, "page_size": 25, "sort_by": "item_name", "sort_dir": "asc"})
    await _capture(client, sdir, "students_browse_p1", "/api/v1/students/browse",
                   {**sp, "page": 1, "page_size": 50})
    for d in DIM_ROUTES:
        await _capture(client, sdir, f"dim_{d}", f"/api/v1/dim/{d}", sp)
    await _capture(client, sdir, "schools_accessible", "/api/v1/schools/accessible", {})

    # Yearly / summary reports (school-scoped; YTD needs subject+grade — filled below)
    await _capture(client, sdir, "standard-summary_full",
                   "/api/v1/reports/standard-summary", sp)
    await _capture(client, sdir, "strand-summary_full",
                   "/api/v1/reports/strand-summary", sp)
    await _capture(client, sdir, "data-quality_alignment",
                   "/api/v1/reports/data-quality/standards-alignment", sp)

    # Per-item report routes + one YTD scoped by the item's subject/grade
    items = await _discover_items(client, school_id)
    for idx, row in enumerate(items):
        item_id = _pick(row, "item_id", "subject_id", "id")
        subject = _pick(row, "subject", "subject_name")
        grade = _pick(row, "grade", "grade_level", "grade_band")
        tag = f"item{idx}_{_slug(str(item_id))[:24]}"
        for name, tmpl in ITEM_REPORT_ROUTES:
            await _capture(client, sdir, f"{tag}__{name}",
                           tmpl.format(item_id=item_id), sp)
        for name, tmpl in ITEM_EXPORT_ROUTES:
            await _capture(client, sdir, f"{tag}__{name}",
                           tmpl.format(item_id=item_id), sp)
        # IAD — the only two-param report route (item_id + question_id). Sweep a
        # few question ids; consistent selection makes pre/post comparable even
        # for ids that 404/empty.
        for qid in ("1", "2", "3"):
            await _capture(client, sdir, f"{tag}__iad_q{qid}",
                           f"/api/v1/reports/incorrect-answer-details/{item_id}/{qid}", sp)
            await _capture(client, sdir, f"{tag}__iad_q{qid}_xlsx",
                           f"/api/v1/reports/incorrect-answer-details/{item_id}/{qid}/export.xlsx", sp)
        if subject and grade:
            ytd_p = {**sp, "subject": subject, "grade": grade}
            await _capture(client, sdir, f"{tag}__ytd",
                           "/api/v1/reports/year-to-date-performance", ytd_p)
            await _capture(client, sdir, f"{tag}__ytd_xlsx",
                           "/api/v1/reports/year-to-date-performance/export.xlsx", ytd_p)
            await _capture(client, sdir, f"{tag}__standard-summary_xlsx",
                           "/api/v1/reports/standard-summary/export.xlsx", ytd_p)
            await _capture(client, sdir, f"{tag}__strand-summary_xlsx",
                           "/api/v1/reports/strand-summary/export.xlsx", ytd_p)

    # Per-student reports (Phase B scope)
    for i, uid in enumerate(await _discover_students(client, school_id)):
        await _capture(client, sdir, f"student{i}_{_slug(uid)[:24]}__report",
                       f"/api/v1/students/{uid}/report", sp)


async def _capture_openapi(client: httpx.AsyncClient, out_root: Path) -> None:
    meta = out_root / "_meta"
    meta.mkdir(parents=True, exist_ok=True)
    resp = await client.get("/openapi.json")
    try:
        (meta / "openapi.json").write_text(_canon(resp.json()))
    except Exception:
        (meta / "openapi.json").write_text(_canon({"__status__": resp.status_code}))


async def main_async(out: str, schools: Optional[list[str]]) -> None:
    out_root = Path(out)
    out_root.mkdir(parents=True, exist_ok=True)
    client = await _client()
    try:
        await _capture_openapi(client, out_root)
        targets = schools or list(SCHOOLS.keys())
        for school in targets:
            sid = SCHOOLS[school]
            print(f"[goldens] capturing {school} ({sid})...", flush=True)
            await _capture_school(client, out_root, school, sid)
    finally:
        await client.aclose()
        app.dependency_overrides.pop(get_current_user, None)
    print(f"[goldens] done → {out_root}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Golden-master capture harness")
    ap.add_argument("--out", required=True, help="output dir (scratchpad, not committed)")
    ap.add_argument("--schools", nargs="*", choices=list(SCHOOLS.keys()),
                    help="subset of schools (default: all)")
    args = ap.parse_args()
    asyncio.run(main_async(args.out, args.schools))


if __name__ == "__main__":
    main()
