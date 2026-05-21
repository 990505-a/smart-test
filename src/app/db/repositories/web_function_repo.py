"""Web function repository.

Provides web function and sub-function specific database queries
extending BaseRepository.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.db.models.web_function import WebFunction, WebSubFunction
from src.app.db.repositories.base import BaseRepository


class WebFunctionRepository(BaseRepository[WebFunction]):
    """Repository for web function CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(WebFunction, session)

    async def list_by_project(
        self,
        project_id: UUID,
        folder_id: Optional[UUID] = None,
        search: Optional[str] = None,
        offset: int = 0,
        limit: int = 30,
    ) -> list[WebFunction]:
        """List web functions by project with optional filters."""
        query = select(WebFunction).where(WebFunction.project_id == project_id)

        if folder_id:
            query = query.where(WebFunction.folder_id == folder_id)
        if search:
            query = query.where(WebFunction.name.ilike(f"%{search}%"))

        query = query.order_by(WebFunction.sort_order, WebFunction.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_by_project(
        self,
        project_id: UUID,
        folder_id: Optional[UUID] = None,
        search: Optional[str] = None,
    ) -> int:
        """Count web functions in a project with optional filters."""
        query = select(func.count()).select_from(WebFunction).where(
            WebFunction.project_id == project_id
        )

        if folder_id:
            query = query.where(WebFunction.folder_id == folder_id)
        if search:
            query = query.where(WebFunction.name.ilike(f"%{search}%"))

        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_by_identifier(self, identifier: str) -> Optional[WebFunction]:
        """Get a web function by its identifier."""
        result = await self.session.execute(
            select(WebFunction).where(WebFunction.identifier == identifier)
        )
        return result.scalar_one_or_none()


class WebSubFunctionRepository(BaseRepository[WebSubFunction]):
    """Repository for web sub-function CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(WebSubFunction, session)

    async def list_by_function(
        self,
        function_id: UUID,
        offset: int = 0,
        limit: int = 30,
    ) -> list[WebSubFunction]:
        """List sub-functions for a web function."""
        result = await self.session.execute(
            select(WebSubFunction)
            .where(WebSubFunction.function_id == function_id)
            .order_by(WebSubFunction.sort_order, WebSubFunction.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_function(self, function_id: UUID) -> int:
        """Count sub-functions for a web function."""
        result = await self.session.execute(
            select(func.count()).select_from(WebSubFunction).where(
                WebSubFunction.function_id == function_id
            )
        )
        return result.scalar_one()
