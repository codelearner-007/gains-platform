"""SQLAlchemy declarative base - re-export from canonical location."""

from app.models.base import Base  # noqa: F401

__all__ = ["Base"]
