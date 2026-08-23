"""Tests for lib/logger.py — no network, no real credentials."""

import json

from lib.logger import redact, setup_logging


def test_level_filtering_suppresses_below_configured_level(capsys):
    log = setup_logging(run_id="run-1", level="info")
    log.debug("should not appear")
    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""


def test_debug_and_info_go_to_stdout(capsys):
    log = setup_logging(run_id="run-2", level="debug")
    log.debug("debug message")
    log.info("info message")
    out, err = capsys.readouterr()
    assert err == ""
    lines = [line for line in out.strip().splitlines() if line]
    assert len(lines) == 2
    levels = {json.loads(line)["level"] for line in lines}
    assert levels == {"DEBUG", "INFO"}


def test_warning_and_error_go_to_stderr(capsys):
    log = setup_logging(run_id="run-3", level="info")
    log.warning("warning message")
    log.error("error message")
    out, err = capsys.readouterr()
    assert out == ""
    lines = [line for line in err.strip().splitlines() if line]
    assert len(lines) == 2
    levels = {json.loads(line)["level"] for line in lines}
    assert levels == {"WARNING", "ERROR"}


def test_run_id_present_on_every_emitted_record(capsys):
    log = setup_logging(run_id="run-xyz", level="debug")
    log.debug("d")
    log.info("i")
    log.warning("w")
    log.error("e")
    out, err = capsys.readouterr()
    records = [json.loads(line) for line in (out + err).strip().splitlines() if line]
    assert len(records) == 4
    assert all(record["run_id"] == "run-xyz" for record in records)


def test_json_line_shape_and_extra_fields(capsys):
    log = setup_logging(run_id="run-shape", level="info")
    log.info("hello", extra={"dump_bytes": 123})
    out, _ = capsys.readouterr()
    record = json.loads(out.strip())
    assert record["message"] == "hello"
    assert record["logger"] == "backup"
    assert record["level"] == "INFO"
    assert record["run_id"] == "run-shape"
    assert record["dump_bytes"] == 123
    assert "timestamp" in record


def test_redact_masks_connection_string_password():
    text = "postgresql://myuser:sup3rSecret@db.example.com:5432/gains"
    masked = redact(text)
    assert "sup3rSecret" not in masked
    assert "myuser" in masked
    assert "db.example.com" in masked


def test_redact_masks_api_key():
    text = 'config: {"api_key": "sk_live_abcdef1234567890"}'
    masked = redact(text)
    assert "sk_live_abcdef1234567890" not in masked


def test_redact_masks_jwt_looking_token():
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    masked = redact(f"Authorization: Bearer {jwt}")
    assert jwt not in masked
    assert "<jwt>" in masked


def test_redact_leaves_non_secret_text_untouched():
    text = "backup completed in 12.3s, dump_bytes=104857600"
    assert redact(text) == text


def test_message_itself_is_redacted(capsys):
    log = setup_logging(run_id="run-msg", level="info")
    log.info("connecting to postgresql://myuser:sup3rSecret@db.example.com/gains")
    out, _ = capsys.readouterr()
    record = json.loads(out.strip())
    assert "sup3rSecret" not in record["message"]
