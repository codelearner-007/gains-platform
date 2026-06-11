"""GAINS data toolchain — one CLI for wipe / seed / ingest / rebuild.

This is the production-reusable orchestrator that sits on top of the PROVEN
ingest + transformation pipeline. It does NOT duplicate ingest logic: `ingest`
calls `app.jobs.ingest_schoology.run_ingestion()` (which itself runs
`app.transformations.run_all`). `seed` reuses the rebuild-era GoTrue-safe
superadmin SQL and the `supabase/seeds/load_standards.py` loader.

Subcommands
-----------
    wipe    [--keep-standards] [--yes]
        pg_dump backup → FK-safe TRUNCATE of all raw_*/stg_*/dim_*/fact_*/cube_*
        + ingested_files/ingestion_runs → delete non-superadmin auth.users.
        Keeps schema, migrations, RBAC, and (with --keep-standards, the default)
        dim_standard/dim_strand. REFUSES without --yes.

    seed    [--superadmin-email …] [--superadmin-password …]
        Idempotent base bootstrap: ensure schools_all + standards + rbac present
        and create exactly ONE superadmin (default m.arham@insightanalytics.net /
        !Password123). GoTrue-safe; super_admin role assigned by name lookup.

    ingest  [--school SHORT|ALL] [--data-root PATH] [--source local|azure]
            [--limit-per-school N] [--seed S]
        Source-agnostic via make_blob_client. --school ALL iterates active
        schools. --limit-per-school N deterministically samples N assessments
        (= distinct (school, Item_ID) recovered from CSV rows) per school,
        seeded by --seed; never splits a Question-Data/Submission-Summary/
        Student-Submissions trio. Omitting --limit = FULL ingest (prod default).

    rebuild [--limit-per-school N] [--seed S] [--yes]
        The one-command path: wipe(--keep-standards) → seed → ingest --school ALL.

CLI usage:
    cd backend && python -m app.jobs.gains_data seed
    cd backend && python -m app.jobs.gains_data ingest --school ALL --limit-per-school 100 --seed 42
    cd backend && python -m app.jobs.gains_data rebuild --limit-per-school 100 --seed 42 --yes
"""

# ruff: noqa: E402  -- intentional sys.path bootstrap below requires deferred imports

from __future__ import annotations

# ─── sys.path bootstrap (mirror ingest_schoology) ──────────────────────────
import os as _os
import sys as _sys

_BACKEND_DIR = _os.path.dirname(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
)
if _BACKEND_DIR not in _sys.path:
    _sys.path.insert(0, _BACKEND_DIR)
# ──────────────────────────────────────────────────────────────────────────

import argparse
import asyncio
import logging
import random
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable

from sqlalchemy import text

from app.jobs.blob_client import BlobClient, BlobInfo, make_blob_client
from app.jobs.db import dispose_engine, session_scope
from app.jobs.ingest_schoology import IngestSummary, run_ingestion
from app.jobs.parsers.common import decode_csv_bytes, read_csv_text


logger = logging.getLogger("gains_data")

DEFAULT_SUPERADMIN_EMAIL = "m.arham@insightanalytics.net"
DEFAULT_SUPERADMIN_PASSWORD = "!Password123"  # noqa: S105 - dev bootstrap default

# Table-name prefixes wiped by `wipe`. dim_standard / dim_strand are excluded
# when --keep-standards (the default).
_WIPE_PREFIXES = ("raw_", "stg_", "dim_", "fact_", "cube_")
_WIPE_EXTRA = ("ingested_files", "ingestion_runs")
_STANDARDS_TABLES = ("dim_standard", "dim_strand")


# ───────────────────────────────────────────────────────────────────────────
# Deterministic per-school assessment sampling (blob-listing layer)
# ───────────────────────────────────────────────────────────────────────────

