"""Project model definition.

Stores test project information. Adapted from classroom reference:
- Removed User FK (D-04), replaced with plain UUID using DEFAULT_USER_ID
- Removed Team, APITest, WebTest, WebFunction, WebSubFunction relationships
- Kept Project -> Folders, TestCases, Tags, TestRuns, APIEndpoints relationships
"""

from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    # Relationships (string forward references to avoid circular imports)
    folders: Mapped[list["Folder"]] = relationship(
        "Folder",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    test_cases: Mapped[list["TestCase"]] = relationship(
        "TestCase",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    tags: Mapped[list["Tag"]] = relationship(
        "Tag",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    test_runs: Mapped[list["TestRun"]] = relationship(
        "TestRun",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    api_endpoints: Mapped[list["APIEndpoint"]] = relationship(
        "APIEndpoint",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    web_functions: Mapped[list["WebFunction"]] = relationship(
        "WebFunction",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    web_tests: Mapped[list["WebTest"]] = relationship(
        "WebTest",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, identifier={self.identifier}, name={self.name})>"
