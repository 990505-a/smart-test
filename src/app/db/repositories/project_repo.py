"""Project repository.

Provides project-specific database queries extending BaseRepository.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.project import Project
from src.app.db.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Repository for project CRUD."""

    def __init__(self, session: AsyncSession):
        super().__init__(Project, session)

    async def get_by_identifier(self, identifier: str) -> Optional[Project]:
        """Get a project by its identifier (e.g. PR-1234)."""
        result = await self.session.execute(
            select(Project).where(Project.identifier == identifier)
        )
        return result.scalar_one_or_none()