# Filename prefixes that make up an assessment "trio". Submission-Summary has no
# Item ID column, so its item is recovered from its sibling Question-Data /
# Student-Submissions file in the SAME folder sharing the SAME filename suffix.
_TRIO_PREFIXES = (
    "Question-Data-",
    "Submission-Summary-",
    "Student-Submissions-",
)
# Members that DO carry an "Item ID" column we can read.
_ITEM_BEARING_PREFIXES = ("Question-Data-", "Student-Submissions-")


def _trio_key(blob_path: str) -> tuple[str, str] | None:
    """Map a blob path → its trio key (folder_dir, filename_suffix).

    The suffix is the filename with its trio prefix stripped, so the three
    members of one assessment share an identical key. Returns None for files
    that are not part of a recognised trio.
    """
    parts = PurePosixPath(blob_path)
    folder = str(parts.parent)
    fn = parts.name
    for prefix in _TRIO_PREFIXES:
        if fn.startswith(prefix):
            return (folder, fn[len(prefix):])
    return None


def _item_id_from_csv(raw_bytes: bytes, source_name: str) -> str | None:
    """Recover the (single) distinct Item ID from a trio member's CSV rows.

    Each assessment folder/trio maps to exactly one Item ID. We read the first
    non-empty 'Item ID' cell. Returns None if the column is absent/empty.
    """
    item_id, _ = _item_and_school_from_csv(raw_bytes, source_name)
    return item_id


def _item_and_school_from_csv(
    raw_bytes: bytes, source_name: str
) -> tuple[str | None, str | None]:
    """Recover (Item ID, User School ID) from a trio member's CSV rows.

    Each assessment folder/trio maps to exactly one Item ID and one school. We
    read the first non-empty 'Item ID' / 'User School ID' cells. Either may be
    None if the column is absent/empty (Question-Data has no User School ID).
    """
    decoded = decode_csv_bytes(raw_bytes, source_name=source_name)
    headers, rows = read_csv_text(decoded, source_name=source_name)
    item_id: str | None = None
    school_id: str | None = None
    have_item = "Item ID" in headers
    have_school = "User School ID" in headers
    if not have_item and not have_school:
        return None, None
    for row in rows:
        if item_id is None and have_item:
            v = (row.get("Item ID") or "").strip()
            if v:
                item_id = v
        if school_id is None and have_school:
            v = (row.get("User School ID") or "").strip()
            if v:
                school_id = v
        if (item_id or not have_item) and (school_id or not have_school):
            break
    return item_id, school_id


def _stable_seed(seed: int, school_root: str) -> int:
    """Derive a per-school RNG seed that is stable across runs and independent
    of which order schools are listed in. Same (seed, school_root) → same int.
    """
    h = 1469598103934665603  # FNV-1a 64-bit offset basis
    for b in f"{seed}:{school_root}".encode():
        h ^= b
        h = (h * 1099511628257) & 0xFFFFFFFFFFFFFFFF
    return h


