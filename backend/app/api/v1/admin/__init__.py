"""Admin sub-router. Aggregates schools + ingestion + LTI under /api/v1/admin.

The LTI admin surface is registered UNCONDITIONALLY (not behind LTI_ENABLED): an
admin must configure per-school bindings before the global protocol flag flips
on. LTI_ENABLED only gates the public /api/v1/lti/* protocol routes.
"""

from fastapi import APIRouter

from app.api.v1.admin import ingestion, lti, schools

admin_router = APIRouter(prefix="/admin", tags=["Admin"])
admin_router.include_router(schools.router)
admin_router.include_router(ingestion.router)
admin_router.include_router(lti.router)
