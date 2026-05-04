"""User management service."""

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_repository import UserRepository
from app.repositories.user_role_repository import UserRoleRepository
from app.schemas.common import PaginatedResponse
from app.schemas.response.user import UserStatsResponse, UserWithRolesResponse
from app.schemas.response.user_role import UserRoleResponse


class UserService:
    """Service for user management operations."""

    def __init__(self, session: AsyncSession):
        self.user_repo = UserRepository(session)
        self.user_role_repo = UserRoleRepository(session)

    async def get_stats(self) -> UserStatsResponse:
        stats = await self.user_repo.get_stats()
        return UserStatsResponse(**stats)

    async def list_users_with_roles(
        self,
        page: int = 1,
        page_size: int = 20,
        role: Optional[str] = None,
        email_verified: Optional[bool] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> PaginatedResponse[UserWithRolesResponse]:
        total = await self.user_repo.count_filtered(
            role=role, email_verified=email_verified,
            status=status, search=search,
        )
        offset = (page - 1) * page_size
        total_pages = (total + page_size - 1) // page_size

        users = await self.user_repo.list_filtered(
            offset=offset, limit=page_size,
            role=role, email_verified=email_verified,
            status=status, search=search,
        )

        if not users:
            return PaginatedResponse(
                items=[], total=total, page=page,
                page_size=page_size, total_pages=total_pages,
            )

        # Compute is_banned for each user
        for user in users:
            banned_until = user["banned_until"]
            user["is_banned"] = (
                False if banned_until is None
                else banned_until > datetime.now(banned_until.tzinfo)
            )

        # Bulk fetch roles
        user_ids = [u["id"] for u in users]
        roles_by_user = await self.user_role_repo.list_by_users(user_ids)

        items = [
            UserWithRolesResponse(
                **user,
                roles=[
                    UserRoleResponse.model_validate(ur)
                    for ur in roles_by_user.get(user["id"], [])
                ],
            )
            for user in users
        ]

        return PaginatedResponse(
            items=items, total=total, page=page,
            page_size=page_size, total_pages=total_pages,
        )
