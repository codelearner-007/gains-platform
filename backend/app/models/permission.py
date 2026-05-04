"""Permission model."""

from typing import List

from sqlalchemy import String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin


class Permission(Base, CreatedAtMixin):
    """Permission model for RBAC."""

    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v7()")
    )
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    role_permissions: Mapped[List["RolePermission"]] = relationship(
        "RolePermission", back_populates="permission", cascade="all, delete-orphan"
    )

    @property
    def name(self) -> str:
        """Get permission name in module:action format."""
        return f"{self.module}:{self.action}"

    def __repr__(self) -> str:
        return f"<Permission(id={self.id}, name={self.name}, module={self.module})>"
