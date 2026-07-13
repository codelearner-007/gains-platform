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
        # CFDocument-level URI (all standards in a framework share one) — this
        # is the raw IMS/CASE JSON API, kept legacy-faithful in the seed. It is
        # NOT a human web page; run `resolve_cpalms_links.py` after loading to
        # rewrite dim_standard.direct_link to the CPALMS standard page
        # (…/PreviewStandard/Preview/{id}). Reports suppress any leftover JSON
        # link (see students/bands.ts `standardHref`).
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


# ─── Update mode (default) ─────────────────────────────────────────────────

# Columns refreshed from CPALMS in --update mode. Everything else on the
# existing row is preserved as-is — most importantly `Schoology_Standard`
# (the AI.MA.* alias) and its derived columns (cPalms_Standard, Standard_New).
UPDATABLE_COLUMNS = (
    "description",
    "Custom.CleanedDescription",
    "cluster",
    "Strand",
    "Grader",
    "Subject",
    "Direct_Link",
    "lastChangeDateTime",
    "rundate",
)


def _read_existing_csv(path: Path) -> list[dict[str, str]]:
    """Read the existing dim_standard.csv preserving every column verbatim."""
    if not path.exists():
        raise FileNotFoundError(
            f"Existing seed not found at {path}. Use --full-pull to bootstrap."
        )
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise RuntimeError(f"Seed at {path} is empty.")
    # Sanity-check the header matches what we expect.
    first = rows[0]
    missing = [c for c in CSV_COLUMNS if c not in first]
    if missing:
        raise RuntimeError(
            f"Seed at {path} missing expected columns: {missing}"
        )
    return rows


def _count_alias_rows(path: Path) -> int:
    """Count Schoology course-prefix alias rows in the existing seed.

    An "alias" row is one whose ``Schoology_Standard`` is NOT the plain
    canonical CPALMS/IMS form — i.e. it carries a Schoology course prefix
    (``AI.MA.912.AR.3.1``) or an embedded ``MAFS``/``LAFS`` alignment
    (``MA.9-12.MAFS.912.N-RN.1.2``). These rows exist only because legacy
    observed them in gradebook CSVs; a pure CPALMS pull cannot reproduce
    them. Used by the --full-pull guard to refuse silent alias loss.

    Returns 0 when the seed is absent (nothing to lose → bootstrap is safe).
    """
    if not path.exists():
        return 0
    count = 0
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("Schoology_Standard") or "")
            if "MAFS" in code or "LAFS" in code:
                count += 1
            elif code[:3] in ("AI.", "BA.", "AL.") and "." in code[3:]:
                # Course-prefix alias (Algebra-I, Biology, etc.).
                count += 1
    return count


def _index_cpalms_by_identifier(
    cpalms_rows: list[dict[str, str]],
) -> dict[str, dict[str, str]]:
    """Group rows by lowercased Identifier; pick the first if duplicates."""
    index: dict[str, dict[str, str]] = {}
    for r in cpalms_rows:
        ident = (r.get("Identifier") or "").lower()
        if not ident or ident in index:
            continue
        index[ident] = r
    return index


