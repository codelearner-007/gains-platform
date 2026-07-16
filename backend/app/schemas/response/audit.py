"""Audit log response schemas for API output serialization."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class AuditLogResponse(BaseModel):
    """Response schema for a single audit log entry."""

    id: str
    created_at: datetime
    user_id: Optional[str]
    actor_email: Optional[str] = None
    action: str
    module: str
    resource_id: Optional[str]
    details: Optional[dict]
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    model_config = {"from_attributes": True}

    @field_validator("ip_address", mode="before")
    @classmethod
    def _coerce_ip(cls, v: object) -> Optional[str]:
        # The INET column yields an ipaddress.IPv4/6Address; store as string.
        return None if v is None else str(v)
