"""One-shot daily database backup: pg_dump -> Cloudflare R2, with a run-summary email.

Entry point for the `backup` Railway service. Run manually via `python backup.py`
(real backup) or `python backup.py --dry-run` (preflight checks only, no dump or
upload). See docs/backup-service-technical-plan.md Section 2 for the runtime
sequence this mirrors.
"""

import argparse
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from dotenv import load_dotenv

from lib.config import get_settings
from lib.logger import setup_logging
from lib.notify import send_run_summary
from lib.pg_dump import PgDumpError, check_pg_dump_available, dump_destination, run_pg_dump
from lib.r2_upload import MIN_RETENTION_COUNT, check_bucket_access, prune_old_backups, upload_dump

# No-op on Railway (env vars are injected directly); loads .env for local dev
# before any Settings() is constructed.
load_dotenv()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backup.py",
        description=(
            "One-shot database backup: pg_dump the configured database, upload "
            "the dump to Cloudflare R2, and email a run summary."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run preflight checks only (settings, pg_dump availability, R2 bucket "
        "access). No dump is taken and nothing is uploaded.",
    )
    return parser


def main(argv: list[str]) -> int:
    # Parsed before the try/finally below: an unrecognized flag makes argparse
    # exit(2) directly here, so no run has started and no summary email fires.
    args = _build_arg_parser().parse_args(argv)

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    summary: dict[str, Any] = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "dry_run": args.dry_run,
        "fatal_error": None,
        "cleanup": None,
    }

    # Fallback logger in case Settings() itself fails to load (e.g. a missing
    # required env var); rebound to the configured level once settings load.
    log = setup_logging(run_id, "info")
    exit_code = 0
    stage = "preflight"

    try:
        settings = get_settings()
        log = setup_logging(run_id, settings.backup_log_level)
        try:
            summary["database_host"] = urlsplit(settings.database_url).hostname or "?"
        except ValueError:
            summary["database_host"] = "?"
        # Reuses prune_old_backups' own floor so the summary/email can never
        # report a different number than what actually gets enforced.
        summary["retention_count"] = max(MIN_RETENTION_COUNT, settings.backup_retention_count)
        log.info("backup run starting", extra={"stage": "startup", "dry_run": summary["dry_run"]})

        log.info("running preflight checks", extra={"stage": "preflight"})
        check_pg_dump_available()
        check_bucket_access(settings)
        log.info("preflight checks passed", extra={"stage": "preflight"})

        if args.dry_run:
            log.info("dry-run: skipping pg_dump and R2 upload", extra={"stage": "dry-run"})
        else:
            tmp_dir = settings.backup_tmp_dir or tempfile.gettempdir()
            dump_file_path = dump_destination(tmp_dir, run_id)
            try:
                stage = "pg_dump"
                dump_result = run_pg_dump(
                    database_url=settings.database_url,
                    tmp_dir=tmp_dir,
                    timeout_ms=settings.backup_pgdump_timeout_ms,
                    run_id=run_id,
                    log=log,
                )
                summary["dump_bytes"] = dump_result.dump_bytes
                summary["dump_duration_sec"] = round(dump_result.duration_ms / 1000, 3)

                stage = "upload"
                upload_info = upload_dump(
                    file_path=dump_result.file_path,
                    run_id=run_id,
                    settings=settings,
                    timeout_ms=settings.backup_upload_timeout_ms,
                    log=log,
                )
                summary["r2_bucket"] = upload_info["r2_bucket"]
                summary["r2_key"] = upload_info["r2_key"]
                summary["upload_duration_sec"] = upload_info["upload_duration_sec"]

                stage = "cleanup"
                summary["cleanup"] = prune_old_backups(
                    settings, keep=summary["retention_count"], log=log
                )
            finally:
                # Always clear the temp dump file, success or failure -- including
                # a partial file left behind by a pg_dump that timed out or exited
                # non-zero before returning a PgDumpResult -- so a multi-GB dump
                # never survives on the container's ephemeral disk.
                if os.path.exists(dump_file_path):
                    os.remove(dump_file_path)

        stage = "done"
        log.info("backup run completed successfully", extra={"stage": "done"})
    except Exception as exc:
        exit_code = 1
        fatal_error: dict[str, Any] = {
            "name": type(exc).__name__,
            "message": str(exc),
            "stage": stage,
        }
        if isinstance(exc, PgDumpError) and exc.stderr_tail:
            fatal_error["stderr_tail"] = exc.stderr_tail
        summary["fatal_error"] = fatal_error
        log.error(f"backup run failed at stage={stage}: {exc}", extra={"stage": stage})
    finally:
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        summary["duration_sec"] = round(elapsed, 3)
        # Runs on every exit path -- success, a caught dump/upload/preflight
        # error, or an unhandled exception -- so a run's outcome is always
        # reported. send_run_summary() never raises, so a Resend outage here
        # can never mask exit_code determined above.
        send_run_summary(summary, log)

    return exit_code


if __name__ == "__main__":
    try:
        _exit_code = main(sys.argv[1:])
    except SystemExit:
        # argparse's own exit(2) on bad CLI usage -- let it through unchanged,
        # not a case for the last-resort guard below.
        raise
    except BaseException as exc:  # noqa: BLE001 -- last-resort guard, see module docstring
        # Catches whatever main()'s own try/except/finally didn't (e.g. a
        # KeyboardInterrupt during a manual run): log it and exit(1) directly.
        print(f"backup.py: unhandled error: {exc}", file=sys.stderr)
        sys.exit(1)
    else:
        sys.exit(_exit_code)