class SamplingBlobClient:
    """Wraps a BlobClient and limits `list_files` to a deterministic sample of
    N assessments (distinct Item IDs) PER SCHOOL.

    Implements the BlobClient protocol so the orchestrator is unchanged. Because
    the legacy backup is a single MIXED tree (all schools share one root and each
    row carries its own "User School ID"), a sample taken over the whole root
    must be partitioned by school first, then sampled N-per-school — otherwise a
    flat "N total" sample would starve the smaller schools. The sample is:
      1. list every blob under the (whole-tree) root,
      2. group into trios by (folder, filename-suffix),
      3. recover each trio's Item ID AND User School ID from its CSV rows (the
         Student-Submissions member carries both; Item ID maps 1:1 to a school),
      4. bucket items by school, seed random.Random with a per-school-stable seed
         (keyed off seed + school id) and sample N distinct Item IDs per school,
      5. return ONLY the blobs belonging to the selected items' trios — so a trio
         is never split.

    `--limit-per-school 0` (or None) is handled by the caller (it just uses the
    base client). Trios whose Item ID/School cannot be recovered are kept intact
    and bucketed under a sentinel school so nothing is dropped.
    """

    def __init__(self, base: BlobClient, *, limit: int, seed: int) -> None:
        self._base = base
        self._limit = limit
        self._seed = seed

    def download(self, blob_path: str, school_root: str | Path) -> bytes:
        return self._base.download(blob_path, school_root)

    def list_files(self, school_root: str | Path) -> Iterable[BlobInfo]:
        all_blobs: list[BlobInfo] = list(self._base.list_files(school_root))

        # Group blobs into trios; collect the item-bearing member to read Item ID
        # + User School ID. Prefer Student-Submissions (carries BOTH columns).
        trios: dict[tuple[str, str], list[BlobInfo]] = defaultdict(list)
        item_source: dict[tuple[str, str], BlobInfo] = {}
        for blob in all_blobs:
            key = _trio_key(blob.path)
            if key is None:
                # Unknown file shape — keep it as its own unit (own item id).
                key = ("__loose__", blob.path)
            trios[key].append(blob)
            fn = PurePosixPath(blob.path).name
            is_student_sub = fn.startswith("Student-Submissions-")
            is_item_bearing = any(fn.startswith(p) for p in _ITEM_BEARING_PREFIXES)
            cur = item_source.get(key)
            cur_is_student = cur is not None and PurePosixPath(
                cur.path
            ).name.startswith("Student-Submissions-")
            # Prefer a Student-Submissions member (has User School ID); else any
            # item-bearing member (Question-Data → Item ID only, no school).
            if is_item_bearing and (cur is None or (is_student_sub and not cur_is_student)):
                item_source[key] = blob

        # Recover each trio's (Item ID, School ID). Trios with no readable Item ID
        # fall back to a unit id derived from the trio key; trios with no readable
        # School ID are bucketed under a sentinel so they are still sampleable.
        unit_for_trio: dict[tuple[str, str], str] = {}
        school_for_trio: dict[tuple[str, str], str] = {}
        for key, _members in trios.items():
            src = item_source.get(key)
            item_id: str | None = None
            school_id: str | None = None
            if src is not None:
                try:
                    raw = self._base.download(src.path, school_root)
                    item_id, school_id = _item_and_school_from_csv(raw, src.path)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(
                        "sampling: could not read Item ID/School from %s: %s",
                        src.path, exc,
                    )
            unit_for_trio[key] = item_id if item_id else f"__nokey__:{key[0]}|{key[1]}"
            school_for_trio[key] = school_id if school_id else "__noschool__"

        # Map (school, sampling-unit) → the trio keys that belong to it. In
        # practice one item == one trio, but two folders can share an item
        # (e.g. Sec 1 / Sec 2 of a shared course) — keep them together.
        units: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
        units_by_school: dict[str, set[str]] = defaultdict(set)
        for key, unit in unit_for_trio.items():
            sc = school_for_trio[key]
            units[(sc, unit)].append(key)
            units_by_school[sc].add(unit)

        # Sample N distinct items PER SCHOOL, each with its own stable seed.
        selected: set[tuple[str, str]] = set()
        for sc in sorted(units_by_school.keys()):
            unit_ids = sorted(units_by_school[sc])
            rng = random.Random(_stable_seed(self._seed, f"{school_root}|{sc}"))
            n = min(self._limit, len(unit_ids))
            chosen = set(rng.sample(unit_ids, n)) if n else set()
            for u in chosen:
                selected.add((sc, u))
            logger.info(
                "sampling[school=%s]: %d assessments available, selecting %d (seed=%d)",
                sc, len(unit_ids), len(chosen), self._seed,
            )

        for skey in sorted(units.keys()):
            if skey not in selected:
                continue
            for key in units[skey]:
                yield from trios[key]


# ───────────────────────────────────────────────────────────────────────────
# wipe
# ───────────────────────────────────────────────────────────────────────────


def _dsn() -> str:
    return _os.environ.get(
        "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:56322/postgres"
    )


