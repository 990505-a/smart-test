"""Configuration service.

Business logic layer for configuration CRUD operations.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.configuration import Configuration
from src.app.db.repositories.configuration_repo import ConfigurationRepository
from src.app.db.schemas.configuration import ConfigurationInfo
from src.app.db.utils.exceptions import NotFoundException


class ConfigurationService:
    """Service for configuration business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ConfigurationRepository(db)

    async def create(self, data: dict) -> ConfigurationInfo:
        """Create a new configuration."""
        config = Configuration(
            name=data.get("name", ""),
            os=data.get("os"),
            os_version=data.get("os_version"),
            device=data.get("device"),
            browser=data.get("browser"),
            browser_version=data.get("browser_version"),
            is_system=data.get("is_system", False),
            description=data.get("description"),
        )
        self.db.add(config)
        await self.db.flush()
        await self.db.refresh(config)
        return ConfigurationInfo.model_validate(config)

    async def get(self, config_id: int) -> ConfigurationInfo:
        """Get a configuration by ID."""
        config = await self.repo.get_by_id(config_id)
        if not config:
            raise NotFoundException("Configuration", str(config_id))
        return ConfigurationInfo.model_validate(config)

    async def update(self, config_id: int, data: dict) -> ConfigurationInfo:
        """Update a configuration."""
        config = await self.repo.get_by_id(config_id)
        if not config:
            raise NotFoundException("Configuration", str(config_id))

        for key, value in data.items():
            if hasattr(config, key) and value is not None:
                setattr(config, key, value)

        await self.db.flush()
        await self.db.refresh(config)
        return ConfigurationInfo.model_validate(config)

    async def delete(self, config_id: int) -> str:
        """Delete a configuration."""
        config = await self.repo.get_by_id(config_id)
        if not config:
            raise NotFoundException("Configuration", str(config_id))
        name = config.name
        await self.repo.delete(config)
        return f"Configuration {name} deleted successfully"

    async def get_list(
        self,
        offset: int = 0,
        limit: int = 30,
    ) -> tuple[list[ConfigurationInfo], int]:
        """List all configurations with pagination."""
        configs = await self.repo.list_all(offset=offset, limit=limit)
        total = await self.repo.count_all()
        return ([ConfigurationInfo.model_validate(c) for c in configs], total)

    async def get_system_configurations(self) -> list[ConfigurationInfo]:
        """Get all system-provided configurations."""
        configs = await self.repo.get_system_configs()
        return [ConfigurationInfo.model_validate(c) for c in configs]
