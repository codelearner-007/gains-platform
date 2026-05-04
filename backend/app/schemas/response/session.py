"""Session response schemas for API output serialization."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SessionResponse(BaseModel):
    """Response schema for a single user session."""

    id: str
    user_agent: Optional[str] = None
    ip: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    refreshed_at: Optional[datetime] = None
    is_current: bool = False


class SessionListResponse(BaseModel):
    """Response schema for list of user sessions."""

    sessions: list[SessionResponse]
    total: int
