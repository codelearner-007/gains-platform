#!/usr/bin/env python3
"""Rewrite ``dim_standard.direct_link`` to the human-readable CPALMS standard page.

Background
----------
``refresh_standards.py`` seeds ``dim_standard.direct_link`` with the *CFDocument*
IMS/CASE JSON URI (``…/ims/case/v1p0/CFDocuments/<doc>.json``) — a machine API
shared by *every* standard in a framework. So clicking a standard in a report
opened raw JSON, not a web page (and not even the specific standard).

CPALMS exposes **no** HTML page addressable by the human code or the CASE guid;
the real page is keyed by CPALMS's internal NUMERIC id:

    https://www.cpalms.org/PreviewStandard/Preview/<id>

That id is resolved once per standard from its code via the anonymous endpoint

    https://www.cpalms.org/Search/GetSearchStandard?KeyWord=<code>

whose HTML contains ``PreviewSliderDetail('StandardDetail', '<id>', …)`` and a
card title equal to the canonical code. Aliased Schoology codes (``AI.…``,
``SCI.8.…``) don't match CPALMS search, so we fall back to the CFItem's canonical
``humanCodingScheme`` (fetched by guid).

What this does
--------------
Resolves the id for every standard **referenced by fact data** (default) or for
**all** standards (``--all``) and rewrites ``direct_link`` in place to the Preview
URL. Codes it cannot resolve are set to ``NULL`` (the report then renders the code
as plain text). Prior values are snapshotted to ``dim_standard_directlink_bak``
before the first change, so it is idempotent and reversible.

Usage
-----
    python resolve_cpalms_links.py [--all] [--dry-run] [--limit N] [--workers 8]
    DATABASE_URL=postgresql://…      # defaults to local dev (56322)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

DEV_DB = "postgresql://postgres:postgres@127.0.0.1:56322/postgres"
PREVIEW = "https://www.cpalms.org/PreviewStandard/Preview/{id}"
SEARCH = "https://www.cpalms.org/Search/GetSearchStandard?KeyWord={kw}"
CFITEM = "https://www.cpalms.org/Public/ims/case/v1p0/CFItems/{guid}.json"

_ID_RE = re.compile(r"PreviewSliderDetail\(\s*'StandardDetail'\s*,\s*'(\d+)'")
_TITLE_RE = re.compile(r'card-title[^>]*>\s*([A-Za-z0-9.\-]+)\s*<')
_HCS_RE = re.compile(r'"humanCodingScheme"\s*:\s*"([^"]+)"')

_print_lock = threading.Lock()


def _curl(url: str, timeout: int = 20, retries: int = 2) -> Optional[str]:
    """GET a URL via curl (system Python's SSL store is unreliable on macOS)."""
    for attempt in range(retries + 1):
        try:
            out = subprocess.run(
                ["curl", "-s", "--fail", "--max-time", str(timeout), url],
                capture_output=True,
                timeout=timeout + 5,
            )
            if out.returncode == 0 and out.stdout:
                return out.stdout.decode("utf-8", "ignore")
        except subprocess.TimeoutExpired:
            pass
        if attempt < retries:
            time.sleep(0.4 * (attempt + 1))
    return None


def _search_id(code: str) -> Optional[str]:
    """Resolve a *canonical* code to its CPALMS numeric id (title must match)."""
    html = _curl(SEARCH.format(kw=urllib.parse.quote(code)))
    if not html:
        return None
    ids = _ID_RE.findall(html)
    titles = _TITLE_RE.findall(html)
    if not ids:
        return None
    # Prefer the card whose title equals the code; else the sole result.
    for i, title in zip(ids, titles):
        if title.strip().upper() == code.strip().upper():
            return i
    return ids[0] if len(ids) == 1 else None


def _canonical(guid: str) -> Optional[str]:
    """Authoritative canonical code for a standard = CFItem.humanCodingScheme."""
    js = _curl(CFITEM.format(guid=guid))
    if not js:
        return None
    m = _HCS_RE.search(js)
    return m.group(1) if m else None


# ── resolution (thread-safe id cache keyed by code) ─────────────────────────
_cache: Dict[str, Optional[str]] = {}
_cache_lock = threading.Lock()


def _cached_search(code: str) -> Optional[str]:
    with _cache_lock:
        if code in _cache:
            return _cache[code]
    val = _search_id(code)
    with _cache_lock:
        _cache[code] = val
    return val


def resolve_one(guid: str, codes: List[str]) -> Optional[str]:
    """Return the Preview URL for a standard, or None if unresolvable.

    Tries each display code first (covers the ~85% non-aliased), then falls back
    to the CFItem's canonical humanCodingScheme for aliased Schoology codes.
    """
    for code in codes:
        sid = _cached_search(code)
        if sid:
            return PREVIEW.format(id=sid)
    canon = _canonical(guid)
    if canon and canon not in codes:
        sid = _cached_search(canon)
        if sid:
            return PREVIEW.format(id=sid)
    return None


# ── DB helpers (psql subprocess — no driver dependency) ─────────────────────
def _psql(db: str, sql: str, tuples_only: bool = True) -> str:
    args = ["psql", db, "-v", "ON_ERROR_STOP=1"]
    if tuples_only:
        args += ["-tA", "-F", "\t"]
    args += ["-c", sql]
    out = subprocess.run(args, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"psql failed:\n{out.stderr}")
    return out.stdout


def load_targets(db: str, scope_all: bool, limit: Optional[int]) -> Dict[str, List[str]]:
    """Return {identifier: [display codes]} for the chosen scope."""
    where_ref = (
        "" if scope_all
        else "WHERE EXISTS (SELECT 1 FROM fact_student_submission f "
             "WHERE f.identifier = d.identifier AND f.identifier <> '')"
    )
    sql = (
        "SELECT d.identifier, d.schoology_standard FROM dim_standard d "
        f"{where_ref} "
        "AND d.identifier IS NOT NULL AND d.identifier <> '' "
        if where_ref
        else "SELECT d.identifier, d.schoology_standard FROM dim_standard d "
             "WHERE d.identifier IS NOT NULL AND d.identifier <> '' "
    )
    rows = _psql(db, sql.strip())
    by_guid: Dict[str, List[str]] = {}
    for line in rows.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        guid = parts[0].strip()
        code = (parts[1] if len(parts) > 1 else "").strip()
        if not guid:
            continue
        codes = by_guid.setdefault(guid, [])
        if code and code not in codes:
            codes.append(code)
    if limit:
        by_guid = dict(list(by_guid.items())[:limit])
    return by_guid


def _sql_literal(v: Optional[str]) -> str:
    if v is None:
        return "NULL"
    return "'" + v.replace("'", "''") + "'"


def apply_updates(db: str, resolved: Dict[str, Optional[str]]) -> None:
    """Snapshot prior values once, then rewrite direct_link transactionally."""
    guids = list(resolved.keys())
    values = ",\n".join(
        f"({_sql_literal(g)}, {_sql_literal(url)})" for g, url in resolved.items()
    )
    guid_list = ",".join(_sql_literal(g) for g in guids)
    script = f"""
BEGIN;
CREATE TABLE IF NOT EXISTS dim_standard_directlink_bak (
    identifier text,
    direct_link text,
    backed_up_at timestamptz DEFAULT now()
);
-- snapshot the ORIGINAL value once (never overwrite on re-run)
INSERT INTO dim_standard_directlink_bak (identifier, direct_link)
SELECT DISTINCT d.identifier, d.direct_link
FROM dim_standard d
WHERE d.identifier IN ({guid_list})
  AND NOT EXISTS (SELECT 1 FROM dim_standard_directlink_bak b WHERE b.identifier = d.identifier);
UPDATE dim_standard d
SET direct_link = v.url
FROM (VALUES
{values}
) AS v(identifier, url)
WHERE d.identifier = v.identifier;
COMMIT;
"""
    _psql(db, script, tuples_only=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="resolve every standard, not just fact-referenced")
    ap.add_argument("--dry-run", action="store_true", help="resolve + report, do NOT write the DB")
    ap.add_argument("--limit", type=int, default=None, help="cap number of standards (testing)")
    ap.add_argument("--workers", type=int, default=8, help="concurrent resolvers")
    args = ap.parse_args()

    db = os.environ.get("DATABASE_URL", DEV_DB)
    redacted = re.sub(r"//[^@]+@", "//***@", db)
    print(f"DB: {redacted}   scope: {'ALL' if args.all else 'fact-referenced'}"
          f"{'   [DRY RUN]' if args.dry_run else ''}")

    targets = load_targets(db, args.all, args.limit)
    print(f"standards to resolve: {len(targets)}")
    if not targets:
        return

    resolved: Dict[str, Optional[str]] = {}
    done = 0
    t0 = time.time()

    def _work(item: Tuple[str, List[str]]) -> Tuple[str, Optional[str]]:
        guid, codes = item
        return guid, resolve_one(guid, codes)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for guid, url in ex.map(_work, targets.items()):
            resolved[guid] = url
            done += 1
            if done % 100 == 0:
                ok = sum(1 for v in resolved.values() if v)
                with _print_lock:
                    print(f"  {done}/{len(targets)}  resolved={ok}  ({time.time()-t0:.0f}s)")

    ok = {g: u for g, u in resolved.items() if u}
    miss = [g for g, u in resolved.items() if not u]
    print(f"\nresolved {len(ok)}/{len(targets)}  ({len(miss)} unresolved → will be NULL)")
    # show a few samples
    for g, u in list(ok.items())[:5]:
        print(f"  {g}  {targets[g]}  ->  {u}")
    if miss[:5]:
        print("  unresolved examples:", [targets[g] for g in miss[:5]])

    if args.dry_run:
        print("\n[dry-run] no DB changes written.")
        return

    apply_updates(db, resolved)
    print(f"\n✓ dim_standard.direct_link rewritten "
          f"({len(ok)} Preview URLs, {len(miss)} set NULL). "
          f"Prior values snapshotted to dim_standard_directlink_bak.")


if __name__ == "__main__":
    main()
