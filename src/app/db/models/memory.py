"""Memory model definition.

Stores persistent agent memories scoped by space_id.
Each memory has a key, content, and optional category for grouping.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin


class Memory(Base, UUIDMixin, TimestampMixin):
    """Memory table - stores agent persistent memories."""

    __tablename__ = "memories"
    __table_args__ = {"comment": "Agent persistent memory table"}

    space_id: Mapped[str] = mapped_column(
        String(50),
        default="default",
        nullable=False,
        index=True,
        comment="Workspace isolation scope",
    )
    key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Short identifier for the memory",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The actual memory content",
    )
    category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Optional categorization (e.g. preference, domain_knowledge)",
    )

    def __repr__(self) -> str:
        return f"<Memory(id={self.id}, space_id={self.space_id}, key={self.key})>"
