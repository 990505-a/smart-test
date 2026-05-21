"""Configuration repository.

Provides configuration-specific database queries extending BaseRepository.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.configuration import Configuration
from src.app.db.repositories.base import BaseRepository


class ConfigurationRepository(BaseRepository[Configuration]):
    """Repository for configuration CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Configuration, session)

    async def list_all(
        self,
        offset: int = 0,
        limit: int = 30,
    ) -> list[Configuration]:
        """List all configurations with pagination."""
        result = await self.session.execute(
            select(Configuration)
            .order_by(Configuration.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_all(self) -> int:
        """Count total configurations."""
        result = await self.session.execute(
            select(func.count()).select_from(Configuration)
        )
        return result.scalar_one()

    async def get_system_configs(self) -> list[Configuration]:
        """Get all system-provided configurations."""
        result = await self.session.execute(
            select(Configuration)
            .where(Configuration.is_system == True)  # noqa: E712
            .order_by(Configuration.created_at.desc())
        )
        return list(result.scalars().all())
