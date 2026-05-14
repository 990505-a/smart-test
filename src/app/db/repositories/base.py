"""Base repository with generic CRUD operations.

Provides a generic BaseRepository[ModelType] class with common
database operations: get_by_id, get_all, count, create, update,
delete, exists. Includes advisory lock support for concurrency safety.
"""

from typing import Generic, Optional, Type, TypeVar
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.database import Base


ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic base repository for CRUD operations.

    Usage::

        class ProjectRepository(BaseRepository[Project]):
            def __init__(self, session: AsyncSession):
                super().__init__(Project, session)
    """

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """Initialize repository.

        Args:
            model: SQLAlchemy model class.
            session: Async database session.
        """
        self.model = model
        self.session = session

    async def _acquire_xact_lock(self, lock_key: str) -> None:
        """Acquire PostgreSQL advisory lock within current transaction.

        Automatically released on commit/rollback. Used for serializing
        concurrent identifier generation to prevent unique constraint violations.

        Args:
            lock_key: Stable string key for the lock.
        """
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": lock_key},
        )

    async def get_by_id(self, id: UUID) -> Optional[ModelType]:
        """Get a record by its primary key ID.

        Args:
            id: Record UUID.

        Returns:
            Model instance or None.
        """
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        offset: int = 0,
        limit: int = 30,
    ) -> list[ModelType]:
        """Get all records with pagination, ordered by created_at descending.

        Args:
            offset: Number of records to skip.
            limit: Maximum records to return.

        Returns:
            List of model instances.
        """
        result = await self.session.execute(
            select(self.model)
            .offset(offset)
            .limit(limit)
            .order_by(self.model.created_at.desc())
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        """Count total records.

        Returns:
            Total record count.
        """
        result = await self.session.execute(
            select(func.count()).select_from(self.model)
        )
        return result.scalar_one()

    async def create(self, **kwargs) -> ModelType:
        """Create a new record.

        Args:
            **kwargs: Model field values.

        Returns:
            Created model instance.
        """
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(
        self,
        instance: ModelType,
        **kwargs,
    ) -> ModelType:
        """Update an existing record.

        Only updates fields where the new value is not None.

        Args:
            instance: Model instance to update.
            **kwargs: Fields to update.

        Returns:
            Updated model instance.
        """
        for key, value in kwargs.items():
            if hasattr(instance, key) and value is not None:
                setattr(instance, key, value)

        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelType) -> None:
        """Delete a record.

        Args:
            instance: Model instance to delete.
        """
        await self.session.delete(instance)
        await self.session.flush()

    async def exists(self, id: UUID) -> bool:
        """Check if a record exists by ID.

        Args:
            id: Record UUID.

        Returns:
            True if record exists.
        """
        result = await self.session.execute(
            select(func.count()).select_from(self.model).where(self.model.id == id)
        )
        return result.scalar_one() > 0
