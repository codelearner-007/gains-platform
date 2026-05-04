"""Base repository with generic CRUD operations."""

from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic repository with CRUD operations."""

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """
        Initialize repository.

        Args:
            model: SQLAlchemy model class
            session: Database session
        """
        self.model = model
        self.session = session

    async def get(self, id: str) -> Optional[ModelType]:
        """
        Get record by ID.

        Args:
            id: Record ID

        Returns:
            Model instance or None if not found
        """
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def list(
        self, skip: int = 0, limit: int = 100, filters: Optional[Dict[str, Any]] = None
    ) -> List[ModelType]:
        """
        List records with pagination and filters.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            filters: Dictionary of field: value filters

        Returns:
            List of model instances
        """
        query = select(self.model)

        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)

        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count records with filters.

        Args:
            filters: Dictionary of field: value filters

        Returns:
            Total count
        """
        query = select(func.count()).select_from(self.model)

        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def create(self, obj: ModelType) -> ModelType:
        """
        Create a new record.

        Args:
            obj: Model instance to create

        Returns:
            Created model instance
        """
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, obj: ModelType, update_data: Dict[str, Any]) -> ModelType:
        """
        Update an existing record.

        Callers should pass data from model.model_dump(exclude_unset=True) so that
        only explicitly provided fields are updated. None values ARE applied (allowing
        fields to be cleared intentionally).

        Args:
            obj: Model instance to update
            update_data: Dictionary of fields to update (use exclude_unset=True when dumping)

        Returns:
            Updated model instance
        """
        for key, value in update_data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)

        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: ModelType) -> None:
        """
        Delete a record.

        Args:
            obj: Model instance to delete
        """
        await self.session.delete(obj)
        await self.session.flush()

    async def get_by_field(self, field: str, value: Any) -> Optional[ModelType]:
        """
        Get record by a specific field.

        Args:
            field: Field name
            value: Field value

        Returns:
            Model instance or None if not found
        """
        if not hasattr(self.model, field):
            return None

        result = await self.session.execute(
            select(self.model).where(getattr(self.model, field) == value)
        )
        return result.scalar_one_or_none()
