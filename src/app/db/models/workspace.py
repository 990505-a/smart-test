"""Workspace model definition.

Stores workspace information for multi-workspace support.
Each workspace has its own directory structure under settings.workspace_dir.
"""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin


class Workspace(Base, UUIDMixin, TimestampMixin):
    """Workspace table - stores workspace information."""

    __tablename__ = "workspaces"
    __table_args__ = {"comment": "Workspace table"}

    slug: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="URL-safe workspace slug",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Workspace description",
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether this is the system default workspace",
    )

    def __repr__(self) -> str:
        return f"<Workspace(id={self.id}, slug={self.slug}, name={self.name})>"
