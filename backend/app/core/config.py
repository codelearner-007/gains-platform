"""Application configuration using Pydantic Settings."""

import json
import re
from typing import ClassVar, List, Pattern

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@127.0.0.1:56322/postgres"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Supabase
    SUPABASE_URL: str = "http://127.0.0.1:56321"
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_KEY: str
    JWT_SECRET: str

    # JWT Configuration
    USE_JWKS: bool = True
    JWT_ALGORITHM: str = "HS256"
    JWT_AUDIENCE: str = "authenticated"

    # Application
    APP_BASE_URL: str = "http://localhost:3000"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # LTI 1.3 — disabled by default. Flip to true to expose /api/v1/lti/* routes.
    # Off by default keeps the LTI protocol surface from provisioning auth.users /
    # user_schools while the integration is dormant. Code/tables/migrations remain
    # intact so enabling restores full function.
    LTI_ENABLED: bool = False
    # Shared secret for the machine-auth LTI session-bridge endpoint
    # (X-LTI-Bridge-Secret header on /api/v1/lti/consume-ticket). None/empty →
    # the dependency fails CLOSED (401), same rationale as
    # INGESTION_TRIGGER_SECRET, so the consume surface is never open unconfigured.
    LTI_BRIDGE_SECRET: str | None = None

    # Schoology ingestion (scraper → Supabase Storage → backend).
    # Private bucket the scraper uploads CSV exports into and the
    # SupabaseStorageBlobClient reads from (created by
    # 20260722090000_schoology_ingest_storage.sql).
    INGESTION_STORAGE_BUCKET: str = "schoology-ingest"
    # Shared secret for the machine-auth scraper endpoints
    # (X-Ingestion-Secret header). None/empty → the dependency fails CLOSED (401)
    # so the trigger surface is never open when unconfigured.
    INGESTION_TRIGGER_SECRET: str | None = None

    # Ingestion durability (HARDENING_PLAN §3). This kill-switch decides whether a
    # box ATTEMPTS a transform at all. It is enabled in BOTH sanctioned modes:
    #   * the full-raw rebuild machine sets it True to run whole-DB rebuilds; and
    #   * a serving box sets it True to run SCOPED, incremental transforms — the
    #     sanctioned way to fold freshly-scraped runs into a serving database,
    #     paired with INGESTION_PURGE_TRANSFORMED_RAW=True so each folded slice is
    #     purged of raw ancestry and returned to frozen/protected state.
    # So this flag being True on a serving box is expected, not a mistake; the
    # scoped path (not a full rebuild) is what actually runs there.
    # It is an efficiency/gating setting, NOT the safety mechanism: historic-year
    # data is protected unconditionally in code by the §HISTORIC invariant in
    # app/transformations/runner.py, which needs no configuration and cannot be
    # switched off. Even a mistaken FULL rebuild is therefore survivable — it is
    # refused and rolled back by the invariant, not by this flag.
    INGESTION_TRANSFORMS_ENABLED: bool = False
    INGESTION_WORKER_ENABLED: bool = True
    INGESTION_WORKER_POLL_SECONDS: int = 15
    INGESTION_LEASE_SECONDS: int = 180
    INGESTION_HEARTBEAT_SECONDS: int = 30
    INGESTION_MAX_ATTEMPTS: int = 3
    INGESTION_RAW_FLOOR: int = 1000
    # Post-transform raw purge (RECON LOCKED decision 2 — environment-aware).
    # When True (prod-only), a SUCCESSFUL scoped transform is followed by a
    # post-commit, self-healing sweep that DELETEs raw_* rows for every run
    # already folded into fact (status='succeeded' AND transforms_applied=true),
    # then VACUUMs — keeping a serving box lean and returning each transformed
    # slice to "frozen/protected" (no raw ancestry) so the §HISTORIC invariant
    # reinforces it. Default False on the local full-raw rebuild machine, which
    # KEEPS raw as the reproducibility source of truth. This is a CONFIG choice,
    # NOT derivable from data: a local first ingest is indistinguishable from a
    # prod ingest by row contents, so the guard/pipeline stay config-free and
    # only this cleanup policy is environment-gated.
    INGESTION_PURGE_TRANSFORMED_RAW: bool = False

    # Redis
    REDIS_URL: str | None = None
    REDIS_PREFIX: str = "starter_template"
    REDIS_CONNECT_TIMEOUT_SECONDS: int = 2
    REDIS_SOCKET_TIMEOUT_SECONDS: int = 2
    REDIS_ENABLE_RATE_LIMIT_STORAGE: bool | None = None
    REDIS_ENABLE_SHARE_SESSIONS: bool | None = None

    # Rate limiting (slowapi/limits syntax)
    RATE_LIMIT_AUTH_ME: str = "30/minute"
    RATE_LIMIT_USER_ROLES_ASSIGN: str = "30/minute"
    RATE_LIMIT_USER_ROLES_REMOVE: str = "30/minute"
    # Report XLSX export is CPU/memory heavy (large student×question matrices);
    # cap it well below the read endpoints.
    RATE_LIMIT_REPORTS_EXPORT: str = "20/minute"
    # Public LTI protocol routes (login/launch/consume-ticket). A single user
    # click drives a handful of these; the limit is generous enough for a
    # classroom launching concurrently (buckets are per-IP for unauthenticated
    # platform traffic) yet caps brute-force/replay probing. Same order of
    # magnitude as ingestion's 10/minute. NOTE: /.well-known/jwks.json is left
    # UNLIMITED (Schoology polls it).
    RATE_LIMIT_LTI: str = "30/minute"

    # CORS (optional, disabled by default for Vercel rewrites)
    ENABLE_CORS: bool = False
    ALLOWED_ORIGINS: str = '["http://localhost:3000"]'

    rate_limit_pattern: ClassVar[Pattern[str]] = re.compile(
        r"^\d+\/(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)$"
    )

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def parse_allowed_origins(cls, v: str) -> List[str]:
        """Parse ALLOWED_ORIGINS from JSON string to list."""
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("*")
    @classmethod
    def validate_rate_limit_policy(cls, value: str, info: ValidationInfo) -> str:
        if info.field_name.startswith("RATE_LIMIT_"):
            if not isinstance(value, str) or not cls.rate_limit_pattern.match(value):
                raise ValueError(
                    "Rate limit policy must be a string in the format N/unit, for example '60/minute'."
                )
        return value

    @model_validator(mode="after")
    def apply_redis_defaults_and_validate(self) -> "Settings":
        # Redis is opt-in. Default the toggles OFF when unset so a missing
        # REDIS_URL degrades to in-memory rate limiting instead of crash-looping
        # the app at import. Enabling a feature without a URL is still an explicit
        # misconfiguration and fails fast below.
        if self.REDIS_ENABLE_RATE_LIMIT_STORAGE is None:
            self.REDIS_ENABLE_RATE_LIMIT_STORAGE = False
        if self.REDIS_ENABLE_SHARE_SESSIONS is None:
            self.REDIS_ENABLE_SHARE_SESSIONS = False

        if (self.REDIS_ENABLE_RATE_LIMIT_STORAGE or self.REDIS_ENABLE_SHARE_SESSIONS) and not self.REDIS_URL:
            raise ValueError("REDIS_URL is required when Redis features are enabled")

        return self


# Global settings instance
settings = Settings()
