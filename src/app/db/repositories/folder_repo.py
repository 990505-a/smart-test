"""Folder repository.

Provides folder-specific database queries extending BaseRepository.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.folder import Folder
from src.app.db.repositories.base import BaseRepository


class FolderRepository(BaseRepository[Folder]):
    """Repository for folder CRUD with hierarchical queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(Folder, session)

    async def get_by_project(self, project_id: UUID) -> list[Folder]:
        """Get all folders for a project."""
        result = await self.session.execute(
            select(Folder)
            .where(Folder.project_id == project_id)
            .order_by(Folder.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_root_folders(self, project_id: UUID) -> list[Folder]:
        """Get root folders (no parent) for a project."""
        result = await self.session.execute(
            select(Folder)
            .where(
                Folder.project_id == project_id,
                Folder.parent_id.is_(None),
            )
            .order_by(Folder.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_children(self, parent_id: UUID) -> list[Folder]:
        """Get child folders of a parent."""
        result = await self.session.execute(
            select(Folder)
            .where(Folder.parent_id == parent_id)
            .order_by(Folder.created_at.asc())
        )
        return list(result.scalars().all())
