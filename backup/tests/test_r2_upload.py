from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import boto3
import pytest
from botocore.config import Config
from botocore.stub import ANY, Stubber

from lib import r2_upload


@dataclass
class FakeSettings:
    r2_account_id: str = "test-account"
    r2_access_key_id: str = "test-key-id"
    r2_secret_access_key: str = "test-secret"
    r2_bucket: str = "test-bucket"
    r2_backup_prefix: str = "backups/"


@pytest.fixture
def log() -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logging.getLogger("test-r2-upload"), {})


def _make_stubbed_client() -> tuple[object, Stubber]:
    # Mirrors r2_upload._build_client's Config so the checksum-header
    # suppression is exercised the same way it is in production.
    client = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="dummy",
        aws_secret_access_key="dummy",
        config=Config(
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
    return client, Stubber(client)


def test_upload_dump_uses_correct_bucket_and_dated_key(
    tmp_path: Path, log: logging.LoggerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    dump_file = tmp_path / "gains-run123.dump"
    dump_file.write_bytes(b"fake-dump-contents")

    client, stubber = _make_stubbed_client()
    today = datetime.now(timezone.utc).date()
    expected_key = f"backups/{today:%Y-%m-%d}/gains-platform-run123.dump"
    stubber.add_response(
        "put_object",
        {},
        expected_params={"Bucket": "test-bucket", "Key": expected_key, "Body": ANY},
    )
    stubber.activate()
    monkeypatch.setattr(r2_upload, "_build_client", lambda settings, timeout_ms: client)

    result = r2_upload.upload_dump(
        str(dump_file), "run123", FakeSettings(), timeout_ms=5_000, log=log
    )

    stubber.assert_no_pending_responses()
    assert result == {
        "r2_bucket": "test-bucket",
        "r2_key": expected_key,
        "upload_duration_sec": result["upload_duration_sec"],
    }
    assert isinstance(result["upload_duration_sec"], float)


def test_upload_dump_raises_timeout_when_upload_hangs(
    tmp_path: Path, log: logging.LoggerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    dump_file = tmp_path / "gains-run456.dump"
    dump_file.write_bytes(b"fake-dump-contents")

    class SlowClient:
        def upload_file(self, *_args: object, **_kwargs: object) -> None:
            time.sleep(2)

    monkeypatch.setattr(r2_upload, "_build_client", lambda settings, timeout_ms: SlowClient())

    with pytest.raises(TimeoutError, match="timed out"):
        r2_upload.upload_dump(str(dump_file), "run456", FakeSettings(), timeout_ms=50, log=log)


def test_upload_dump_reraises_underlying_upload_error(
    tmp_path: Path, log: logging.LoggerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    dump_file = tmp_path / "gains-run789.dump"
    dump_file.write_bytes(b"fake-dump-contents")

    class FailingClient:
        def upload_file(self, *_args: object, **_kwargs: object) -> None:
            raise ValueError("boom")

    monkeypatch.setattr(r2_upload, "_build_client", lambda settings, timeout_ms: FailingClient())

    with pytest.raises(ValueError, match="boom"):
        r2_upload.upload_dump(str(dump_file), "run789", FakeSettings(), timeout_ms=5_000, log=log)


def test_check_bucket_access_raises_runtime_error_on_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, stubber = _make_stubbed_client()
    stubber.add_client_error(
        "head_bucket",
        service_error_code="404",
        service_message="Not Found",
        http_status_code=404,
    )
    stubber.activate()
    monkeypatch.setattr(r2_upload, "_build_client", lambda settings, timeout_ms: client)

    with pytest.raises(RuntimeError, match="test-bucket"):
        r2_upload.check_bucket_access(FakeSettings())

    stubber.assert_no_pending_responses()


def test_check_bucket_access_succeeds_when_bucket_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, stubber = _make_stubbed_client()
    stubber.add_response("head_bucket", {}, expected_params={"Bucket": "test-bucket"})
    stubber.activate()
    monkeypatch.setattr(r2_upload, "_build_client", lambda settings, timeout_ms: client)

    r2_upload.check_bucket_access(FakeSettings())

    stubber.assert_no_pending_responses()


def test_list_backup_keys_returns_keys_sorted_oldest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, stubber = _make_stubbed_client()
    stubber.add_response(
        "list_objects_v2",
        {
            "Contents": [
                {
                    "Key": "backups/2026-08-22/gains-platform-b.dump",
                    "LastModified": datetime(2026, 8, 22, tzinfo=timezone.utc),
                    "Size": 10,
                },
                {
                    "Key": "backups/2026-08-20/gains-platform-a.dump",
                    "LastModified": datetime(2026, 8, 20, tzinfo=timezone.utc),
                    "Size": 10,
                },
                {
                    "Key": "backups/2026-08-23/gains-platform-c.dump",
                    "LastModified": datetime(2026, 8, 23, tzinfo=timezone.utc),
                    "Size": 10,
                },
            ],
            "KeyCount": 3,
        },
        expected_params={"Bucket": "test-bucket", "Prefix": "backups/"},
    )
    stubber.activate()
    monkeypatch.setattr(r2_upload, "_build_client", lambda settings, timeout_ms: client)

    result = r2_upload.list_backup_keys(FakeSettings())

    assert result == [
        "backups/2026-08-20/gains-platform-a.dump",
        "backups/2026-08-22/gains-platform-b.dump",
        "backups/2026-08-23/gains-platform-c.dump",
    ]
    stubber.assert_no_pending_responses()


def test_list_backup_keys_returns_empty_list_when_no_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, stubber = _make_stubbed_client()
    stubber.add_response(
        "list_objects_v2",
        {"KeyCount": 0},
        expected_params={"Bucket": "test-bucket", "Prefix": "backups/"},
    )
    stubber.activate()
    monkeypatch.setattr(r2_upload, "_build_client", lambda settings, timeout_ms: client)

    result = r2_upload.list_backup_keys(FakeSettings())

    assert result == []
    stubber.assert_no_pending_responses()


def _stub_list_objects(stubber: Stubber, keys: list[str]) -> None:
    stubber.add_response(
        "list_objects_v2",
        {
            "Contents": [
                {
                    "Key": key,
                    "LastModified": datetime(2026, 8, 20 + i, tzinfo=timezone.utc),
                    "Size": 10,
                }
                for i, key in enumerate(keys)
            ],
            "KeyCount": len(keys),
        },
        expected_params={"Bucket": "test-bucket", "Prefix": "backups/"},
    )


def test_prune_old_backups_deletes_only_oldest_excess(
    log: logging.LoggerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    keys = [
        "backups/2026-08-20/a.dump",
        "backups/2026-08-21/b.dump",
        "backups/2026-08-22/c.dump",
        "backups/2026-08-23/d.dump",
    ]
    client, stubber = _make_stubbed_client()
    _stub_list_objects(stubber, keys)
    stubber.add_response(
        "delete_object", {}, expected_params={"Bucket": "test-bucket", "Key": keys[0]}
    )
    stubber.add_response(
        "delete_object", {}, expected_params={"Bucket": "test-bucket", "Key": keys[1]}
    )
    stubber.activate()

    build_calls = 0

    def _build_client_once(settings: object, timeout_ms: int) -> object:
        nonlocal build_calls
        build_calls += 1
        return client

    monkeypatch.setattr(r2_upload, "_build_client", _build_client_once)

    result = r2_upload.prune_old_backups(FakeSettings(), keep=2, log=log)

    assert result == {
        "attempted": True,
        "deleted": [keys[0], keys[1]],
        "errors": [],
        "list_error": None,
        "remaining": 2,
    }
    # One client for the whole operation, reused for both the list and the
    # deletes -- not a second one built just for deleting.
    assert build_calls == 1
    stubber.assert_no_pending_responses()


def test_prune_old_backups_deletes_nothing_when_keys_within_keep(
    log: logging.LoggerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    keys = ["backups/2026-08-22/c.dump", "backups/2026-08-23/d.dump"]
    client, stubber = _make_stubbed_client()
    _stub_list_objects(stubber, keys)
    stubber.activate()
    monkeypatch.setattr(r2_upload, "_build_client", lambda settings, timeout_ms: client)

    result = r2_upload.prune_old_backups(FakeSettings(), keep=3, log=log)

    assert result == {
        "attempted": True,
        "deleted": [],
        "errors": [],
        "list_error": None,
        "remaining": 2,
    }
    # No delete_object was queued -- an unstubbed call would raise here.
    stubber.assert_no_pending_responses()


def test_prune_old_backups_clamps_keep_to_one_never_deletes_newest(
    log: logging.LoggerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    keys = ["backups/2026-08-22/only.dump"]
    client, stubber = _make_stubbed_client()
    _stub_list_objects(stubber, keys)
    stubber.activate()
    monkeypatch.setattr(r2_upload, "_build_client", lambda settings, timeout_ms: client)

    result = r2_upload.prune_old_backups(FakeSettings(), keep=0, log=log)

    assert result == {
        "attempted": True,
        "deleted": [],
        "errors": [],
        "list_error": None,
        "remaining": 1,
    }
    stubber.assert_no_pending_responses()


def test_prune_old_backups_returns_list_error_without_attempting_deletes(
    log: logging.LoggerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, stubber = _make_stubbed_client()
    stubber.add_client_error(
        "list_objects_v2",
        service_error_code="AccessDenied",
        service_message="denied",
        http_status_code=403,
        expected_params={"Bucket": "test-bucket", "Prefix": "backups/"},
    )
    stubber.activate()
    monkeypatch.setattr(r2_upload, "_build_client", lambda settings, timeout_ms: client)

    result = r2_upload.prune_old_backups(FakeSettings(), keep=3, log=log)

    assert result["attempted"] is True
    assert result["deleted"] == []
    assert result["errors"] == []
    assert result["list_error"] is not None
    assert "AccessDenied" in result["list_error"]
    assert result["remaining"] is None
    stubber.assert_no_pending_responses()


def test_prune_old_backups_captures_per_key_delete_failure_without_stopping(
    log: logging.LoggerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    keys = [
        "backups/2026-08-20/a.dump",
        "backups/2026-08-21/b.dump",
        "backups/2026-08-22/c.dump",
    ]
    client, stubber = _make_stubbed_client()
    _stub_list_objects(stubber, keys)
    stubber.add_client_error(
        "delete_object",
        service_error_code="InternalError",
        service_message="boom",
        http_status_code=500,
        expected_params={"Bucket": "test-bucket", "Key": keys[0]},
    )
    stubber.add_response(
        "delete_object", {}, expected_params={"Bucket": "test-bucket", "Key": keys[1]}
    )
    stubber.activate()
    monkeypatch.setattr(r2_upload, "_build_client", lambda settings, timeout_ms: client)

    result = r2_upload.prune_old_backups(FakeSettings(), keep=1, log=log)

    assert result["attempted"] is True
    assert result["deleted"] == [keys[1]]
    assert len(result["errors"]) == 1
    assert result["errors"][0]["key"] == keys[0]
    assert "InternalError" in result["errors"][0]["error"] or "boom" in result["errors"][0]["error"]
    assert result["list_error"] is None
    assert result["remaining"] == 2
    stubber.assert_no_pending_responses()
