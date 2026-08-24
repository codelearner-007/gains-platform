from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass

_VERSION_CHECK_TIMEOUT_SEC = 10
_STDERR_TAIL_CHARS = 4000


@dataclass
class PgDumpResult:
    file_path: str
    dump_bytes: int
    duration_ms: int


class PgDumpError(Exception):
    def __init__(self, message: str, stderr_tail: str = "") -> None:
        super().__init__(message)
        self.stage = "pg_dump"
        self.stderr_tail = stderr_tail


def _decode_stderr_tail(stderr: bytes | None) -> str:
    if not stderr:
        return ""
    return stderr.decode("utf-8", errors="replace")[-_STDERR_TAIL_CHARS:]


def check_pg_dump_available() -> None:
    if shutil.which("pg_dump") is None:
        raise PgDumpError("pg_dump not found on PATH")
    try:
        result = subprocess.run(
            ["pg_dump", "--version"],
            capture_output=True,
            timeout=_VERSION_CHECK_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PgDumpError(f"pg_dump --version failed: {exc}") from exc
    if result.returncode != 0:
        raise PgDumpError(
            "pg_dump --version exited non-zero",
            stderr_tail=_decode_stderr_tail(result.stderr),
        )


def dump_destination(tmp_dir: str, run_id: str) -> str:
    """The temp file path `run_pg_dump` writes to for a given run -- exposed so
    callers can locate (and clean up) that path even when `run_pg_dump` raises
    before returning a `PgDumpResult`."""
    return os.path.join(tmp_dir, f"gains-{run_id}.dump")


def run_pg_dump(
    database_url: str,
    tmp_dir: str,
    timeout_ms: int,
    run_id: str,
    log: logging.LoggerAdapter,
) -> PgDumpResult:
    dest = dump_destination(tmp_dir, run_id)
    args = ["pg_dump", "-Fc", "--no-owner", "--no-privileges", f"--file={dest}", database_url]

    log.debug("starting pg_dump", extra={"tmp_dir": tmp_dir})
    start = time.monotonic()
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout_ms / 1000)
    except subprocess.TimeoutExpired as exc:
        raise PgDumpError(f"pg_dump timed out after {timeout_ms}ms") from exc
    duration_ms = int((time.monotonic() - start) * 1000)

    if result.returncode != 0:
        raise PgDumpError(
            f"pg_dump exited with code {result.returncode}",
            stderr_tail=_decode_stderr_tail(result.stderr),
        )

    dump_bytes = os.stat(dest).st_size
    log.info(
        "pg_dump completed",
        extra={"dump_bytes": dump_bytes, "duration_ms": duration_ms},
    )
    return PgDumpResult(file_path=dest, dump_bytes=dump_bytes, duration_ms=duration_ms)
