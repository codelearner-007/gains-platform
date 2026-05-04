"""Authentication endpoints."""

from fastapi import APIRouter, Depends, Request

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.schemas.auth import CurrentUser
from app.schemas.response.auth import CurrentUserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me", response_model=CurrentUserResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH_ME)
async def get_current_user_info(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUserResponse:
    """
    Get current authenticated user information including JWT claims.

    Requires: Valid JWT token in Authorization header or Supabase SSR cookie.
    """
    return CurrentUserResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        user_role=current_user.user_role,
        hierarchy_level=current_user.hierarchy_level,
        permissions=current_user.permissions,
    )
