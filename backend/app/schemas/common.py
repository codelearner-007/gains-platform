"""Common schemas and base models used across request and response schemas."""

from datetime import datetime
from typing import Generic, List, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class TimestampSchema(BaseModel):
    """Base schema with timestamp fields."""

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreatedAtSchema(BaseModel):
    """Base schema with created_at field only (for tables without updated_at)."""

    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class ErrorResponse(BaseModel):
    """Standard error response returned by all error handlers."""

    error: str
    status_code: int
    details: dict = {}
