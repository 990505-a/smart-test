"""Attachment repository.

Provides attachment-specific database queries extending BaseRepository.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.attachment import Attachment
from src.app.db.repositories.base import BaseRepository
from src.app.db.schemas.enums import AttachmentEntityType


class AttachmentRepository(BaseRepository[Attachment]):
    """Repository for attachment CRUD with entity-based queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(Attachment, session)

    async def get_by_entity(
        self,
        entity_type: AttachmentEntityType,
        entity_id: UUID,
    ) -> list[Attachment]:
        """Get attachments by entity type and ID."""
        result = await self.session.execute(
            select(Attachment)
            .where(
                Attachment.entity_type == entity_type,
                Attachment.entity_id == entity_id,
            )
            .order_by(Attachment.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_project(self, project_id: UUID) -> list[Attachment]:
        """Get all attachments for a project."""
        result = await self.session.execute(
            select(Attachment)
            .where(Attachment.project_id == project_id)
            .order_by(Attachment.created_at.desc())
        )
        return list(result.scalars().all())
