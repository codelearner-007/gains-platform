"""Admin sub-router. Aggregates schools + ingestion under /api/v1/admin."""

from fastapi import APIRouter

from app.api.v1.admin import ingestion, schools

admin_router = APIRouter(prefix="/admin", tags=["Admin"])
admin_router.include_router(schools.router)
admin_router.include_router(ingestion.router)
