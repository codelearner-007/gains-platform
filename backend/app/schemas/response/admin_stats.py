"""Response schemas for the admin overview (owner-grade stats).

Replaces the old vanity-count dashboard payload. Every field maps to a real,
owner-relevant question: who's active, who's pending, how access is distributed,
and per-school data coverage / freshness.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class PeopleStats(BaseModel):
    total: int
    active_7d: int
    active_30d: int
    pending_invites: int
    banned: int


class PendingInvite(BaseModel):
    id: str
    email: Optional[str] = None
    invited_at: Optional[datetime] = None


class RoleDistribution(BaseModel):
    role_id: str
    name: str
    users: int


class SchoolUserDistribution(BaseModel):
    school_id: str
    name: str
    short_name: Optional[str] = None
    users: int


class SchoolCoverage(BaseModel):
    school_id: str
    name: str
    short_name: Optional[str] = None
    logo_url: Optional[str] = None
    is_active: bool = True
    current_session: Optional[str] = None
    assessments: int = 0
    students: int = 0
    subjects: int = 0
    sessions_covered: int = 0
    last_assessment_date: Optional[date] = None
    is_stale: bool = False


class ActivityEntry(BaseModel):
    id: str
    created_at: Optional[datetime] = None
    action: str
    module: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    actor_email: Optional[str] = None


class IngestionHealth(BaseModel):
    run_id: Optional[str] = None
    school_id: Optional[str] = None
    status: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    files_processed: Optional[int] = None
    rows_inserted: Optional[int] = None
    error_count: Optional[int] = None


class AdminOverviewResponse(BaseModel):
    people: PeopleStats
    pending_invites: List[PendingInvite]
    roles: List[RoleDistribution]
    schools_users: List[SchoolUserDistribution]
    coverage: List[SchoolCoverage]
    recent_activity: List[ActivityEntry]
    ingestion: Optional[IngestionHealth] = None
    generated_at: datetime
