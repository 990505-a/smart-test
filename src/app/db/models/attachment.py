"""Attachment model definition.

Stores file attachment metadata. Actual files stored on local filesystem
under workspace/{space_id}/attachments/ (D-07: local filesystem storage).
"""

from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin
from src.app.db.schemas.enums import AttachmentEntityType


class Attachment(Base, UUIDMixin, TimestampMixin):
    """Attachment table - stores file metadata, actual files on local filesystem."""

    __tablename__ = "attachments"
    __table_args__ = {"comment": "Attachment table"}

    # Entity association
    entity_type: Mapped[AttachmentEntityType] = mapped_column(
        SQLEnum(AttachmentEntityType),
        nullable=False,
        index=True,
        comment="Associated entity type",
    )
    entity_id: Mapped[UUID] = mapped_column(
        Uuid,
        nullable=False,
        index=True,
        comment="Associated entity ID",
    )

    # Project association (for access control)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Project ID",
    )

    # File info
    file_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Original file name",
    )
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="File size in bytes",
    )
    content_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="MIME type",
    )

    # Storage info - relative file path (local filesystem, D-07)
    object_name: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        unique=True,
        comment="Relative file path",
    )

    # Extra info
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Attachment description",
    )
    created_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Uploader email",
    )

    # Step-related (when entity_type is test_case_step or test_step_result)
    step_index: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Step index (starting from 1)",
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        backref="attachments",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Attachment(id={self.id}, file_name={self.file_name})>"
