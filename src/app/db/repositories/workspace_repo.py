"""Workspace repository.

Provides workspace-specific database operations extending BaseRepository.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.workspace import Workspace
from src.app.db.repositories.base import BaseRepository


class WorkspaceRepository(BaseRepository[Workspace]):
    """Workspace repository with slug-based lookups."""

    def __init__(self, session: AsyncSession):
        super().__init__(Workspace, session)

    async def get_by_slug(self, slug: str) -> Optional[Workspace]:
        """Get a workspace by its unique slug.

        Args:
            slug: Workspace slug string.

        Returns:
            Workspace instance or None.
        """
        result = await self.session.execute(
            select(Workspace).where(Workspace.slug == slug)
        )
        return result.scalar_one_or_none()
