"""Main v1 API router."""

from fastapi import APIRouter

from app.api.v1 import (
    assessments,
    audit,
    auth,
    dashboard,
    dim,
    permissions,
    profile,
    reports,
    roles,
    sessions,
    user_roles,
    users,
)
from app.api.v1.admin import admin_router

# Create v1 router
api_router = APIRouter(prefix="/v1")

# Include sub-routers
api_router.include_router(auth.router)
api_router.include_router(profile.router)
api_router.include_router(roles.router)
api_router.include_router(permissions.router)
api_router.include_router(user_roles.router)
api_router.include_router(users.router)
api_router.include_router(audit.router)
api_router.include_router(dashboard.router)
api_router.include_router(sessions.router)

# Phase 5 — Gains pipeline endpoints
api_router.include_router(assessments.router)
api_router.include_router(reports.router)
api_router.include_router(dim.router)
api_router.include_router(admin_router)
