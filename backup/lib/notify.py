"""Per-run email notification for the backup service.

Mirrors `scraper/lib/notify.js`'s design decisions — not its code: the never-
throws contract on `send_run_summary`, the recipient-parsing/classification
rules, the failure taxonomy (no-recipients is INFO, everything past that is
ERROR-and-swallowed), the "always" vs. "failure" notify policy, and the
verdict-first subject line. The summary shape is this service's own (dump/
upload figures, not schools/assessment-funnel data) — see
`docs/backup-service-technical-plan.md` Section 1.

WHY A RESEND OUTAGE MUST NEVER SURFACE HERE: `backup.py` calls
`send_run_summary()` from its own `finally` block so the email fires on every
exit path, including ones where an exception is already in flight. If this
function raised, it would replace the run's real outcome with a notification
failure and the operator would never learn the backup itself succeeded or
failed.
"""

import logging
import re
from typing import Any

import httpx

from lib.config import get_settings
from lib.logger import redact

RESEND_ENDPOINT = "https://api.resend.com/emails"

_ADDRESS_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ANGLE_ADDR_RE = re.compile(r"[^,;]*<([^>]+)>")

_CLEANUP_LABEL = "Cleanup:            "


def split_recipients(raw: str) -> list[str]:
    """Split a recipient list. Commas/semicolons/whitespace separate, except
    inside a `Name <addr>` form, which is split off first so a display name
    is not shredded into bogus tokens."""
    angled: list[str] = []

    def _capture(match: re.Match[str]) -> str:
        angled.append(match.group(1).strip())
        return ""

    rest = _ANGLE_ADDR_RE.sub(_capture, raw)
    tokens = angled + re.split(r"[,;\s]+", rest)
    return [t.strip() for t in tokens if t.strip()]


def is_address(value: str) -> bool:
    # Deliberately loose: enough to catch a stray word or a missing @, without
    # implementing RFC 5322. Bounded so one very long token can't be pathological.
    return len(value) <= 320 and bool(_ADDRESS_RE.match(value))


def classify_recipients(raw: str) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    invalid: list[str] = []
    for token in split_recipients(raw) if raw else []:
        (valid if is_address(token) else invalid).append(token)
    return valid, invalid


def overall_status(summary: dict[str, Any]) -> str:
    fatal_error = summary.get("fatal_error")
    if not fatal_error:
        return "OK"
    # A tagged pg_dump/upload failure is an expected, named failure mode of the
    # run itself (FAILED); anything else — preflight, or a truly unhandled
    # exception with no stage — means the run aborted somewhere the plan didn't
    # account for (FATAL).
    stage = fatal_error.get("stage") if isinstance(fatal_error, dict) else None
    if stage in ("pg_dump", "upload"):
        return "FAILED"
    return "FATAL"


def _database_host(summary: dict[str, Any]) -> str:
    return str(summary.get("database_host") or "?")


def _human_bytes(num_bytes: Any) -> str:
    if not isinstance(num_bytes, (int, float)) or isinstance(num_bytes, bool):
        return "n/a"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _format_duration(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value if value is not None else 0)


def _cleanup_line(cleanup: dict[str, Any] | None, retention_count: Any) -> str:
    if cleanup is None:
        return f"{_CLEANUP_LABEL}not attempted"
    list_error = cleanup.get("list_error")
    if list_error:
        return f"{_CLEANUP_LABEL}FAILED to list old backups: {list_error}"
    errors = cleanup.get("errors") or []
    deleted = cleanup.get("deleted") or []
    remaining = cleanup.get("remaining")
    if errors:
        keys = ", ".join(str(e.get("key")) for e in errors)
        line = f"{_CLEANUP_LABEL}FAILED to delete {len(errors)} old backup(s): {keys}"
        if deleted:
            line += f" (deleted {len(deleted)} other(s) successfully)"
        if remaining is not None:
            line += (
                f" — {remaining} backup(s) now in R2 "
                f"(retry needed to reach the {retention_count}-backup limit)"
            )
        return line
    if deleted:
        return (
            f"{_CLEANUP_LABEL}deleted {len(deleted)} old backup(s) to stay within the "
            f"{retention_count}-backup limit — {remaining} backup(s) now in R2"
        )
    return (
        f"{_CLEANUP_LABEL}nothing to delete — {remaining} of {retention_count} "
        "backup(s) kept (within limit)"
    )


def build_subject(summary: dict[str, Any]) -> str:
    status = overall_status(summary)
    dump_bytes_human = _human_bytes(summary.get("dump_bytes"))
    duration = _format_duration(summary.get("duration_sec"))
    suffix = " (dry-run)" if summary.get("dry_run") else ""
    return f"[GAINS backup] {status} — {dump_bytes_human} — {duration}s{suffix}"


