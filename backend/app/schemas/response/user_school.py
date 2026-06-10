"""Response schemas for per-school membership."""

from datetime import datetime

from pydantic import BaseModel


class UserSchoolResponse(BaseModel):
    """A single ``user_schools`` membership row, enriched with school metadata."""

    id: str
    user_id: str
    school_id: str
    school_role: str
    is_primary: bool
    school_name: str
    school_short_name: str
    school_is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
