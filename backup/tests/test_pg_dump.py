from __future__ import annotations

import os
import subprocess
from typing import Any

import pytest

from lib.pg_dump import PgDumpError, PgDumpResult, run_pg_dump


class _StubLog:
    def debug(self, msg: str, extra: dict[str, Any] | None = None) -> None:
        pass

    def info(self, msg: str, extra: dict[str, Any] | None = None) -> None:
        pass

    def warning(self, msg: str, extra: dict[str, Any] | None = None) -> None:
        pass

    def error(self, msg: str, extra: dict[str, Any] | None = None) -> None:
        pass


@pytest.fixture
def log() -> _StubLog:
    return _StubLog()


def _fake_completed_process(
    args: list[str], returncode: int = 0, stderr: bytes = b""
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=b"", stderr=stderr)


def test_run_pg_dump_invokes_expected_argument_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, log: _StubLog
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(
        args: list[str], capture_output: bool, timeout: float
    ) -> subprocess.CompletedProcess[bytes]:
        captured["args"] = args
        captured["capture_output"] = capture_output
        captured["timeout"] = timeout
        dest = args[4].removeprefix("--file=")
        with open(dest, "wb") as f:
            f.write(b"fake dump contents")
        return _fake_completed_process(args, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    database_url = "postgresql://user:pass@fake-host:5432/gains"
    run_id = "test-run-id"
    run_pg_dump(
        database_url=database_url,
        tmp_dir=str(tmp_path),
        timeout_ms=30_000,
        run_id=run_id,
        log=log,  # type: ignore[arg-type]
    )

    expected_dest = os.path.join(str(tmp_path), f"gains-{run_id}.dump")
    assert captured["args"] == [
        "pg_dump",
        "-Fc",
        "--no-owner",
        "--no-privileges",
        f"--file={expected_dest}",
        database_url,
    ]
    assert captured["capture_output"] is True
    assert captured["timeout"] == pytest.approx(30.0)


def test_run_pg_dump_timeout_raises_pg_dump_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, log: _StubLog
) -> None:
    def fake_run(
        args: list[str], capture_output: bool, timeout: float
    ) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(PgDumpError) as exc_info:
        run_pg_dump(
            database_url="postgresql://user:pass@fake-host:5432/gains",
            tmp_dir=str(tmp_path),
            timeout_ms=50,
            run_id="timeout-run",
            log=log,  # type: ignore[arg-type]
        )

    assert exc_info.value.stage == "pg_dump"
    assert "50ms" in str(exc_info.value)


def test_run_pg_dump_nonzero_exit_captures_stderr_tail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, log: _StubLog
) -> None:
    stderr_bytes = b"x" * 5000 + b"tail marker"

    def fake_run(
        args: list[str], capture_output: bool, timeout: float
    ) -> subprocess.CompletedProcess[bytes]:
        return _fake_completed_process(args, returncode=1, stderr=stderr_bytes)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(PgDumpError) as exc_info:
        run_pg_dump(
            database_url="postgresql://user:pass@fake-host:5432/gains",
            tmp_dir=str(tmp_path),
            timeout_ms=30_000,
            run_id="failing-run",
            log=log,  # type: ignore[arg-type]
        )

    err = exc_info.value
    assert err.stage == "pg_dump"
    assert "1" in str(err)
    expected_tail = stderr_bytes.decode("utf-8")[-4000:]
    assert err.stderr_tail == expected_tail
    assert len(err.stderr_tail) == 4000
    assert err.stderr_tail.endswith("tail marker")


def test_run_pg_dump_result_matches_fixture_file_stat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, log: _StubLog
) -> None:
    run_id = "fixture-run"
    dest = os.path.join(str(tmp_path), f"gains-{run_id}.dump")
    fixture_bytes = b"a" * 12345

    def fake_run(
        args: list[str], capture_output: bool, timeout: float
    ) -> subprocess.CompletedProcess[bytes]:
        with open(dest, "wb") as f:
            f.write(fixture_bytes)
        return _fake_completed_process(args, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_pg_dump(
        database_url="postgresql://user:pass@fake-host:5432/gains",
        tmp_dir=str(tmp_path),
        timeout_ms=30_000,
        run_id=run_id,
        log=log,  # type: ignore[arg-type]
    )

    assert isinstance(result, PgDumpResult)
    assert result.file_path == dest
    assert result.dump_bytes == os.stat(dest).st_size
    assert result.dump_bytes == len(fixture_bytes)
    assert result.duration_ms >= 0