def build_body(summary: dict[str, Any]) -> str:
    status = overall_status(summary)
    lines = [
        f"Status:      {status}",
        f"Run id:      {summary.get('run_id', '?')}",
        f"Started:     {summary.get('started_at', '?')}",
        f"Duration:    {_format_duration(summary.get('duration_sec'))}s",
        f"Mode:        {'dry-run (no dump/upload)' if summary.get('dry_run') else 'live'}",
        f"Database:    {_database_host(summary)}",
        f"Retention:   keep last {summary.get('retention_count', '?')} backup(s)",
        "",
    ]

    fatal_error = summary.get("fatal_error")
    if fatal_error:
        lines.append("FATAL — the run aborted before completing:")
        name = fatal_error.get("name", "?") if isinstance(fatal_error, dict) else "?"
        message = (
            fatal_error.get("message", "?") if isinstance(fatal_error, dict) else str(fatal_error)
        )
        lines.append(f"  {name}: {message}")
        stderr_tail = fatal_error.get("stderr_tail") if isinstance(fatal_error, dict) else None
        if stderr_tail:
            lines.append("")
            lines.append("  pg_dump stderr (tail):")
            lines.append(str(stderr_tail))
        lines.append(f"{_CLEANUP_LABEL}skipped (backup did not complete successfully)")
        lines.append("")
    elif summary.get("dry_run"):
        lines.append(f"{_CLEANUP_LABEL}skipped (dry-run)")
        lines.append("")

    if not summary.get("dry_run") and not fatal_error:
        lines.append(f"Dump size:          {_human_bytes(summary.get('dump_bytes'))}")
        lines.append(f"Dump duration:      {_format_duration(summary.get('dump_duration_sec'))}s")
        lines.append(f"Upload duration:    {_format_duration(summary.get('upload_duration_sec'))}s")
        lines.append(f"R2 bucket:          {summary.get('r2_bucket', '?')}")
        lines.append(f"R2 key:             {summary.get('r2_key', '?')}")
        lines.append(_cleanup_line(summary.get("cleanup"), summary.get("retention_count", "?")))
        lines.append("")

    return "\n".join(lines)


def send_run_summary(summary: dict[str, Any], log: logging.LoggerAdapter) -> dict[str, Any]:  # type: ignore[type-arg]
    try:
        settings = get_settings()
    except Exception as exc:
        log.error(
            "run-summary email NOT sent: configuration failed to load",
            extra={"error": redact(str(exc))},
        )
        return {"sent": False, "reason": "config error"}

    valid, invalid = classify_recipients(settings.backup_notify_emails)
    if invalid:
        log.warning(
            "ignoring malformed entries in BACKUP_NOTIFY_EMAILS",
            extra={"ignored": ",".join(invalid)},
        )

    if not valid:
        # Not an error: notification is opt-in. Say so once so an operator who
        # EXPECTED mail can see why none arrived.
        log.info(
            "no run-summary email sent: BACKUP_NOTIFY_EMAILS is unset or has no valid addresses"
        )
        return {"sent": False, "reason": "no recipients"}

    # Deriving the status walks caller-supplied summary data, so it runs inside
    # its own try — a malformed summary must still produce SOME notification
    # attempt, not an exception out of a function documented as never throwing.
    try:
        status = overall_status(summary)
    except Exception as exc:
        log.error(
            "could not derive run status for the notification email",
            extra={"error": redact(str(exc))},
        )
        status = "UNKNOWN"

    notify_on = (settings.backup_notify_on or "always").strip().lower()
    if notify_on == "failure" and status == "OK":
        log.info(
            "run-summary email suppressed by BACKUP_NOTIFY_ON=failure", extra={"status": status}
        )
        return {"sent": False, "reason": "suppressed by policy"}

    if not settings.resend_api_key or not settings.backup_notify_from:
        # Recipients were configured but the transport was not — that IS a
        # misconfiguration and must be loud, or alerts silently never arrive.
        missing = "RESEND_API_KEY" if not settings.resend_api_key else "BACKUP_NOTIFY_FROM"
        log.error(
            f"run-summary email NOT sent: recipients are configured but {missing} is missing",
            extra={"recipients": len(valid)},
        )
        return {"sent": False, "reason": "transport not configured"}

    try:
        subject = redact(build_subject(summary))
        text = redact(build_body(summary))
    except Exception as exc:
        # A summary that can't be rendered must still produce an alert — a bare
        # "the run finished with status X and the report broke" beats silence.
        log.error(
            "could not render the run-summary email; sending a minimal fallback",
            extra={"error": redact(str(exc))},
        )
        subject = f"[GAINS backup] {status} — summary could not be rendered"
        text = (
            f"Run {summary.get('run_id', '(unknown)')} finished with status {status}, but the "
            f"summary could not be rendered: {exc}\n\nCheck the run log directly."
        )

    payload = {"from": settings.backup_notify_from, "to": valid, "subject": subject, "text": text}

    try:
        response = httpx.post(
            RESEND_ENDPOINT,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15.0,
        )
    except Exception as exc:
        # Swallowed by design: a mail outage must not change the run's verdict.
        log.error(
            "run-summary email failed to send",
            extra={"error": redact(str(exc)), "recipients": len(valid)},
        )
        return {"sent": False, "reason": type(exc).__name__ or "send failed"}

    if response.status_code < 200 or response.status_code >= 300:
        log.error(
            "run-summary email rejected by provider",
            extra={"status": response.status_code, "body": redact(response.text[:200])},
        )
        return {"sent": False, "reason": f"provider {response.status_code}"}

    log.info("run-summary email sent", extra={"recipients": len(valid), "status": status})
    return {"sent": True, "reason": None}
