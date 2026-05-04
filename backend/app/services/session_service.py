"""Session service for managing user sessions."""

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.session_repository import SessionRepository
from app.schemas.response.session import SessionListResponse, SessionResponse


class SessionService:
    """Service for user session management."""

    def __init__(self, session: AsyncSession):
        self.repository = SessionRepository(session)

    async def list_sessions(
        self, user_id: str, current_session_id: Optional[str] = None
    ) -> SessionListResponse:
        """
        List active sessions for a user.

        Args:
            user_id: Auth user UUID
            current_session_id: ID of the current session (to mark is_current)

        Returns:
            SessionListResponse with sessions and total count
        """
        rows = await self.repository.list_user_sessions(user_id)
        sessions = [
            SessionResponse(
                id=str(row["id"]),
                user_agent=row.get("user_agent"),
                ip=str(row["ip"]) if row.get("ip") else None,
                created_at=row["created_at"],
                updated_at=row.get("updated_at"),
                refreshed_at=row.get("refreshed_at"),
                is_current=(str(row["id"]) == current_session_id)
                if current_session_id
                else False,
            )
            for row in rows
        ]
        return SessionListResponse(sessions=sessions, total=len(sessions))

    async def revoke_session(self, session_id: str, user_id: str) -> bool:
        """
        Revoke a specific session.

        Args:
            session_id: Session UUID to revoke
            user_id: Auth user UUID

        Returns:
            True if session was revoked

        Raises:
            HTTPException: 404 if session not found
        """
        deleted = await self.repository.revoke_session(session_id, user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Session not found")
        return True
