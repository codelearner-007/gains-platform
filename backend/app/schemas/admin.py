"""Pydantic schemas for the admin sub-router (schools and ingestion)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SchoolBase(BaseModel):
    schoology_building_id: str
    name: str
    short_name: str
    schoology_school_id: Optional[str] = None
    edvance_tenant_id: Optional[str] = None
    logo_url: Optional[str] = None
    category_regex: Optional[str] = None
    due_date_window_days: Optional[int] = Field(default=None, ge=0)
    course_page_limit: Optional[int] = Field(default=None, ge=1)
    download_index: Optional[List[int]] = None
    item_filter_expression: Optional[str] = None
    category_folder_override: Optional[str] = None
    current_session: Optional[str] = None
    timezone: Optional[str] = None
    is_active: Optional[bool] = None


class CreateSchoolRequest(SchoolBase):
    pass


class UpdateSchoolRequest(BaseModel):
    schoology_building_id: Optional[str] = None
    schoology_school_id: Optional[str] = None
    edvance_tenant_id: Optional[str] = None
    name: Optional[str] = None
    short_name: Optional[str] = None
    logo_url: Optional[str] = None
    category_regex: Optional[str] = None
    due_date_window_days: Optional[int] = Field(default=None, ge=0)
    course_page_limit: Optional[int] = Field(default=None, ge=1)
    download_index: Optional[List[int]] = None
    item_filter_expression: Optional[str] = None
    category_folder_override: Optional[str] = None
    current_session: Optional[str] = None
    timezone: Optional[str] = None
    is_active: Optional[bool] = None


class SchoolResponse(BaseModel):
    school_id: str
    schoology_building_id: str
    schoology_school_id: Optional[str] = None
    edvance_tenant_id: Optional[str] = None
    name: str
    short_name: str
    logo_url: Optional[str] = None
    category_regex: str
    due_date_window_days: int
    course_page_limit: int
    download_index: List[int]
    item_filter_expression: Optional[str] = None
    category_folder_override: Optional[str] = None
    current_session: Optional[str] = None
    timezone: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TriggerIngestionRequest(BaseModel):
    school_id: Optional[str] = None
    note: Optional[str] = None


class TriggerIngestionResponse(BaseModel):
    run_id: str
    status: str
    started_at: datetime


class IngestionRunResponse(BaseModel):
    run_id: str
    school_id: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    files_processed: int
    rows_inserted: int
    error_count: int
    error_details: Optional[Dict[str, Any]] = None
