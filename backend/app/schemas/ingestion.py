"""Pydantic models for the machine-auth scraper ingestion endpoints.

These back the FROZEN scraper ↔ backend contract:

    GET  /api/v1/ingestion/scraper-config   → ScraperConfigResponse
    POST /api/v1/ingestion/scraper-complete → ScraperCompleteRequest → ScraperCompleteResponse

Authenticated by the `X-Ingestion-Secret` header (see `require_ingestion_secret`),
NOT by a user JWT — the scraper is a headless machine caller.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class ScraperSchool(BaseModel):
    """One active school as the scraper needs it (NO credentials).

    ``credential_ref`` (contract v1.1, additive) is a NON-SECRET pointer into the
    scraper service's ``SCHOOLOGY_CREDENTIALS`` map — never a credential itself.
    When null the scraper falls back to ``short_name`` → ``"default"`` → legacy
    flat env (HARDENING_PLAN §7).
    """

    school_id: str
    name: str
    short_name: str
    schoology_building_id: str
    category_regex: Optional[str] = None
    due_date_window_days: Optional[int] = None
    course_page_limit: Optional[int] = None
    download_index: Optional[List[int]] = None
    category_folder_override: Optional[str] = None
    current_session: Optional[str] = None
    timezone: Optional[str] = None
    credential_ref: Optional[str] = None


class ScraperStorage(BaseModel):
    """Storage target the scraper uploads exports into."""

    bucket: str


class ScraperConfigResponse(BaseModel):
    """Payload the scraper fetches before a run (active schools only)."""

    storage: ScraperStorage
    schools: List[ScraperSchool]


class ScraperCompleteRequest(BaseModel):
    """Body the scraper POSTs after finishing all uploads for one school."""

    short_name: str
    note: Optional[str] = None


class ScraperCompleteResponse(BaseModel):
    """202 response acknowledging the pre-created (pending) run row."""

    run_id: str
    status: str
    school_id: str
    short_name: str
