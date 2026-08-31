"""Project model definition.

Stores test project information. 2026-08 用例 MD 重构后仅作为附件等
资源的归属锚点；测试用例本体存于 workspace/default/cases/*.md。
"""

from uuid import UUID

from sqlalchemy import String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin

DEFAULT_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


class Project(Base, UUIDMixin, TimestampMixin):
    """Project table - stores test project information."""

    __tablename__ = "projects"
    __table_args__ = {"comment": "Project table"}

    identifier: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Project identifier, e.g. PR-1234",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Project name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Project description",
    )
    created_by: Mapped[UUID] = mapped_column(
        Uuid,
        default=lambda: DEFAULT_USER_ID,
        nullable=False,
        comment="Creator ID",
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, identifier={self.identifier}, name={self.name})>"
