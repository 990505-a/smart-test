"""Attachment service.

Business logic layer for attachment upload/download with local filesystem
storage. Per D-07: uses local filesystem under workspace/{space_id}/attachments/.
"""

import uuid
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.attachment import Attachment
from src.app.db.repositories.attachment_repo import AttachmentRepository
from src.app.db.schemas.attachment import AttachmentInfo
from src.app.db.schemas.enums import AttachmentEntityType
from src.app.db.utils.exceptions import NotFoundException
from src.app.db.utils.file_storage import (
    get_attachment_dir,
    get_file_path,
    save_file,
)


class AttachmentService:
    """Service for attachment business logic with local filesystem storage."""

    def __init__(self, db: AsyncSession, space_id: str = "default"):
        self.repo = AttachmentRepository(db)
        self.db = db
        self.space_id = space_id

    async def upload(
        self,
        file_content: bytes,
        file_name: str,
        content_type: str,
        entity_type: AttachmentEntityType,
        entity_id: UUID,
        project_id: UUID,
        description: str | None = None,
        step_index: int | None = None,
    ) -> AttachmentInfo:
        """Upload an attachment: save file to filesystem and create DB record."""
        # Generate unique relative path
        ext = Path(file_name).suffix if file_name else ""
        unique_name = f"{uuid.uuid4().hex}{ext}"
        relative_path = f"attachments/{unique_name}"

        # Save file to filesystem
        save_file(file_content, relative_path, self.space_id)

        # Create DB record
        attachment = Attachment(
            entity_type=entity_type,
            entity_id=entity_id,
            project_id=project_id,
            file_name=file_name,
            file_size=len(file_content),
            content_type=content_type,
            object_name=relative_path,
            description=description,
            step_index=step_index,
        )
        self.db.add(attachment)
        await self.db.flush()
        await self.db.refresh(attachment)

        return AttachmentInfo.model_validate(attachment)

    async def download(self, attachment_id: UUID) -> tuple[bytes, str, str]:
        """Download an attachment: read file from filesystem.

        Returns:
            Tuple of (file_content, file_name, content_type).
        """
        attachment = await self.repo.get_by_id(attachment_id)
        if not attachment:
            raise NotFoundException("Attachment", str(attachment_id))

        file_path = get_file_path(attachment.object_name, self.space_id)
        if not file_path.exists():
            raise NotFoundException("Attachment file", attachment.object_name)

        file_content = file_path.read_bytes()
        return (file_content, attachment.file_name, attachment.content_type)

    async def get_by_entity(
        self,
        entity_type: AttachmentEntityType,
        entity_id: UUID,
    ) -> list[AttachmentInfo]:
        """Get attachments by entity type and ID."""
        attachments = await self.repo.get_by_entity(entity_type, entity_id)
        return [AttachmentInfo.model_validate(a) for a in attachments]

    async def delete(self, attachment_id: UUID) -> str:
        """Delete an attachment: remove file from filesystem and DB record."""
        attachment = await self.repo.get_by_id(attachment_id)
        if not attachment:
            raise NotFoundException("Attachment", str(attachment_id))

        # Remove file from filesystem
        file_path = get_file_path(attachment.object_name, self.space_id)
        if file_path.exists():
            file_path.unlink()

        object_name = attachment.object_name
        await self.repo.delete(attachment)
        return f"Attachment {object_name} deleted successfully"