def update_existing_from_cpalms(
    seed_path: Path,
    cpalms_rows: list[dict[str, str]],
    dry_run: bool = False,
) -> tuple[int, int, list[str]]:
    """Apply CPALMS text content onto the existing seed file in-place.

    Returns (rows_updated, rows_unmapped, sample_unmapped_identifiers).

    Behavior (matches the validated plan):
      - For every row in the existing seed whose Identifier is also in CPALMS:
        overwrite each column in `UPDATABLE_COLUMNS` with the CPALMS value.
      - For seed rows with no CPALMS match: leave the row unchanged, count it,
        log a warning.
      - CPALMS rows with no seed match are silently skipped.

    `Schoology_Standard`, `cPalms_Standard`, `Standard_New`, `Language`,
    `uniquesID`, `Cognitive_Complexity_Rating`, and `Identifier` are
    preserved untouched — they encode the Schoology alias and its
    derivations and must not change here.
    """
    existing = _read_existing_csv(seed_path)
    index = _index_cpalms_by_identifier(cpalms_rows)

    logger.info("Existing seed: %d rows.", len(existing))
    logger.info("CPALMS canonical rows indexed: %d identifiers.", len(index))

    rows_updated = 0
    rows_unmapped: list[str] = []
    rows_unchanged_after_match = 0
    fields_changed: dict[str, int] = {c: 0 for c in UPDATABLE_COLUMNS}

    for row in existing:
        ident = (row.get("Identifier") or "").lower()
        cpalms = index.get(ident)
        if not cpalms:
            # Standard exists in our seed but not in CPALMS — leave alone.
            rows_unmapped.append(
                f"{ident}  schoology={row.get('Schoology_Standard','')}"
            )
            continue

        changed_any = False
        for col in UPDATABLE_COLUMNS:
            new = cpalms.get(col, "")
            old = row.get(col, "")
            if new != old:
                row[col] = new
                fields_changed[col] += 1
                changed_any = True
        if changed_any:
            rows_updated += 1
        else:
            rows_unchanged_after_match += 1

    logger.info("")
    logger.info("Update summary:")
    logger.info("  rows matched + updated:       %d", rows_updated)
    logger.info("  rows matched but already current: %d", rows_unchanged_after_match)
    logger.info("  rows with no CPALMS match (left alone): %d", len(rows_unmapped))
    logger.info("")
    logger.info("Per-column change counts:")
    for col, n in fields_changed.items():
        logger.info("  %-30s  %5d rows touched", col, n)

    if rows_unmapped:
        logger.info("")
        logger.info(
            "Sample of unmapped identifiers (first 10 of %d):", len(rows_unmapped)
        )
        for line in rows_unmapped[:10]:
            logger.info("  %s", line)

    if dry_run:
        logger.info("")
        logger.info("--dry-run: not writing CSV.")
        return rows_updated, len(rows_unmapped), rows_unmapped[:10]

    write_csv(existing, seed_path)
    logger.info("")
    logger.info("Wrote %d rows + header to %s", len(existing), seed_path)
    return rows_updated, len(rows_unmapped), rows_unmapped[:10]


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
        "--full-pull",
        action="store_true",
        help=(
            "Generate a fresh CSV from scratch (one row per CPALMS identifier; "
            "DROPS Schoology AI.MA.* alias rows). Only use this for an initial "
            "bootstrap or when you have no existing seed. Default behavior is "
            "the safer update-in-place mode. Requires "
            "--i-understand-this-drops-aliases unless the existing seed has no "
            "alias rows to lose."
        ),
    )
    parser.add_argument(
        "--i-understand-this-drops-aliases",
        action="store_true",
        help=(
            "Required confirmation for --full-pull when the existing seed "
            "contains Schoology course-prefix alias rows (AI.MA.*, *.MAFS.*). "
            "Dropping them silently breaks the exact-match rollup joins — see "
            "backend/tests/api/test_standards_alias_coverage.py."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and compute, but do not overwrite the CSV. Prints summary.",
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

    logger.info("Total CPALMS rows extracted: %d.", len(all_rows))

    if args.full_pull:
        # Bootstrap mode — discard existing seed structure, write a fresh
        # CSV with one row per CPALMS identifier. This drops Schoology
        # alias rows (AI.MA.*); only use for initial setup or when the
        # existing seed is unrecoverable.
        #
        # SAFETY GUARD: count the alias rows the existing seed would lose.
        # Those rows are the ONLY thing letting the per-item rollups join
        # Schoology's emitted alias labels (AI.MA.*, *.MAFS.*) — they were
        # observed from gradebook CSVs, not present in the CPALMS/IMS feed
        # (docs/audit/legacy-schoology-cpalms-mapping.md). If the operator
        # hasn't explicitly acknowledged the loss, abort.
        alias_rows = _count_alias_rows(args.output)
        if alias_rows > 0 and not args.i_understand_this_drops_aliases:
            logger.error(
                "ABORT: --full-pull would drop %d Schoology alias row(s) "
                "(AI.MA.* / *.MAFS.*) from %s.",
                alias_rows,
                args.output,
            )
            logger.error(
                "These aliases are required by the exact-match rollup joins; "
                "dropping them silently collapses aligned questions into the "
                "'Other' bucket. Prefer the default update-in-place mode "
                "(omit --full-pull), or — if you really must rebuild from "
                "scratch — re-add --i-understand-this-drops-aliases AND plan "
                "to re-augment aliases from the Question-Data CSVs afterward."
            )
            logger.error(
                "Verify coverage after any refresh: "
                "cd backend && ./venv/bin/python -m pytest "
                "tests/api/test_standards_alias_coverage.py"
            )
            return 2
        if alias_rows > 0:
            logger.warning(
                "--full-pull: dropping %d Schoology alias row(s) per explicit "
                "--i-understand-this-drops-aliases. Re-augment them from the "
                "Question-Data CSVs and re-run the alias-coverage test before "
                "shipping.",
                alias_rows,
            )
        if args.dry_run:
            logger.info("--dry-run --full-pull: not writing CSV.")
            if all_rows:
                sample = all_rows[0]
                logger.info("Sample row:")
                for k in CSV_COLUMNS:
                    logger.info("  %-30s = %r", k, sample.get(k, ""))
            return 0
        n = write_csv(all_rows, args.output)
        logger.info("Wrote %d rows + header to %s (full-pull mode).", n, args.output)
    else:
        # Default mode — update only the text content of existing seed rows
        # whose Identifier matches a CPALMS canonical row. Preserves every
        # Schoology AI.MA.* alias row by-the-by because Identifier is the
        # join key and the rows are kept untouched on their Schoology_Standard.
        logger.info("Updating existing seed in place from CPALMS …")
        update_existing_from_cpalms(args.output, all_rows, dry_run=args.dry_run)

    if args.dry_run:
        return 0

    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. Inspect the diff:  git diff %s", args.output)
    logger.info("  2. Reload into local DB:")
    logger.info("       python3 supabase/seeds/load_standards.py --force")
    logger.info("  3. Rebuild cubes:")
    logger.info(
        "       cd backend && ./venv/bin/python -m app.transformations.runner"
    )
    logger.info("  4. Verify the KPI anchors didn't move:")
    logger.info(
        "       cd backend && ./venv/bin/python -m pytest tests/api/test_canonical_kpis.py"
    )
    logger.info("  5. If unhappy, restore the backup:")
    logger.info(
        "       mv %s %s", args.output.with_suffix(".csv.bak"), args.output
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
