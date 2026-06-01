"""Memory repository.

Provides memory-specific database operations extending BaseRepository.
Includes search and category filtering for memory retrieval.
"""

from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.memory import Memory
from src.app.db.repositories.base import BaseRepository


class MemoryRepository(BaseRepository[Memory]):
    """Memory repository with space-scoped queries, search, and category filtering."""

    def __init__(self, session: AsyncSession):
        super().__init__(Memory, session)

    async def get_by_space(
        self,
        space_id: str,
        offset: int = 0,
        limit: int = 50,
        category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[Memory]:
        """Get memories filtered by space_id with optional category and search filters.

        Args:
            space_id: Workspace scope.
            offset: Number of records to skip.
            limit: Maximum records to return.
            category: Optional category filter.
            search: Optional text search on key and content columns.

        Returns:
            List of Memory instances.
        """
        query = select(Memory).where(Memory.space_id == space_id)

        if category:
            query = query.where(Memory.category == category)

        if search:
            query = query.where(
                or_(
                    Memory.key.ilike(f"%{search}%"),
                    Memory.content.ilike(f"%{search}%"),
                )
            )

        query = query.order_by(Memory.updated_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_by_space(
        self,
        space_id: str,
        category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        """Count memories for a space with optional filters.

        Args:
            space_id: Workspace scope.
            category: Optional category filter.
            search: Optional text search.

        Returns:
            Count of matching memories.
        """
        query = select(func.count()).select_from(Memory).where(Memory.space_id == space_id)

        if category:
            query = query.where(Memory.category == category)

        if search:
            query = query.where(
                or_(
                    Memory.key.ilike(f"%{search}%"),
                    Memory.content.ilike(f"%{search}%"),
                )
            )

        result = await self.session.execute(query)
        return result.scalar_one()
