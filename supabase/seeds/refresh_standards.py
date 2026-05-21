"""Pull a fresh copy of `dim_standard.csv` from Schoology's /standards API.

The seed at `supabase/seeds/dim_standard.csv` was originally exported from
Schoology and has cross-subject corruption in some `description` rows
(see `c1ebebd fix(seeds): patch corrupted descriptions in 4 dim_standard
rows`). This script re-pulls the authoritative dataset and overwrites the
seed CSV in the same column order so `load_standards.py` can re-load it
without changes.

Schoology /standards API
------------------------
Reference: https://developers.schoology.com/api-documentation/rest-api-v1
Auth: OAuth 1.0a two-legged with consumer key/secret OR an admin API token.
The script supports both: prefer the two-legged OAuth pattern matching
the legacy Spark notebook (Schoology_py.ipynb Schoology.fetch_data).

Required environment variables (at least one auth path):
    SCHOOLOGY_BASE_URL          (default https://api.schoology.com/v1)
    SCHOOLOGY_OAUTH_KEY         consumer key  (two-legged OAuth)
    SCHOOLOGY_OAUTH_SECRET      consumer secret
        — OR —
    SCHOOLOGY_API_TOKEN         bearer token (admin)

Usage:
    cd backend  # any cwd works; the script writes to a fixed seed path
    python3 supabase/seeds/refresh_standards.py
    # optional flags
    python3 supabase/seeds/refresh_standards.py --dry-run --limit 500

The script does NOT load the new data into Postgres on its own. After it
finishes, run:
    python3 supabase/seeds/load_standards.py --force

and then rebuild cubes:
    cd backend && ./venv/bin/python -m app.transformations.runner

This file is intentionally standalone — no FastAPI / SQLAlchemy imports.
It only needs `requests` (already pinned via backend/requirements.txt) and
`requests-oauthlib` for the two-legged signing flow.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "`requests` is required. Install via `pip install requests requests-oauthlib`."
    ) from exc

SEEDS_DIR = Path(__file__).parent
DIM_STANDARD_CSV = SEEDS_DIR / "dim_standard.csv"

DEFAULT_BASE_URL = os.environ.get(
    "SCHOOLOGY_BASE_URL", "https://api.schoology.com/v1"
).rstrip("/")

# Output column order — MUST match the existing CSV header so the loader
# (`load_standards.py`) keeps working unchanged.
CSV_COLUMNS = [
    "Cognitive_Complexity_Rating",
    "Direct_Link",
    "Grader",
    "Identifier",
    "Language",
    "Schoology_Standard",
    "Standard_New",
    "Strand",
    "Subject",
    "cPalms_Standard",
    "cluster",
    "description",
    "lastChangeDateTime",
    "rundate",
    "Custom.CleanedDescription",
    "uniquesID",
]


def _build_session() -> requests.Session:
    """Authenticated requests.Session using either OAuth1 or Bearer token."""
    session = requests.Session()

    key = os.environ.get("SCHOOLOGY_OAUTH_KEY")
    secret = os.environ.get("SCHOOLOGY_OAUTH_SECRET")
    token = os.environ.get("SCHOOLOGY_API_TOKEN")

    if key and secret:
        try:
            from requests_oauthlib import OAuth1
        except ImportError as exc:  # pragma: no cover
            raise SystemExit(
                "Two-legged OAuth requires `requests-oauthlib`. "
                "Install via `pip install requests-oauthlib`."
            ) from exc
        # Schoology's two-legged flow: empty resource_owner_key/secret
        # and signature_method='PLAINTEXT' — see legacy notebook
        # Schoology.fetch_data implementation.
        session.auth = OAuth1(
            client_key=key,
            client_secret=secret,
            signature_method="PLAINTEXT",
        )
        session.headers.update({"Accept": "application/json"})
        return session

    if token:
        session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
        )
        return session

    raise SystemExit(
        "No Schoology credentials found. Set either "
        "SCHOOLOGY_OAUTH_KEY + SCHOOLOGY_OAUTH_SECRET (preferred) or "
        "SCHOOLOGY_API_TOKEN before running."
    )


def _fetch_page(
    session: requests.Session, url: str, start: int = 0, limit: int = 200
) -> dict[str, Any]:
    """One paginated GET. Schoology paginates via `start` + `limit`."""
    params = {"start": start, "limit": limit}
    r = session.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_all_standards(
    base_url: str, total_limit: int | None = None, dry_run: bool = False
) -> list[dict[str, Any]]:
    """Walk /standards with pagination. Returns the full list of raw JSON rows."""
    session = _build_session()
    url = f"{base_url}/standards"

    rows: list[dict[str, Any]] = []
    start = 0
    page_size = 200
    pages = 0

    while True:
        data = _fetch_page(session, url, start=start, limit=page_size)
        # Schoology paginated responses typically nest under `standard` or
        # under the resource name; handle both.
        page_rows: list[dict[str, Any]] = (
            data.get("standard")
            or data.get("standards")
            or data.get("items")
            or []
        )
        if not page_rows:
            break

        rows.extend(page_rows)
        pages += 1
        print(f"  page {pages}: +{len(page_rows)} rows  (total {len(rows)})")

        if total_limit and len(rows) >= total_limit:
            rows = rows[:total_limit]
            break

        # Stop when fewer than a full page returned, or when paginated
        # navigation hints exhaustion.
        if len(page_rows) < page_size:
            break

        start += page_size
        time.sleep(0.1)  # polite throttle

        if dry_run and pages >= 1:
            print("  --dry-run: stopping after 1 page")
            break

    return rows


def _coerce(row: dict[str, Any]) -> dict[str, str]:
    """Map one Schoology JSON row into the CSV-column flat shape.

    Schoology /standards returns fields like:
      identifier, language, schoology_standard, cpalms_standard, cluster,
      description, lastChangeDateTime, strand, subject, …
    Some keys differ by capitalization; we look up both spellings.
    """

    def pick(*candidates: str) -> str:
        for key in candidates:
            if key in row and row[key] is not None:
                return str(row[key])
        return ""

    return {
        "Cognitive_Complexity_Rating": pick(
            "cognitive_complexity_rating", "Cognitive_Complexity_Rating"
        ),
        "Direct_Link": pick("direct_link", "Direct_Link"),
        "Grader": pick("grader", "Grader"),
        "Identifier": pick("identifier", "Identifier"),
        "Language": pick("language", "Language"),
        "Schoology_Standard": pick("schoology_standard", "Schoology_Standard"),
        "Standard_New": pick("standard_new", "Standard_New"),
        "Strand": pick("strand", "Strand"),
        "Subject": pick("subject", "Subject"),
        "cPalms_Standard": pick("cpalms_standard", "cPalms_Standard"),
        "cluster": pick("cluster", "Cluster"),
        # `\r\n` -> ' ' to mirror the legacy notebook (Schoology_py.ipynb line 191).
        "description": pick("description", "Description").replace("\r\n", " "),
        "lastChangeDateTime": pick("lastChangeDateTime", "last_change_date_time"),
        "rundate": time.strftime("%Y-%m-%d"),
        "Custom.CleanedDescription": pick(
            "custom_cleaned_description", "Custom.CleanedDescription"
        ),
        "uniquesID": pick("uniquesID", "uniques_id")
        or f"{pick('identifier')}_{pick('schoology_standard')}",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Refresh dim_standard.csv from Schoology.")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap total rows fetched (useful for dry runs).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch only one page and print stats; do not overwrite the CSV.",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=DIM_STANDARD_CSV,
        help=f"Output CSV (default: {DIM_STANDARD_CSV}).",
    )
    args = p.parse_args()

    print(f"Fetching from {args.base_url}/standards ...")
    raw = fetch_all_standards(args.base_url, total_limit=args.limit, dry_run=args.dry_run)
    print(f"Fetched {len(raw)} raw standards rows.")

    if args.dry_run:
        sample = raw[:3]
        print("--dry-run sample (first 3 raw rows):")
        for s in sample:
            print(" ", {k: s.get(k) for k in list(s)[:6]})
        return 0

    coerced = [_coerce(r) for r in raw]
    print(f"Coerced to CSV shape: {len(coerced)} rows.")

    backup = args.out.with_suffix(".csv.bak")
    if args.out.exists():
        args.out.replace(backup)
        print(f"Backed up old seed to {backup.name}.")

    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_MINIMAL
        )
        writer.writeheader()
        writer.writerows(coerced)

    print(f"Wrote {args.out} ({len(coerced)} rows + header).")
    print("\nNext steps:")
    print("  1. Inspect the diff:  git diff supabase/seeds/dim_standard.csv")
    print("  2. Reload into local DB:")
    print("       python3 supabase/seeds/load_standards.py --force")
    print("  3. Rebuild cubes:")
    print("       cd backend && ./venv/bin/python -m app.transformations.runner")
    print("  4. If happy, commit; if not, restore the backup:")
    print(f"       mv supabase/seeds/dim_standard.csv.bak supabase/seeds/dim_standard.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
