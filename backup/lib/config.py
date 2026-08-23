"""Environment-driven configuration for the backup service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket: str
    r2_backup_prefix: str = "backups/"
    backup_retention_count: int = 3
    backup_pgdump_timeout_ms: int = 1_800_000
    backup_upload_timeout_ms: int = 1_200_000
    backup_tmp_dir: str | None = None
    backup_log_level: str = "info"
    backup_notify_emails: str = ""
    resend_api_key: str = ""
    backup_notify_from: str = ""
    backup_notify_on: str = "always"


def get_settings() -> Settings:
    # A module-level Settings() singleton would raise at import time whenever a
    # required field (e.g. database_url) is unset — which breaks pytest collection
    # for every other module that imports anything from lib/. Must be a function,
    # called once near the top of backup.py's main(), never at module import time.
    return Settings()
