"""Dashboard response schemas for API output serialization."""

from pydantic import BaseModel


class DashboardStatsResponse(BaseModel):
    """Admin dashboard statistics response."""

    total_roles: int
    total_permissions: int
    total_users: int
    total_audit_logs: int
    recent_activity_24h: int
