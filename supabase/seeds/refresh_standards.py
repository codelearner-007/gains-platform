"""Refresh `supabase/seeds/dim_standard.csv` from IMS Global CASE Network.

Mirrors the EdvanceLearning `K12StandardsImport` Blazor pipeline 1:1 but
skips the LMS DB round-trip — pulls directly from 1EdTech's CASE Network
hub and emits the CSV the seed loader expects.

Audit references (legacy → mirror):
  - docs/audit/legacy-standards-refresh.md (legacy refresh process)
  - docs/audit/edvancelearning-ims-integration.md (the integration we mirror)
  - Legacy code:
      /Users/mac/Desktop/PS_P/gains legacy/EdvanceLearning/services/lms/
        host/EdvanceLS.LMS.HttpApi.Host/appsettings.json:9-14
        src/EdvanceLS.LMS.Application/.../RemoteCaseNetworkStandards.cs:75-96
          (loop over CFDocuments)
        src/EdvanceLS.LMS.Application/.../RemoteCaseNetworkStandards.cs:615-681
          (ImsCaseNetworkApiCall — OAuth2 + GET pattern we mirror)
        src/EdvanceLS.LMS.Application/.../LocalCaseNetworkStandards.cs:198-262
          (tree-walking semantics)
      /Users/mac/Desktop/PS_P/gains legacy/OEA/modules/module_catalog/EdvanceLS/
        notebook/Standards/Standards_py.ipynb (legacy column extraction we
        mirror in `_make_row`).

IMS endpoints (verbatim from legacy `appsettings.json`):
  Token : POST https://casenetwork.1edtech.org/case-oauth2/clienttoken
  List  : GET  {base}/CFDocuments          → list of {identifier, title, uri, ...}
  Bundle: GET  {base}/CFPackages/{id}      → full pkg with CFItems +
                                              CFAssociations + CFDefinitions
  Base default: https://casenetwork.1edtech.org/ims/case/v1p1/

Authentication mirrors legacy verbatim:
  - HTTP Basic auth header on the token endpoint:
      Authorization: Basic base64(client_id ":" client_secret)
  - Form body: grant_type=client_credentials
  - Resource endpoint receives:
      Authorization: Bearer <token>

Three legacy bugs we deliberately do NOT mirror:
  1. Token cached for `expires_in` seconds instead of refetched per call.
  2. Retry with exponential backoff on token + resource GETs.
  3. Atomic CSV write (temp file + os.replace) instead of in-place overwrite.

Usage:
  export IMS_CASE_CLIENT_ID=<your 1EdTech CASE Network client id>
  export IMS_CASE_CLIENT_SECRET=<secret>
  python3 supabase/seeds/refresh_standards.py            # full refresh
  python3 supabase/seeds/refresh_standards.py --dry-run  # preview, no write
  python3 supabase/seeds/refresh_standards.py \
      --documents <cfdoc-uuid1>,<cfdoc-uuid2>            # subset

After a successful run:
  python3 supabase/seeds/load_standards.py --force
  cd backend && ./venv/bin/python -m app.transformations.runner

This script only needs `requests` from PyPI; everything else is stdlib.
"""

from __future__ import annotations

import argparse
import base64
import csv
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import requests
    from requests.exceptions import RequestException
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "`requests` is required. Install via `pip install requests`."
    ) from exc


# ─── Constants ─────────────────────────────────────────────────────────────

# CSV header order — MUST match the existing `dim_standard.csv` so
# `load_standards.py` keeps working unchanged.
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

# Default base: Florida CPALMS hub (anonymous, no auth required). This is
# the upstream-of-upstream — 1EdTech's CASE Network republishes the same
# documents from here. We use CPALMS directly to skip auth complexity and
# because our seed actually came from FLDOE-published standards.
DEFAULT_BASE_URL = "https://www.cpalms.org/Public/ims/case/v1p0/"
# 1EdTech's CASE Network hub. Requires OAuth2 client_credentials.
# Kept as opt-in via --base-url + --token-url / IMS_CASE_* env vars; used
# by EdvanceLearning's legacy K12StandardsImport pipeline.
ONEEDTECH_BASE_URL = "https://casenetwork.1edtech.org/ims/case/v1p1/"
DEFAULT_TOKEN_URL = "https://casenetwork.1edtech.org/case-oauth2/clienttoken"

