"""Structured JSON logging for unattended backup runs.

Mirrors `scraper/lib/logger.js`'s design (ISO-8601 UTC timestamps, WARN/ERROR
to stderr so a collector can split streams, a run id bound once and attached
to every line, `redact()` applied before anything reaches a log line) without
sharing code — Python's `logging` module already gives us levels, handlers and
a `LoggerAdapter` for bound context, so there is no `Logger`/`child()` class to
reimplement.
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any, MutableMapping

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

# LogRecord's own attributes — anything else found on a record came from the
# caller's `extra={...}` and belongs in the JSON line's top-level fields.
_STANDARD_RECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
    }
)

_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._-]{10,}")
# `scheme://user:password@host` — mask only the password segment, keep the
# username and host visible since they are useful for debugging.
_CONN_STRING_RE = re.compile(r"(://[^:/\s]+:)([^@/\s]+)(@)")
_KV_SECRET_RE = re.compile(
    r'(?i)((?:password|secret|api[_-]?key|access[_-]?key(?:[_-]?id)?)"?\s*[:=]\s*"?)[^",\s}]+'
)


def redact(text: str) -> str:
    masked = str(text)
    masked = _JWT_RE.sub("<jwt>", masked)
    masked = _CONN_STRING_RE.sub(r"\1<redacted>\3", masked)
    masked = _BEARER_RE.sub(r"\1<redacted>", masked)
    masked = _KV_SECRET_RE.sub(r"\1<redacted>", masked)
    return masked


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _MaxLevelFilter(logging.Filter):
    def __init__(self, below: int) -> None:
        super().__init__()
        self._below = below

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < self._below


class _RunIdLoggerAdapter(logging.LoggerAdapter):  # type: ignore[type-arg]
    def process(
        self, msg: Any, kwargs: MutableMapping[str, Any]
    ) -> tuple[Any, MutableMapping[str, Any]]:
        extra = dict(kwargs.get("extra") or {})
        redacted_extra = {k: (redact(v) if isinstance(v, str) else v) for k, v in extra.items()}
        redacted_extra["run_id"] = self.extra["run_id"]  # type: ignore[index]
        kwargs["extra"] = redacted_extra
        redacted_msg = redact(msg) if isinstance(msg, str) else msg
        return redacted_msg, kwargs


def setup_logging(run_id: str, level: str) -> logging.LoggerAdapter:  # type: ignore[type-arg]
    logger = logging.getLogger("backup")
    logger.setLevel(_LEVELS.get(level.lower(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    formatter = _JSONFormatter()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(_MaxLevelFilter(logging.WARNING))
    stdout_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)

    logger.addHandler(stdout_handler)
    logger.addHandler(stderr_handler)

    return _RunIdLoggerAdapter(logger, {"run_id": run_id})