def _pg_dump_backup(backup_dir: str = "/tmp/gains-backup") -> str:
    """pg_dump the current DB to a timestamped custom-format file. Returns path.

    Raises on failure — a wipe must NOT proceed without a backup.
    """
    Path(backup_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = str(Path(backup_dir) / f"prebuild-{ts}.dump")
    dsn = _dsn()
    # pg_dump accepts a libpq URL directly (strip the +asyncpg driver suffix).
    url = dsn.replace("postgresql+asyncpg://", "postgresql://")
    logger.info("wipe: pg_dump backup → %s", out)
    subprocess.run(
        ["pg_dump", "--format=custom", "--file", out, url],
        check=True,
    )
    return out


async def _discover_wipe_tables(keep_standards: bool) -> list[str]:
    """Discover all public tables matching the wipe prefixes + the extras."""
    async with session_scope() as session:
        result = await session.execute(
            text(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
                """
            )
        )
        all_tables = [r.tablename for r in result]

    targets: list[str] = []
    for t in all_tables:
        if t in _WIPE_EXTRA or any(t.startswith(p) for p in _WIPE_PREFIXES):
            if keep_standards and t in _STANDARDS_TABLES:
                continue
            targets.append(t)
    return targets


async def cmd_wipe(*, keep_standards: bool, yes: bool, backup: bool = True) -> int:
    """Backup → FK-safe TRUNCATE of data tables → drop non-superadmin users."""
    if not yes:
        logger.error(
            "REFUSING TO WIPE without --yes. This empties all ingested data and "
            "drops non-superadmin auth.users."
        )
        return 1

    if backup:
        _pg_dump_backup()

    targets = await _discover_wipe_tables(keep_standards)
    if not targets:
        logger.warning("wipe: no data tables matched — nothing to truncate.")
    else:
        # A single TRUNCATE ... CASCADE over the full set is FK-safe: CASCADE
        # follows FKs to any dependent rows, and listing every data table means
        # standards (when kept) are the only rows that survive.
        table_list = ", ".join(targets)
        logger.info("wipe: TRUNCATE %d table(s) (keep_standards=%s)",
                    len(targets), keep_standards)
        async with session_scope() as session:
            await session.execute(
                text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")
            )

    # Drop every auth.users row that is NOT a super_admin. Their public rows
    # (user_profiles, user_roles, user_schools) cascade via FK ON DELETE.
    async with session_scope() as session:
        result = await session.execute(
            text(
                """
                DELETE FROM auth.users u
                WHERE NOT EXISTS (
                    SELECT 1 FROM public.user_roles ur
                    JOIN public.roles r ON r.id = ur.role_id
                    WHERE ur.user_id = u.id AND r.name = 'super_admin'
                )
                """
            )
        )
        logger.info("wipe: dropped %d non-superadmin auth.users", result.rowcount or 0)

    logger.info("wipe complete (schema, migrations, RBAC, superadmin preserved).")
    return 0


# ───────────────────────────────────────────────────────────────────────────
# seed
# ───────────────────────────────────────────────────────────────────────────


def _seeds_dir() -> Path:
    """<repo>/supabase/seeds."""
    return Path(_BACKEND_DIR).parent / "supabase" / "seeds"


async def _ensure_schools() -> int:
    """Apply schools_all.sql (idempotent) so all active schools exist."""
    sql_path = _seeds_dir() / "schools_all.sql"
    sql = sql_path.read_text(encoding="utf-8")
    async with session_scope() as session:
        await session.execute(text(sql))
        result = await session.execute(
            text("SELECT count(*) FROM schools WHERE is_active = TRUE")
        )
        count = result.scalar_one()
    logger.info("seed: schools_all applied (%d active schools).", count)
    return count


def _ensure_standards() -> None:
    """Load dim_standard / dim_strand via the proven psycopg2 loader (idempotent)."""
    # load_standards lives under supabase/seeds and uses psycopg2 synchronously;
    # import it lazily so the async path doesn't depend on it.
    seeds_dir = str(_seeds_dir())
    if seeds_dir not in _sys.path:
        _sys.path.insert(0, seeds_dir)
    import load_standards  # type: ignore

    import psycopg2

    dsn = _dsn().replace("postgresql+asyncpg://", "postgresql://")
    with psycopg2.connect(dsn) as conn:
        load_standards.load_dim_standard(conn, force=False)
        load_standards.load_dim_strand(conn, force=False)
    logger.info("seed: standards ensured (dim_standard + dim_strand).")


async def _ensure_rbac() -> None:
    """Ensure the super_admin role has every permission (idempotent)."""
    async with session_scope() as session:
        await session.execute(
            text(
                """
                INSERT INTO public.role_permissions (role_id, permission_id)
                SELECT r.id, p.id
                FROM public.roles r
                CROSS JOIN public.permissions p
                WHERE r.name = 'super_admin'
                ON CONFLICT (role_id, permission_id) DO NOTHING
                """
            )
        )
    logger.info("seed: RBAC grants ensured for super_admin.")


async def _ensure_superadmin(email: str, password: str) -> None:
    """Create exactly ONE superadmin, GoTrue-safe + super_admin role by name.

    Reuses the proven rebuild-era pattern: auth.users token columns set to ''
    (NOT NULL — else GoTrue login 500s), email_confirmed_at set, a matching
    auth.identities row, and an explicit super_admin user_roles assignment.
    Idempotent: re-running resets the password + re-asserts the role.
    """
    full_name = email.split("@")[0].replace(".", " ").title()
    async with session_scope() as session:
        existing = await session.execute(
            text("SELECT id FROM auth.users WHERE email = :email"),
            {"email": email},
        )
        row = existing.first()
        if row is not None:
            user_id = row.id
            await session.execute(
                text(
                    """
                    UPDATE auth.users
                    SET encrypted_password = crypt(:pw, gen_salt('bf')),
                        email_confirmed_at = now(),
                        updated_at = now()
                    WHERE id = :id
                    """
                ),
                {"pw": password, "id": user_id},
            )
        else:
            created = await session.execute(
                text(
                    """
                    INSERT INTO auth.users (
                        id, instance_id, aud, role, email, encrypted_password,
                        email_confirmed_at, raw_app_meta_data, raw_user_meta_data,
                        created_at, updated_at,
                        -- GoTrue scans these token columns as NOT NULL strings;
                        -- manually-inserted rows must set them to '' or login 500s
                        -- with "Database error querying schema".
                        confirmation_token, recovery_token, email_change,
                        email_change_token_new, email_change_token_current,
                        phone_change, phone_change_token, reauthentication_token)
                    VALUES (
                        uuid_generate_v7(), '00000000-0000-0000-0000-000000000000',
                        'authenticated', 'authenticated', CAST(:email AS text),
                        crypt(CAST(:pw AS text), gen_salt('bf')), now(),
                        '{"provider":"email","providers":["email"]}'::jsonb,
                        jsonb_build_object('full_name', CAST(:full_name AS text)),
                        now(), now(),
                        '', '', '', '', '', '', '', '')
                    RETURNING id
                    """
                ),
                {"email": email, "pw": password, "full_name": full_name},
            )
            user_id = created.scalar_one()
            # NOTE: auth.users.confirmed_at is GENERATED ALWAYS AS
            # LEAST(email_confirmed_at, phone_confirmed_at) — never set it
            # directly. Setting email_confirmed_at above populates it.
            await session.execute(
                text(
                    """
                    INSERT INTO auth.identities (
                        id, provider_id, user_id, identity_data, provider,
                        last_sign_in_at, created_at, updated_at)
                    VALUES (
                        uuid_generate_v7(), CAST(:provider_id AS text), :user_id,
                        jsonb_build_object('sub', CAST(:sub AS text),
                                           'email', CAST(:email AS text),
                                           'email_verified', true),
                        'email', now(), now(), now())
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "provider_id": str(user_id),
                    "user_id": user_id,
                    "sub": str(user_id),
                    "email": email,
                },
            )

        # Assert the super_admin role by name lookup (role id changes per reset).
        # The handle_new_user trigger may already have assigned it (first user),
        # but we enforce it explicitly + idempotently. session_user='postgres'
        # is permitted by prevent_super_admin_manual_assignment.
        await session.execute(
            text(
                """
                INSERT INTO public.user_roles (user_id, role_id)
                SELECT :user_id, r.id FROM public.roles r WHERE r.name = 'super_admin'
                ON CONFLICT (user_id, role_id) DO NOTHING
                """
            ),
            {"user_id": user_id},
        )
        # If the trigger assigned the default 'user' role on insert, drop it so
        # the superadmin carries ONLY super_admin.
        await session.execute(
            text(
                """
                DELETE FROM public.user_roles ur
                USING public.roles r
                WHERE ur.role_id = r.id
                  AND ur.user_id = :user_id
                  AND r.name <> 'super_admin'
                """
            ),
            {"user_id": user_id},
        )
    logger.info("seed: superadmin ensured (%s, role=super_admin).", email)


async def cmd_seed(*, superadmin_email: str, superadmin_password: str) -> int:
    """Idempotent base bootstrap: schools + standards + rbac + ONE superadmin."""
    await _ensure_schools()
    _ensure_standards()
    await _ensure_rbac()
    await _ensure_superadmin(superadmin_email, superadmin_password)
    logger.info("seed complete.")
    return 0


# ───────────────────────────────────────────────────────────────────────────
# ingest
# ───────────────────────────────────────────────────────────────────────────


async def cmd_ingest(
    *,
    school: str,
    data_root: str | None,
    source: str | None,
    limit_per_school: int,
    seed: int,
) -> IngestSummary:
    """Run ingest for one school or ALL active schools, optionally sampled.

    Because the staging layer resolves each row's real school from the CSV
    "User School ID", a single MIXED backup tree (the legacy
    synapse/pre_landing/Schoology year-rooted tree, NOT split per-school)
    ingests every school correctly. When `--data-root` points at such a tree
    we make ONE raw pass over the whole root (`whole_tree_root`) rather than
    looking for a per-`short_name` subfolder per school (which the mixed tree
    does not have), then staging distributes rows to all schools.

    Sampling, when requested, deterministically samples N assessments
    (distinct Item IDs) over that whole tree — the school-stable seed keys off
    the (seed, root) pair so it is reproducible.
    """
    base = make_blob_client(source=source, data_root=data_root)
    bc: BlobClient
    if limit_per_school and limit_per_school > 0:
        bc = SamplingBlobClient(base, limit=limit_per_school, seed=seed)
    else:
        bc = base

    school_filter = None if school.upper() == "ALL" else school
    # A supplied local --data-root is the mixed legacy backup tree → whole-tree
    # mode. With no --data-root we fall back to the per-school <repo>/data layout.
    whole_tree_root = "." if data_root else None
    summary = await run_ingestion(
        school_filter=school_filter,
        blob_client=bc,
        whole_tree_root=whole_tree_root,
    )
    return summary


# ───────────────────────────────────────────────────────────────────────────
# rebuild
# ───────────────────────────────────────────────────────────────────────────


async def cmd_rebuild(
    *,
    limit_per_school: int,
    seed: int,
    yes: bool,
    superadmin_email: str,
    superadmin_password: str,
    data_root: str | None,
    source: str | None,
) -> int:
    """wipe(--keep-standards) → seed → ingest --school ALL [--limit-per-school]."""
    if not yes:
        logger.error("REFUSING TO REBUILD without --yes.")
        return 1
    rc = await cmd_wipe(keep_standards=True, yes=True)
    if rc != 0:
        return rc
    await cmd_seed(
        superadmin_email=superadmin_email,
        superadmin_password=superadmin_password,
    )
    summary = await cmd_ingest(
        school="ALL",
        data_root=data_root,
        source=source,
        limit_per_school=limit_per_school,
        seed=seed,
    )
    logger.info(
        "rebuild complete: files_processed=%d rows=%d errors=%d",
        summary.files_processed, summary.rows_inserted, summary.error_count,
    )
    return 0 if summary.error_count == 0 else 2


# ───────────────────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────────────────


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gains_data",
        description="GAINS data toolchain: wipe / seed / ingest / rebuild.",
    )
    parser.add_argument("--log-level", default="INFO", help="DEBUG, INFO, WARNING.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_wipe = sub.add_parser("wipe", help="Backup + truncate data + drop non-superadmins.")
    p_wipe.add_argument(
        "--keep-standards", action="store_true", default=True,
        help="Preserve dim_standard/dim_strand (default).",
    )
    p_wipe.add_argument(
        "--wipe-standards", dest="keep_standards", action="store_false",
        help="Also truncate dim_standard/dim_strand (forces an 8k-row reload).",
    )
    p_wipe.add_argument("--yes", action="store_true", help="Required; confirms the destructive op.")
    p_wipe.add_argument(
        "--no-backup", dest="backup", action="store_false", default=True,
        help="Skip the pg_dump backup (NOT recommended).",
    )

    p_seed = sub.add_parser("seed", help="Idempotent base seed + one superadmin.")
    p_seed.add_argument("--superadmin-email", default=DEFAULT_SUPERADMIN_EMAIL)
    p_seed.add_argument("--superadmin-password", default=DEFAULT_SUPERADMIN_PASSWORD)

    p_ingest = sub.add_parser("ingest", help="Source-agnostic ingest (optionally sampled).")
    p_ingest.add_argument("--school", default="ALL", help="short_name | building_id | name | ALL.")
    p_ingest.add_argument("--data-root", default=None, help="Local data root (LocalBlobClient).")
    p_ingest.add_argument("--source", default=None, choices=("local", "azure"))
    p_ingest.add_argument(
        "--limit-per-school", type=int, default=0,
        help="Sample N assessments/school (0 or omitted = FULL ingest).",
    )
    p_ingest.add_argument("--seed", type=int, default=42, help="RNG seed for sampling.")

    p_rebuild = sub.add_parser("rebuild", help="wipe → seed → ingest ALL (one command).")
    p_rebuild.add_argument("--limit-per-school", type=int, default=0)
    p_rebuild.add_argument("--seed", type=int, default=42)
    p_rebuild.add_argument("--yes", action="store_true")
    p_rebuild.add_argument("--superadmin-email", default=DEFAULT_SUPERADMIN_EMAIL)
    p_rebuild.add_argument("--superadmin-password", default=DEFAULT_SUPERADMIN_PASSWORD)
    p_rebuild.add_argument("--data-root", default=None)
    p_rebuild.add_argument("--source", default=None, choices=("local", "azure"))

    return parser


async def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _setup_logging(args.log_level)

    try:
        if args.command == "wipe":
            return await cmd_wipe(
                keep_standards=args.keep_standards, yes=args.yes, backup=args.backup
            )
        if args.command == "seed":
            return await cmd_seed(
                superadmin_email=args.superadmin_email,
                superadmin_password=args.superadmin_password,
            )
        if args.command == "ingest":
            summary = await cmd_ingest(
                school=args.school,
                data_root=args.data_root,
                source=args.source,
                limit_per_school=args.limit_per_school,
                seed=args.seed,
            )
            return 0 if summary.error_count == 0 else 2
        if args.command == "rebuild":
            return await cmd_rebuild(
                limit_per_school=args.limit_per_school,
                seed=args.seed,
                yes=args.yes,
                superadmin_email=args.superadmin_email,
                superadmin_password=args.superadmin_password,
                data_root=args.data_root,
                source=args.source,
            )
        return 1
    finally:
        await dispose_engine()


if __name__ == "__main__":
    _sys.exit(asyncio.run(main()))