SEEDS_DIR = Path(__file__).parent
DEFAULT_OUTPUT = SEEDS_DIR / "dim_standard.csv"

HTTP_TIMEOUT_SECONDS = 30
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 1.5  # exponential base

logger = logging.getLogger("refresh_standards")


# ─── HTTP / auth ───────────────────────────────────────────────────────────


@dataclass
class _TokenCache:
    """Cached OAuth2 access token. Refresh when it's about to expire."""

    access_token: str
    expires_at: float  # unix-seconds


def _get_token(
    token_url: str,
    client_id: str,
    client_secret: str,
    cache: _TokenCache | None,
) -> _TokenCache:
    """OAuth2 client_credentials via HTTP Basic + form body.

    Mirrors `RemoteCaseNetworkStandards.cs:619-651` exactly, with one
    deliberate divergence: we cache the bearer token for its declared
    expires_in lifetime (minus a 30s safety margin) instead of fetching
    a new one on every resource call. Legacy fetches per call which is
    wasteful and easy to rate-limit; the spec gives us `expires_in` so
    we should honour it.
    """
    if cache is not None and cache.expires_at > time.time() + 30:
        return cache

    credentials = f"{client_id}:{client_secret}".encode("utf-8")
    basic = base64.b64encode(credentials).decode("ascii")
    headers = {
        "Authorization": f"Basic {basic}",
        "Accept": "application/json",
    }
    body = {"grant_type": "client_credentials"}

    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(
                token_url, headers=headers, data=body, timeout=HTTP_TIMEOUT_SECONDS
            )
            if r.status_code == 200:
                payload = r.json()
                token = payload.get("access_token")
                expires_in = int(payload.get("expires_in") or 3600)
                if not token:
                    raise RuntimeError(
                        f"Token endpoint returned 200 but no access_token: {payload!r}"
                    )
                return _TokenCache(
                    access_token=token,
                    expires_at=time.time() + expires_in,
                )
            # Honour Retry-After if provided.
            retry_after = r.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                sleep_s = int(retry_after)
            else:
                sleep_s = RETRY_BACKOFF_SECONDS ** attempt
            last_err = RuntimeError(
                f"Token request failed (status {r.status_code}): {r.text[:200]}"
            )
            logger.warning(
                "Token request attempt %d/%d failed (%d). Sleeping %.1fs.",
                attempt + 1,
                MAX_RETRIES,
                r.status_code,
                sleep_s,
            )
            time.sleep(sleep_s)
        except RequestException as exc:
            last_err = exc
            logger.warning(
                "Token request attempt %d/%d network error: %s",
                attempt + 1,
                MAX_RETRIES,
                exc,
            )
            time.sleep(RETRY_BACKOFF_SECONDS ** attempt)

    raise RuntimeError(
        f"Failed to obtain IMS access token after {MAX_RETRIES} attempts: {last_err}"
    )


