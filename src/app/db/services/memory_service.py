"""Memory service.

Business logic layer for memory CRUD operations and injection queries.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.memory import Memory
from src.app.db.repositories.memory_repo import MemoryRepository
from src.app.db.schemas.memory import MemoryCreate, MemoryInfo, MemoryUpdate
from src.app.db.schemas.pagination import PaginationInfo
from src.app.db.utils.exceptions import NotFoundException


class MemoryService:
    """Service for memory business logic with full CRUD and injection queries."""

    def __init__(self, db: AsyncSession):
        self.repo = MemoryRepository(db)

    async def list_memories(
        self,
        space_id: str = "default",
        page: int = 1,
        page_size: int = 30,
        category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> tuple[list[MemoryInfo], PaginationInfo]:
        """List memories with pagination, category filter, and text search.

        Args:
            space_id: Workspace scope.
            page: Page number (1-based).
            page_size: Items per page.
            category: Optional category filter.
            search: Optional text search.

        Returns:
            Tuple of (list of MemoryInfo, PaginationInfo).
        """
        offset = (page - 1) * page_size
        total = await self.repo.count_by_space(space_id, category=category, search=search)
        memories = await self.repo.get_by_space(
            space_id, offset=offset, limit=page_size, category=category, search=search,
        )
        items = [MemoryInfo.model_validate(m) for m in memories]
        pagination = PaginationInfo.create(
            page=page,
            page_size=page_size,
            total=total,
            base_url="/api/v2/memories",
        )
        return items, pagination

    async def get_memory(self, memory_id: UUID) -> MemoryInfo:
        """Get a single memory by ID.

        Args:
            memory_id: Memory UUID.

        Returns:
            MemoryInfo instance.

        Raises:
            NotFoundException: Memory not found.
        """
        memory = await self.repo.get_by_id(memory_id)
        if not memory:
            raise NotFoundException("Memory", str(memory_id))
        return MemoryInfo.model_validate(memory)

    async def create_memory(self, data: MemoryCreate, space_id: Optional[str] = None) -> MemoryInfo:
        """Create a new memory.

        Args:
            data: Memory creation data.
            space_id: Override space_id (uses data.space_id or 'default').

        Returns:
            Created MemoryInfo.
        """
        effective_space_id = space_id or data.space_id or "default"
        memory = await self.repo.create(
            space_id=effective_space_id,
            key=data.key,
            content=data.content,
            category=data.category,
        )
        return MemoryInfo.model_validate(memory)

    async def update_memory(self, memory_id: UUID, data: MemoryUpdate) -> MemoryInfo:
        """Update an existing memory.

        Args:
            memory_id: Memory UUID.
            data: Update data (only non-None fields are updated).

        Returns:
            Updated MemoryInfo.

        Raises:
            NotFoundException: Memory not found.
        """
        memory = await self.repo.get_by_id(memory_id)
        if not memory:
            raise NotFoundException("Memory", str(memory_id))

        update_kwargs = {}
        if data.key is not None:
            update_kwargs["key"] = data.key
        if data.content is not None:
            update_kwargs["content"] = data.content
        if data.category is not None:
            update_kwargs["category"] = data.category

        if update_kwargs:
            memory = await self.repo.update(memory, **update_kwargs)

        return MemoryInfo.model_validate(memory)

    async def delete_memory(self, memory_id: UUID) -> str:
        """Delete a memory.

        Args:
            memory_id: Memory UUID.

        Returns:
            Confirmation message.

        Raises:
            NotFoundException: Memory not found.
        """
        memory = await self.repo.get_by_id(memory_id)
        if not memory:
            raise NotFoundException("Memory", str(memory_id))
        await self.repo.delete(memory)
        return f"Memory '{memory.key}' deleted successfully"

    async def get_all_for_injection(
        self,
        space_id: str = "default",
        limit: int = 20,
    ) -> list[MemoryInfo]:
        """Get recent memories for middleware injection.

        Returns memories ordered by updated_at descending, limited to
        the most recent entries. Used by MemoryInjectionMiddleware.

        Args:
            space_id: Workspace scope.
            limit: Maximum memories to return.

        Returns:
            List of MemoryInfo instances.
        """
        memories = await self.repo.get_by_space(space_id, offset=0, limit=limit)
        return [MemoryInfo.model_validate(m) for m in memories]
