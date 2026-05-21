"""Web function model definition.

Contains WebFunction and WebSubFunction models for web test management.
Adapted from classroom reference:
- UUID -> Uuid, JSONB -> JSON for SQLite compatibility
- Removed User FK references (D-04)
- Uses string forward references in all relationship() calls
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin


class WebFunction(Base, UUIDMixin, TimestampMixin):
    """Web function table - stores web function definitions with sub-functions."""

    __tablename__ = "web_functions"
    __table_args__ = {"comment": "Web function definitions"}

    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    folder_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    identifier: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True,
    )
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    base_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    business_module: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    navigation: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    pages: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    custom_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    total_sub_functions: Mapped[int] = mapped_column(Integer, default=0)
    total_test_cases: Mapped[int] = mapped_column(Integer, default=0)
    total_test_runs: Mapped[int] = mapped_column(Integer, default=0)
    last_run_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="web_functions")  # noqa: F821
    folder: Mapped[Optional["Folder"]] = relationship("Folder", back_populates="web_functions")  # noqa: F821
    sub_functions: Mapped[list["WebSubFunction"]] = relationship(
        "WebSubFunction",
        back_populates="function",
        cascade="all, delete-orphan",
        order_by="WebSubFunction.sort_order",
    )
    web_tests: Mapped[list["WebTest"]] = relationship(  # noqa: F821
        "WebTest",
        back_populates="function",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<WebFunction(id={self.id}, identifier={self.identifier}, name={self.name})>"


class WebSubFunction(Base, UUIDMixin, TimestampMixin):
    """Web sub-function table - stores sub-function details within a web function."""

    __tablename__ = "web_sub_functions"
    __table_args__ = {"comment": "Web sub-function definitions"}

    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    function_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("web_functions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    folder_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    identifier: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True,
    )
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    test_type: Mapped[str] = mapped_column(String(50), default="functional")
    target_pages: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    test_scenario: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    test_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    expected_results: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    custom_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    total_test_cases: Mapped[int] = mapped_column(Integer, default=0)
    total_test_runs: Mapped[int] = mapped_column(Integer, default=0)
    last_run_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    project: Mapped["Project"] = relationship("Project")  # noqa: F821
    folder: Mapped[Optional["Folder"]] = relationship("Folder")  # noqa: F821
    function: Mapped["WebFunction"] = relationship(
        "WebFunction",
        back_populates="sub_functions",
    )
    web_tests: Mapped[list["WebTest"]] = relationship(  # noqa: F821
        "WebTest",
        back_populates="sub_function",
    )

    def __repr__(self) -> str:
        return f"<WebSubFunction(id={self.id}, identifier={self.identifier}, name={self.name})>"