def _fetch_json(
    url: str,
    token: str | None,
    label: str,
) -> Any:
    """GET a resource (optionally with bearer token), retry/backoff. Returns parsed JSON.

    Mirrors `ImsCaseNetworkApiCall` second leg
    (`httpClient.GetAsync(caseNetworkApiEndpoint)`) but with retry that
    legacy lacks. When `token` is None we send no Authorization header —
    used for anonymous-access hubs like CPALMS.
    """
    headers: dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
            if r.status_code == 200:
                return r.json()
            # 401 means our token expired earlier than `expires_in` claimed.
            # Surface as a clear error so caller can re-auth and retry.
            if r.status_code == 401:
                raise PermissionError(
                    f"401 Unauthorized on {label}. Token likely expired; "
                    "caller should re-auth and retry."
                )
            retry_after = r.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                sleep_s = int(retry_after)
            else:
                sleep_s = RETRY_BACKOFF_SECONDS ** attempt
            last_err = RuntimeError(
                f"{label} returned {r.status_code}: {r.text[:200]}"
            )
            logger.warning(
                "%s attempt %d/%d failed (%d). Sleeping %.1fs.",
                label,
                attempt + 1,
                MAX_RETRIES,
                r.status_code,
                sleep_s,
            )
            time.sleep(sleep_s)
        except RequestException as exc:
            last_err = exc
            logger.warning(
                "%s attempt %d/%d network error: %s",
                label,
                attempt + 1,
                MAX_RETRIES,
                exc,
            )
            time.sleep(RETRY_BACKOFF_SECONDS ** attempt)

    raise RuntimeError(
        f"Failed to fetch {label} after {MAX_RETRIES} attempts: {last_err}"
    )


# ─── IMS resource fetchers ─────────────────────────────────────────────────


def fetch_documents(base_url: str, token: str) -> list[dict[str, Any]]:
    """GET {base}/CFDocuments → flat list of CFDocument summaries.

    Mirrors `RemoteCaseNetworkStandards.GetAllCFDocuments` (line 428). The
    CASE 1.0 spec returns a `{ "CFDocuments": [...] }` wrapper; 1EdTech's
    hub sometimes returns just the array — handle both.
    """
    url = f"{base_url.rstrip('/')}/CFDocuments"
    payload = _fetch_json(url, token, "CFDocuments")
    if isinstance(payload, dict):
        return list(payload.get("CFDocuments") or payload.get("cfDocuments") or [])
    if isinstance(payload, list):
        return list(payload)
    raise RuntimeError(f"Unexpected CFDocuments payload shape: {type(payload)}")


def fetch_package(
    base_url: str,
    token: str | None,
    document: dict[str, Any],
) -> dict[str, Any]:
    """Fetch the full CFPackage bundle for one CFDocument.

    Mirrors `RemoteCaseNetworkStandards.GetCFPackage` (line 599). The
    returned CFPackage inlines CFDocument, CFItems[], CFAssociations[],
    CFRubrics[], and CFDefinitions — one call gives us everything needed
    to reconstruct the standards tree.

    Two URL conventions exist:
      * 1EdTech: `{base}/CFPackages/{document.identifier}` (same id as
        the CFDocument).
      * CPALMS:  the CFPackage has its OWN identifier, exposed by the
        CFDocument under `CFPackageURI.uri`. We prefer this URI when
        present because it always works on both vendors.
    """
    pkg_uri = (document.get("CFPackageURI") or {}).get("uri")
    doc_id = (document.get("identifier") or "").lower()
    label = f"CFPackage for {doc_id}"
    if pkg_uri:
        return _fetch_json(pkg_uri, token, label)
    url = f"{base_url.rstrip('/')}/CFPackages/{doc_id}"
    return _fetch_json(url, token, label)


# ─── Tree walking ──────────────────────────────────────────────────────────


