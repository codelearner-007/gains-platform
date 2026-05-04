"""Audit log response schemas for API output serialization."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    """Response schema for a single audit log entry."""

    id: str
    created_at: datetime
    user_id: Optional[str]
    action: str
    module: str
    resource_id: Optional[str]
    details: Optional[dict]

    model_config = {"from_attributes": True}
