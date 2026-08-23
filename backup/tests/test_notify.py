"""Tests for lib/notify.py.

No real network calls: every test that reaches the send path monkeypatches
`httpx.post`. Every test that reaches `get_settings()` sets the required
non-notify env vars too, since `Settings` validates the whole environment
(database_url, r2_*) even though notify only cares about the BACKUP_NOTIFY_*
subset.
"""

import logging
from typing import Any

import httpx
import pytest

from lib import notify


class _FakeLogAdapter(logging.LoggerAdapter):  # type: ignore[type-arg]
    def __init__(self) -> None:
        super().__init__(logging.getLogger("test"), {"run_id": "test-run"})
        self.records: list[tuple[str, str, dict[str, Any]]] = []

    def _record(self, level: str, msg: object, extra: dict[str, Any] | None) -> None:
        self.records.append((level, str(msg), dict(extra or {})))

    def info(self, msg: object, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        self._record("info", msg, kwargs.get("extra"))

    def warning(self, msg: object, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        self._record("warning", msg, kwargs.get("extra"))

    def error(self, msg: object, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        self._record("error", msg, kwargs.get("extra"))


@pytest.fixture
def log() -> _FakeLogAdapter:
    return _FakeLogAdapter()


@pytest.fixture
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@pooler.example.com:5432/postgres")
    monkeypatch.setenv("R2_ACCOUNT_ID", "acct123")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key123")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret123")
    monkeypatch.setenv("R2_BUCKET", "gains-platform-backups")
    monkeypatch.delenv("BACKUP_NOTIFY_EMAILS", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("BACKUP_NOTIFY_FROM", raising=False)
    monkeypatch.setenv("BACKUP_NOTIFY_ON", "always")


def _configure_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKUP_NOTIFY_EMAILS", "ops@x.com")
    monkeypatch.setenv("RESEND_API_KEY", "re_abc123")
    monkeypatch.setenv("BACKUP_NOTIFY_FROM", "backup@x.com")


def _ok_summary(**overrides: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "run_id": "abc-123",
        "started_at": "2026-08-23T09:00:00+00:00",
        "duration_sec": 42.5,
        "dry_run": False,
        "database_host": "pooler.example.com",
        "dump_bytes": 1024 * 1024 * 12,
        "dump_duration_sec": 10.0,
        "upload_duration_sec": 5.0,
        "r2_bucket": "gains-platform-backups",
        "r2_key": "backups/2026-08-23/gains-platform-abc-123.dump",
        "fatal_error": None,
        "retention_count": 3,
    }
    summary.update(overrides)
    return summary


class TestSplitRecipients:
    def test_splits_on_comma_semicolon_whitespace(self) -> None:
        assert notify.split_recipients("a@x.com, b@x.com; c@x.com  d@x.com") == [
            "a@x.com",
            "b@x.com",
            "c@x.com",
            "d@x.com",
        ]

    def test_unwraps_display_name_form(self) -> None:
        assert notify.split_recipients("Ops Team <ops@x.com>") == ["ops@x.com"]

    def test_mixed_plain_and_display_name(self) -> None:
        result = notify.split_recipients("a@x.com, Ops <ops@x.com>")
        assert set(result) == {"a@x.com", "ops@x.com"}

    def test_empty_string_yields_nothing(self) -> None:
        assert notify.split_recipients("") == []


class TestIsAddress:
    def test_valid_address(self) -> None:
        assert notify.is_address("person@example.com") is True

    def test_missing_at_sign(self) -> None:
        assert notify.is_address("not-an-address") is False

    def test_missing_domain_dot(self) -> None:
        assert notify.is_address("person@localhost") is False

    def test_too_long_is_rejected(self) -> None:
        long_local = "a" * 315
        assert notify.is_address(f"{long_local}@x.com") is False


class TestClassifyRecipients:
    def test_splits_valid_and_invalid(self) -> None:
        valid, invalid = notify.classify_recipients("good@x.com, not-an-address, also-bad")
        assert valid == ["good@x.com"]
        assert invalid == ["not-an-address", "also-bad"]

    def test_all_valid(self) -> None:
        valid, invalid = notify.classify_recipients("a@x.com;b@x.com")
        assert valid == ["a@x.com", "b@x.com"]
        assert invalid == []

    def test_empty_raw_yields_two_empty_lists(self) -> None:
        assert notify.classify_recipients("") == ([], [])


class TestOverallStatus:
    def test_ok_when_no_fatal_error(self) -> None:
        assert notify.overall_status(_ok_summary()) == "OK"

    def test_failed_for_pg_dump_stage(self) -> None:
        summary = _ok_summary(
            fatal_error={"name": "PgDumpError", "message": "boom", "stage": "pg_dump"}
        )
        assert notify.overall_status(summary) == "FAILED"

    def test_failed_for_upload_stage(self) -> None:
        summary = _ok_summary(
            fatal_error={"name": "TimeoutError", "message": "boom", "stage": "upload"}
        )
        assert notify.overall_status(summary) == "FAILED"

    def test_fatal_for_preflight_stage(self) -> None:
        summary = _ok_summary(
            fatal_error={"name": "RuntimeError", "message": "boom", "stage": "preflight"}
        )
        assert notify.overall_status(summary) == "FATAL"

    def test_fatal_for_unstaged_error(self) -> None:
        summary = _ok_summary(fatal_error={"name": "RuntimeError", "message": "boom"})
        assert notify.overall_status(summary) == "FATAL"


class TestNoRecipients(object):
    def test_unset_emails_is_info_not_error(
        self, base_env: None, log: _FakeLogAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = notify.send_run_summary(_ok_summary(), log)
        assert result == {"sent": False, "reason": "no recipients"}
        levels = [level for level, _, _ in log.records]
        assert "info" in levels
        assert "error" not in levels

    def test_only_malformed_emails_still_info_not_error(
        self, base_env: None, log: _FakeLogAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BACKUP_NOTIFY_EMAILS", "not-an-address")
        result = notify.send_run_summary(_ok_summary(), log)
        assert result == {"sent": False, "reason": "no recipients"}
        levels = [level for level, _, _ in log.records]
        assert "warning" in levels
        assert "error" not in levels


class TestMissingTransport:
    def test_missing_resend_api_key(
        self, base_env: None, log: _FakeLogAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BACKUP_NOTIFY_EMAILS", "ops@x.com")
        monkeypatch.setenv("BACKUP_NOTIFY_FROM", "backup@x.com")
        result = notify.send_run_summary(_ok_summary(), log)
        assert result == {"sent": False, "reason": "transport not configured"}
        assert any(level == "error" for level, _, _ in log.records)

    def test_missing_notify_from(
        self, base_env: None, log: _FakeLogAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BACKUP_NOTIFY_EMAILS", "ops@x.com")
        monkeypatch.setenv("RESEND_API_KEY", "re_abc123")
        result = notify.send_run_summary(_ok_summary(), log)
        assert result == {"sent": False, "reason": "transport not configured"}
        assert any(level == "error" for level, _, _ in log.records)


class TestNotifyOnPolicy:
    def test_failure_policy_suppresses_ok_run(
        self, base_env: None, log: _FakeLogAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_transport(monkeypatch)
        monkeypatch.setenv("BACKUP_NOTIFY_ON", "failure")

        def _unexpected_post(*args: object, **kwargs: object) -> httpx.Response:
            raise AssertionError("httpx.post should not be called when suppressed")

        monkeypatch.setattr(httpx, "post", _unexpected_post)
        result = notify.send_run_summary(_ok_summary(), log)
        assert result == {"sent": False, "reason": "suppressed by policy"}

    def test_failure_policy_still_sends_failed_run(
        self, base_env: None, log: _FakeLogAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_transport(monkeypatch)
        monkeypatch.setenv("BACKUP_NOTIFY_ON", "failure")
        monkeypatch.setattr(
            httpx, "post", lambda *a, **k: httpx.Response(200, json={"id": "email_1"})
        )
        summary = _ok_summary(
            fatal_error={"name": "PgDumpError", "message": "boom", "stage": "pg_dump"}
        )
        result = notify.send_run_summary(summary, log)
        assert result == {"sent": True, "reason": None}

    def test_always_policy_sends_ok_run(
        self, base_env: None, log: _FakeLogAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_transport(monkeypatch)
        monkeypatch.setenv("BACKUP_NOTIFY_ON", "always")
        monkeypatch.setattr(
            httpx, "post", lambda *a, **k: httpx.Response(200, json={"id": "email_1"})
        )
        result = notify.send_run_summary(_ok_summary(), log)
        assert result == {"sent": True, "reason": None}


class TestProviderRejection:
    def test_non_2xx_response_is_swallowed(
        self, base_env: None, log: _FakeLogAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_transport(monkeypatch)
        monkeypatch.setattr(
            httpx, "post", lambda *a, **k: httpx.Response(422, text="invalid from address")
        )
        result = notify.send_run_summary(_ok_summary(), log)
        assert result["sent"] is False
        assert result["reason"] == "provider 422"
        assert any(level == "error" for level, _, _ in log.records)


class TestNetworkError:
    def test_connect_error_is_swallowed(
        self, base_env: None, log: _FakeLogAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_transport(monkeypatch)

        def _raise(*args: object, **kwargs: object) -> httpx.Response:
            raise httpx.ConnectTimeout("connection timed out")

        monkeypatch.setattr(httpx, "post", _raise)
        result = notify.send_run_summary(_ok_summary(), log)
        assert result["sent"] is False
        assert result["reason"] == "ConnectTimeout"
        assert any(level == "error" for level, _, _ in log.records)


class TestSendPayload:
    def test_sends_expected_payload_shape(
        self, base_env: None, log: _FakeLogAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BACKUP_NOTIFY_EMAILS", "ops@x.com, second@x.com")
        monkeypatch.setenv("RESEND_API_KEY", "re_abc123")
        monkeypatch.setenv("BACKUP_NOTIFY_FROM", "backup@x.com")
        captured: dict[str, Any] = {}

        def _fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["timeout"] = timeout
            return httpx.Response(200, json={"id": "email_1"})

        monkeypatch.setattr(httpx, "post", _fake_post)
        result = notify.send_run_summary(_ok_summary(), log)

        assert result == {"sent": True, "reason": None}
        assert captured["url"] == notify.RESEND_ENDPOINT
        assert captured["headers"]["Authorization"] == "Bearer re_abc123"
        assert captured["json"]["from"] == "backup@x.com"
        assert captured["json"]["to"] == ["ops@x.com", "second@x.com"]
        assert captured["json"]["subject"].startswith("[GAINS backup] OK")
        assert captured["timeout"] == 15.0

    def test_redacts_secrets_from_subject_and_body(
        self, base_env: None, log: _FakeLogAdapter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_transport(monkeypatch)
        captured: dict[str, Any] = {}

        def _fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            captured["json"] = json
            return httpx.Response(200, json={"id": "email_1"})

        monkeypatch.setattr(httpx, "post", _fake_post)
        summary = _ok_summary(
            fatal_error={
                "name": "RuntimeError",
                "message": "connection failed: postgresql://user:sup3rSecret@host:5432/db",
                "stage": "preflight",
            }
        )
        notify.send_run_summary(summary, log)
        assert "sup3rSecret" not in captured["json"]["text"]


class TestDryRunSuffix:
    def test_subject_marks_dry_run(self) -> None:
        subject = notify.build_subject(_ok_summary(dry_run=True))
        assert subject.endswith("(dry-run)")

    def test_subject_has_no_suffix_for_live_run(self) -> None:
        subject = notify.build_subject(_ok_summary(dry_run=False))
        assert not subject.endswith("(dry-run)")


class TestRetentionLine:
    def test_present_on_dry_run(self) -> None:
        body = notify.build_body(_ok_summary(dry_run=True, retention_count=3))
        assert "Retention:   keep last 3 backup(s)" in body

    def test_present_on_fatal_error(self) -> None:
        summary = _ok_summary(
            retention_count=3,
            fatal_error={"name": "PgDumpError", "message": "boom", "stage": "pg_dump"},
        )
        body = notify.build_body(summary)
        assert "Retention:   keep last 3 backup(s)" in body

    def test_present_on_success(self) -> None:
        body = notify.build_body(_ok_summary(retention_count=3))
        assert "Retention:   keep last 3 backup(s)" in body

    def test_falls_back_to_question_mark_when_missing(self) -> None:
        summary = _ok_summary()
        del summary["retention_count"]
        body = notify.build_body(summary)
        assert "Retention:   keep last ? backup(s)" in body


class TestCleanupLine:
    def test_dry_run_reports_skipped(self) -> None:
        body = notify.build_body(_ok_summary(dry_run=True))
        assert "Cleanup:            skipped (dry-run)" in body

    def test_fatal_error_reports_skipped(self) -> None:
        summary = _ok_summary(
            fatal_error={"name": "PgDumpError", "message": "boom", "stage": "pg_dump"}
        )
        body = notify.build_body(summary)
        assert "Cleanup:            skipped (backup did not complete successfully)" in body

    def test_cleanup_none_reports_not_attempted(self) -> None:
        body = notify.build_body(_ok_summary(cleanup=None))
        assert "Cleanup:            not attempted" in body

    def test_list_error_reported(self) -> None:
        cleanup = {
            "attempted": True,
            "deleted": [],
            "errors": [],
            "list_error": "AccessDenied",
            "remaining": None,
        }
        body = notify.build_body(_ok_summary(cleanup=cleanup))
        assert "Cleanup:            FAILED to list old backups: AccessDenied" in body

    def test_delete_errors_without_successes(self) -> None:
        cleanup = {
            "attempted": True,
            "deleted": [],
            "errors": [{"key": "backups/2026-08-01/old.dump", "error": "AccessDenied"}],
            "list_error": None,
            "remaining": 3,
        }
        body = notify.build_body(_ok_summary(cleanup=cleanup, retention_count=3))
        assert (
            "Cleanup:            FAILED to delete 1 old backup(s): "
            "backups/2026-08-01/old.dump — 3 backup(s) now in R2 "
            "(retry needed to reach the 3-backup limit)" in body
        )

    def test_delete_errors_with_some_successes(self) -> None:
        cleanup = {
            "attempted": True,
            "deleted": ["backups/2026-08-02/ok.dump"],
            "errors": [{"key": "backups/2026-08-01/old.dump", "error": "AccessDenied"}],
            "list_error": None,
            "remaining": 2,
        }
        body = notify.build_body(_ok_summary(cleanup=cleanup, retention_count=3))
        assert (
            "Cleanup:            FAILED to delete 1 old backup(s): "
            "backups/2026-08-01/old.dump (deleted 1 other(s) successfully) — "
            "2 backup(s) now in R2 (retry needed to reach the 3-backup limit)" in body
        )

    def test_deleted_successfully_reported(self) -> None:
        cleanup = {
            "attempted": True,
            "deleted": ["backups/2026-08-01/old.dump", "backups/2026-08-02/older.dump"],
            "errors": [],
            "list_error": None,
            "remaining": 3,
        }
        body = notify.build_body(_ok_summary(cleanup=cleanup, retention_count=3))
        assert (
            "Cleanup:            deleted 2 old backup(s) to stay within the 3-backup limit — "
            "3 backup(s) now in R2" in body
        )

    def test_nothing_to_delete_reported(self) -> None:
        cleanup = {
            "attempted": True,
            "deleted": [],
            "errors": [],
            "list_error": None,
            "remaining": 2,
        }
        body = notify.build_body(_ok_summary(cleanup=cleanup, retention_count=3))
        assert (
            "Cleanup:            nothing to delete — 2 of 3 backup(s) kept (within limit)" in body
        )
