"""Folder repository.

Provides folder-specific database operations extending BaseRepository.
Will be fully implemented in Task 2.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.folder import Folder
from src.app.db.repositories.base import BaseRepository


class FolderRepository(BaseRepository[Folder]):
    """Folder repository with hierarchy-aware queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(Folder, session)

    async def get_by_project(self, project_id: UUID) -> list[Folder]:
        """Get all folders for a project ordered by creation time."""
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
        """Get immediate children of a folder."""
        result = await self.session.execute(
            select(Folder)
            .where(Folder.parent_id == parent_id)
            .order_by(Folder.created_at.asc())
        )
        return list(result.scalars().all())