def _norm_key(d: dict[str, Any] | None, *keys: str) -> Any:
    """Pick the first present key from a dict (case-insensitive helper).

    The CASE spec is case-sensitive but real-world payloads occasionally
    differ in capitalisation between vendors (e.g. `humanCodingScheme`
    vs `HumanCodingScheme`). Try each candidate; return the first hit.
    """
    if not d:
        return None
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _items_by_id(package: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index CFPackage.CFItems[] by identifier (lowercased)."""
    items = package.get("CFItems") or package.get("cfItems") or []
    return {(it.get("identifier") or "").lower(): it for it in items if it.get("identifier")}


def _children_map(
    package: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Build parent_id → [origin_node_uri, ...] from CFAssociations.

    CASE associations point CHILD → PARENT
    (`originNodeURI` is the child; `destinationNodeURI` is the parent).
    We invert so we can walk PARENT → CHILDREN from the document root,
    matching `LocalCaseNetworkStandards.k12PackageChild` /
    `k12PackageSubChild`.

    We filter to `associationType in {"isChildOf", "child"}` — that's the
    only direction relevant to the grade → strand → cluster → standard
    tree.  Other association types (exemplifies, relates, …) carry
    cross-framework links we don't render.
    """
    children: dict[str, list[dict[str, Any]]] = {}
    associations = (
        package.get("CFAssociations") or package.get("cfAssociations") or []
    )
    for a in associations:
        atype = (a.get("associationType") or "").strip().lower()
        if atype not in ("ischildof", "child", "is_child_of"):
            continue
        dest = a.get("destinationNodeURI") or {}
        origin = a.get("originNodeURI") or {}
        parent_id = (dest.get("identifier") or "").lower()
        if not parent_id or not origin.get("identifier"):
            continue
        children.setdefault(parent_id, []).append(origin)
    return children


def _norm_subject(value: Any) -> str:
    """`CFDocument.subject` is a `List<string>` in legacy. Take first entry."""
    if isinstance(value, list):
        return str(value[0]) if value else ""
    if value is None:
        return ""
    return str(value)


def _make_row(
    document: dict[str, Any],
    cf_item: dict[str, Any],
    grader: str,
    strand: str,
    cluster: str,
    rundate: str,
) -> dict[str, str]:
    """Build one `dim_standard.csv` row from a leaf CFItem + its ancestors.

    Column derivations mirror `Standards_py.load_standard()` (legacy
    notebook). See `docs/audit/edvancelearning-ims-integration.md` §11
    for the verbatim mapping table.
    """
    coding = (_norm_key(cf_item, "humanCodingScheme", "HumanCodingScheme") or "")
    parts = coding.split(".")
    identifier_raw = _norm_key(cf_item, "identifier", "Identifier") or ""
    identifier = str(identifier_raw).lower()
    language_raw = _norm_key(cf_item, "language", "Language") or ""
    language = str(language_raw).lower()

    cpalms = ".".join(parts[2:]) if len(parts) > 2 else coding
    standard_new = ".".join(parts[4:]) if len(parts) > 4 else ""

    full_statement = (
        _norm_key(cf_item, "fullStatement", "FullStatement") or ""
    )
    last_change = (
        _norm_key(cf_item, "lastChangeDateTime", "LastChangeDateTime") or ""
    )
    document_uri = _norm_key(document, "uri", "URI", "Uri") or ""
    subject = _norm_subject(_norm_key(document, "subject", "Subject"))

    return {
        # Hardcoded by legacy — not in IMS payload.
        "Cognitive_Complexity_Rating": "",
        # CFDocument-level URI (all standards in a framework share one).
        "Direct_Link": str(document_uri),
        "Grader": grader,
        "Identifier": identifier,
        "Language": language,
        # Misnamed for legacy compat. Actually CFItem.humanCodingScheme.
        "Schoology_Standard": str(coding),
        "Standard_New": standard_new,
        "Strand": strand,
        "Subject": subject,
        "cPalms_Standard": cpalms,
        "cluster": cluster,
        # Raw HTML preserved here (legacy does too); the QRA cube
        # `cube_question_summary_overall` strips tags before serving.
        "description": str(full_statement),
        "lastChangeDateTime": str(last_change),
        "rundate": rundate,
        # Downstream Synapse Schoology preprocess creates this field by
        # cleaning `description`. We mirror by copying as-is; if the cube
        # ever needs a distinct value we can add a strip step.
        "Custom.CleanedDescription": str(full_statement),
        "uniquesID": f"{identifier}_{coding}",
    }


def walk_package_to_rows(
    package: dict[str, Any], rundate: str
) -> list[dict[str, str]]:
    """Walk one CFPackage into the 4-level standards tree → CSV rows.

    Tree depth (per legacy `LocalCaseNetworkStandards.k12PackageChild`):
      level 0 = CFDocument (root)
      level 1 = Grade nodes        → Grader
      level 2 = Strand nodes       → Strand
      level 3 = Cluster nodes      → cluster
      level 4 = Standard nodes     → row (leaf)

    Some frameworks have fewer / more levels. We emit a row at any leaf
    in the (level >= 1) subtree and label whichever ancestor levels are
    present; missing ancestors render as empty string (matches
    `LocalCaseNetworkStandards.cs:206-211` behaviour where parent
    description was always null).
    """
    document = _norm_key(package, "CFDocument", "cfDocument") or {}
    if not document.get("identifier"):
        logger.warning("CFPackage missing CFDocument.identifier; skipping.")
        return []

    children = _children_map(package)
    items = _items_by_id(package)
    root_id = (document.get("identifier") or "").lower()

    rows: list[dict[str, str]] = []
    # We descend the tree iteratively, carrying the (grader, strand,
    # cluster) labels of the most recent ancestors at depths 1/2/3.
    # When we reach a leaf (no children), we emit a row.
    stack: list[tuple[str, int, str, str, str]] = [(root_id, 0, "", "", "")]
    while stack:
        node_id, depth, grader, strand, cluster = stack.pop()
        kids = children.get(node_id, [])
        if not kids:
            # Leaf — emit a row IFF the corresponding CFItem exists.
            # Skip the document root itself (depth 0).
            if depth == 0:
                continue
            cf_item = items.get(node_id)
            if not cf_item:
                continue
            rows.append(
                _make_row(
                    document=document,
                    cf_item=cf_item,
                    grader=grader,
                    strand=strand,
                    cluster=cluster,
                    rundate=rundate,
                )
            )
            continue
        for kid in kids:
            kid_id = (kid.get("identifier") or "").lower()
            kid_title = str(kid.get("title") or "")
            if not kid_id:
                continue
            next_depth = depth + 1
            if next_depth == 1:
                next_grader = kid_title
                next_strand = ""
                next_cluster = ""
            elif next_depth == 2:
                next_grader = grader
                next_strand = kid_title
                next_cluster = ""
            elif next_depth == 3:
                next_grader = grader
                next_strand = strand
                next_cluster = kid_title
            else:
                next_grader, next_strand, next_cluster = grader, strand, cluster
            stack.append(
                (kid_id, next_depth, next_grader, next_strand, next_cluster)
            )

    return rows


# ─── CSV writer ────────────────────────────────────────────────────────────


def write_csv(rows: Iterable[dict[str, str]], output_path: Path) -> int:
    """Atomically overwrite `output_path` with a `dim_standard.csv`.

    Backs up the existing file to `<name>.csv.bak`, writes to a `.tmp`
    sibling, then `os.replace`s into place. Safe under abrupt termination —
    either the old or the new file is always present, never a partial.
    """
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    bak_path = output_path.with_suffix(output_path.suffix + ".bak")

    count = 0
    with tmp_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_MINIMAL
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1

    if output_path.exists():
        shutil.copy2(output_path, bak_path)
        logger.info("Backed up existing seed → %s", bak_path.name)

    os.replace(tmp_path, output_path)
    return count


# ─── CLI ───────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh supabase/seeds/dim_standard.csv from IMS Global "
            "CASE Network (1EdTech)."
        )
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("IMS_CASE_BASE_URL", DEFAULT_BASE_URL),
        help=f"CASE Network base URL (default {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--token-url",
        default=os.environ.get("IMS_CASE_TOKEN_URL", DEFAULT_TOKEN_URL),
        help=f"OAuth2 token URL (default {DEFAULT_TOKEN_URL}).",
    )
    parser.add_argument(
        "--client-id",
        default=os.environ.get("IMS_CASE_CLIENT_ID"),
        help=(
            "OAuth2 client id (env IMS_CASE_CLIENT_ID). Only required for "
            "1EdTech's hub; CPALMS allows anonymous access."
        ),
    )
    parser.add_argument(
        "--client-secret",
        default=os.environ.get("IMS_CASE_CLIENT_SECRET"),
        help=(
            "OAuth2 client secret (env IMS_CASE_CLIENT_SECRET). Only required "
            "for 1EdTech's hub."
        ),
    )
    parser.add_argument(
        "--documents",
        default=os.environ.get("IMS_CASE_DOCUMENT_IDS", "all"),
        help=(
            "Comma-separated CFDocument identifiers to import, or 'all' "
            "(default 'all'). Mirrors the Blazor admin UI checkbox grid."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output CSV path (default {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and walk, but do not overwrite the CSV. Prints row count + sample.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="DEBUG-level logging.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    rundate = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info("rundate = %s", rundate)

    # Auth is optional — CPALMS and other public CASE hubs serve
    # CFDocuments / CFPackages anonymously. 1EdTech requires OAuth2.
    token_cache: _TokenCache | None = None
    has_creds = bool(args.client_id and args.client_secret)
    if has_creds:
        logger.info("Resolving OAuth2 token from %s ...", args.token_url)
        token_cache = _get_token(
            args.token_url, args.client_id, args.client_secret, None
        )
        logger.info(
            "Got token. Expires in ~%ds.",
            int(token_cache.expires_at - time.time()),
        )
    else:
        logger.info("No client credentials — using anonymous (CPALMS-style) access.")

    bearer = token_cache.access_token if token_cache else None
    logger.info("Listing CFDocuments from %s ...", args.base_url)
    docs = fetch_documents(args.base_url, bearer)
    logger.info("Discovered %d CFDocuments.", len(docs))

    if args.documents.lower().strip() == "all":
        wanted = [(d.get("identifier") or "").lower() for d in docs]
        wanted = [w for w in wanted if w]
    else:
        wanted = [s.strip().lower() for s in args.documents.split(",") if s.strip()]
    logger.info("Will import %d CFDocument(s).", len(wanted))

    # Index documents by identifier for fast lookup; we need the
    # CFPackageURI from each document to fetch its bundle on CPALMS.
    docs_by_id = {(d.get("identifier") or "").lower(): d for d in docs}

    all_rows: list[dict[str, str]] = []
    for i, doc_id in enumerate(wanted, start=1):
        doc = docs_by_id.get(doc_id)
        if not doc:
            logger.warning("[%d/%d] CFDocument %s not in catalog — skipping.", i, len(wanted), doc_id)
            continue
        logger.info("[%d/%d] Fetching CFPackage for %s (%s)...", i, len(wanted), doc_id, doc.get("title", "")[:60])

        # Refresh token if needed (handles longer batches gracefully).
        if has_creds:
            token_cache = _get_token(
                args.token_url, args.client_id, args.client_secret, token_cache
            )
            bearer = token_cache.access_token

        try:
            pkg = fetch_package(args.base_url, bearer, doc)
        except PermissionError:
            if not has_creds:
                raise
            logger.info("Refreshing token after 401 ...")
            token_cache = _get_token(
                args.token_url, args.client_id, args.client_secret, None
            )
            bearer = token_cache.access_token
            pkg = fetch_package(args.base_url, bearer, doc)
        rows = walk_package_to_rows(pkg, rundate)
        logger.info("    extracted %d standard rows.", len(rows))
        all_rows.extend(rows)

    logger.info("Total rows extracted: %d.", len(all_rows))

    if args.dry_run:
        logger.info("--dry-run: not writing CSV.")
        if all_rows:
            sample = all_rows[0]
            logger.info("Sample row:")
            for k in CSV_COLUMNS:
                logger.info("  %-30s = %r", k, sample.get(k, ""))
        return 0

    n = write_csv(all_rows, args.output)
    logger.info("Wrote %d rows + header to %s", n, args.output)
    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. Inspect the diff:  git diff %s", args.output)
    logger.info("  2. Reload into local DB:")
    logger.info("       python3 supabase/seeds/load_standards.py --force")
    logger.info("  3. Rebuild cubes:")
    logger.info(
        "       cd backend && ./venv/bin/python -m app.transformations.runner"
    )
    logger.info("  4. If unhappy, restore the backup:")
    logger.info(
        "       mv %s %s", args.output.with_suffix(".csv.bak"), args.output
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
