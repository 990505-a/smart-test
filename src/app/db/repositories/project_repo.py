"""Project repository.

Provides project-specific database operations extending BaseRepository.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.project import Project
from src.app.db.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Project repository with identifier-based lookups."""

    def __init__(self, session: AsyncSession):
        super().__init__(Project, session)

    async def get_by_identifier(self, identifier: str) -> Optional[Project]:
        """Get a project by its unique identifier (e.g. PR-0001).

        Args:
            identifier: Project identifier string.

        Returns:
            Project instance or None.
        """
        result = await self.session.execute(
            select(Project).where(Project.identifier == identifier)
        )
        return result.scalar_one_or_none()
