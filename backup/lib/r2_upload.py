"""Cloudflare R2 upload — S3-compatible API via boto3.

`settings` is typed against a structural `R2Settings` protocol (rather than
importing `lib.config.Settings` directly) so this module only depends on the
handful of fields it actually reads, not the full app-config shape.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


class R2Settings(Protocol):
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket: str
    r2_backup_prefix: str


# The single source of truth for the retention floor: this mechanism must
# never be able to delete the backup that was just uploaded, which is always
# the newest. backup.py reads this same constant so the number it reports in
# the run-summary email can never drift from what prune_old_backups enforces.
MIN_RETENTION_COUNT = 1


def _build_client(settings: R2Settings, timeout_ms: int) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            connect_timeout=10,
            read_timeout=timeout_ms / 1000,
            # boto3 >=1.36 auto-attaches x-amz-checksum-* headers by default,
            # which R2 rejects with SignatureDoesNotMatch — force AWS-only
            # checksum behavior off.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def _abort_stray_multipart_upload(
    client: Any, bucket: str, key: str, log: logging.LoggerAdapter
) -> None:
    """Best-effort cleanup for a timed-out upload: the background thread may have
    started (but not finished) a multipart upload for `key` before we gave up
    waiting on it. Abort it explicitly rather than relying on an R2 lifecycle
    rule to reclaim it later."""
    try:
        response = client.list_multipart_uploads(Bucket=bucket, Prefix=key)
        for upload in response.get("Uploads", []):
            if upload.get("Key") == key:
                client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload["UploadId"])
                log.warning(
                    "aborted stray multipart upload after timeout",
                    extra={"r2_bucket": bucket, "r2_key": key},
                )
    except Exception as exc:  # noqa: BLE001 -- best-effort; the TimeoutError below still fires
        log.warning(
            f"failed to abort stray multipart upload: {exc}",
            extra={"r2_bucket": bucket, "r2_key": key},
        )


def check_bucket_access(settings: R2Settings) -> None:
    client = _build_client(settings, timeout_ms=10_000)
    try:
        client.head_bucket(Bucket=settings.r2_bucket)
    except ClientError as exc:
        raise RuntimeError(f"R2 bucket '{settings.r2_bucket}' is not accessible: {exc}") from exc


def upload_dump(
    file_path: str,
    run_id: str,
    settings: R2Settings,
    timeout_ms: int,
    log: logging.LoggerAdapter,
) -> dict[str, str | float]:
    client = _build_client(settings, timeout_ms=timeout_ms)
    today = datetime.now(timezone.utc).date()
    key = f"{settings.r2_backup_prefix}{today:%Y-%m-%d}/gains-platform-{run_id}.dump"

    upload_error: list[BaseException] = []

    def _run_upload() -> None:
        try:
            client.upload_file(file_path, settings.r2_bucket, key)
        except Exception as exc:  # noqa: BLE001 -- re-raised on the caller's thread below
            upload_error.append(exc)

    started = datetime.now(timezone.utc)
    thread = threading.Thread(target=_run_upload, daemon=True)
    thread.start()
    thread.join(timeout=timeout_ms / 1000)

    if thread.is_alive():
        # Upload keeps running in the background thread; we give up waiting
        # rather than cancel it — boto3's transfer manager has no cancel API,
        # and the underlying HTTP call would keep the socket busy regardless.
        # Best-effort abort any multipart upload it may have already started,
        # so a killed daemon thread doesn't leave an orphaned upload in R2.
        _abort_stray_multipart_upload(client, settings.r2_bucket, key, log)
        raise TimeoutError(f"R2 upload timed out after {timeout_ms}ms")

    if upload_error:
        raise upload_error[0]

    duration_sec = (datetime.now(timezone.utc) - started).total_seconds()
    log.info(
        "r2 upload complete",
        extra={
            "r2_bucket": settings.r2_bucket,
            "r2_key": key,
            "upload_duration_sec": duration_sec,
        },
    )
    return {
        "r2_bucket": settings.r2_bucket,
        "r2_key": key,
        "upload_duration_sec": duration_sec,
    }


def list_backup_keys(
    settings: R2Settings, timeout_ms: int = 10_000, client: Any | None = None
) -> list[str]:
    if client is None:
        client = _build_client(settings, timeout_ms=timeout_ms)
    paginator = client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=settings.r2_bucket, Prefix=settings.r2_backup_prefix):
        objects.extend(page.get("Contents", []))
    objects.sort(key=lambda obj: obj["LastModified"])
    return [obj["Key"] for obj in objects]


def prune_old_backups(
    settings: R2Settings, keep: int, log: logging.LoggerAdapter, timeout_ms: int = 10_000
) -> dict[str, Any]:
    keep = max(MIN_RETENTION_COUNT, keep)
    deleted: list[str] = []
    errors: list[dict[str, str]] = []

    # One client, reused for both the list and any deletes below -- listing
    # always needs one, so build it once up front rather than a second time
    # only if there turns out to be something to delete.
    client = _build_client(settings, timeout_ms=timeout_ms)
    try:
        keys = list_backup_keys(settings, timeout_ms=timeout_ms, client=client)
    except (ClientError, BotoCoreError) as exc:
        log.error(f"failed to list backups for cleanup: {exc}")
        return {
            "attempted": True,
            "deleted": [],
            "errors": [],
            "list_error": str(exc),
            "remaining": None,
        }

    excess = keys[: max(0, len(keys) - keep)]
    if not excess:
        return {
            "attempted": True,
            "deleted": [],
            "errors": [],
            "list_error": None,
            "remaining": len(keys),
        }

    for key in excess:
        try:
            client.delete_object(Bucket=settings.r2_bucket, Key=key)
        except (ClientError, BotoCoreError) as exc:
            log.error(f"failed to delete old backup: {exc}", extra={"r2_key": key})
            errors.append({"key": key, "error": str(exc)})
        else:
            log.info("deleted old backup", extra={"r2_key": key})
            deleted.append(key)

    return {
        "attempted": True,
        "deleted": deleted,
        "errors": errors,
        "list_error": None,
        "remaining": len(keys) - len(deleted),
    }
