"""Session repository for auth.sessions access."""


from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SessionRepository:
    """Repository for querying auth.sessions directly via raw SQL."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_user_sessions(self, user_id: str) -> list[dict]:
        """
        List active sessions for a user.

        Args:
            user_id: Auth user UUID

        Returns:
            List of session dictionaries
        """
        query = text("""
            SELECT id, user_agent, ip, created_at, updated_at, refreshed_at
            FROM auth.sessions
            WHERE user_id = :user_id
              AND (not_after IS NULL OR not_after > NOW())
            ORDER BY refreshed_at DESC NULLS LAST, created_at DESC
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        return [dict(row._mapping) for row in result.fetchall()]

    async def revoke_session(self, session_id: str, user_id: str) -> bool:
        """
        Revoke (delete) a specific session.

        Args:
            session_id: Session UUID to revoke
            user_id: Auth user UUID (ensures ownership)

        Returns:
            True if a session was deleted, False otherwise
        """
        query = text("""
            DELETE FROM auth.sessions
            WHERE id = :session_id AND user_id = :user_id
        """)
        result = await self.session.execute(
            query, {"session_id": session_id, "user_id": user_id}
        )
        await self.session.commit()
        return (result.rowcount or 0) > 0
