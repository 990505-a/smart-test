"""Folder model definition.

Supports hierarchical folder structure for organizing test assets.
Adapted from classroom reference:
- Removed APITest, WebTest, WebFunction, WebSubFunction relationships
- FolderType enum moved to schemas/enums.py
"""

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin
from src.app.db.schemas.enums import FolderType


class Folder(Base, UUIDMixin, TimestampMixin):
    """Folder table - supports infinite-level nesting for organizing test assets."""

    __tablename__ = "folders"
    __table_args__ = {"comment": "Folder table"}

    project_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Project ID",
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Parent folder ID, null means root folder",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Folder name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Folder description",
    )
    folder_type: Mapped[FolderType] = mapped_column(
        SQLEnum(
            FolderType,
            name="foldertype",
            create_type=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=FolderType.TEST_CASE,
        nullable=False,
        comment="Folder type: test_case or api_test",
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="folders",
    )
    parent: Mapped["Folder | None"] = relationship(
        "Folder",
        back_populates="children",
        remote_side="Folder.id",
    )
    children: Mapped[list["Folder"]] = relationship(
        "Folder",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    test_cases: Mapped[list["TestCase"]] = relationship(
        "TestCase",
        back_populates="folder",
        cascade="all, delete-orphan",
    )
    api_endpoints: Mapped[list["APIEndpoint"]] = relationship(
        "APIEndpoint",
        back_populates="folder",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Folder(id={self.id}, name={self.name}, folder_type={self.folder_type}, parent_id={self.parent_id})>"
