"""Main v1 API router."""

from fastapi import APIRouter

from app.api.v1 import (
    audit,
    auth,
    dashboard,
    permissions,
    profile,
    roles,
    sessions,
    user_roles,
    users,
)

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
