"""Web test model definition.

Contains WebTest, WebTestRun, and WebTestResult models for web test
execution management. Adapted from classroom reference:
- UUID -> Uuid, JSONB -> JSON for SQLite compatibility
- Removed User FK references (D-04)
- Follows api_test.py pattern with explicit id/timestamp columns
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.database import Base


class WebTest(Base):
    """Web test table - stores web test definitions and generated scripts."""

    __tablename__ = "web_tests"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
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
    test_case_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("test_cases.id", ondelete="SET NULL"),
        nullable=True,
        comment="Link to existing TestCase for traceability",
    )
    function_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("web_functions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    sub_function_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("web_sub_functions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Identity
    identifier: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Script info
    base_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    script_path: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    script_format: Mapped[str] = mapped_column(String(50), default="playwright")
    script_language: Mapped[str] = mapped_column(String(50), default="typescript")

    # Configuration
    test_config: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    target_pages: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    test_flows: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Generation metadata
    generated_by_agent: Mapped[str] = mapped_column(String(100), default="web_agent")
    generation_params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Stats
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    total_flows: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="web_tests")  # noqa: F821
    folder: Mapped[Optional["Folder"]] = relationship("Folder", back_populates="web_tests")  # noqa: F821
    test_case: Mapped[Optional["TestCase"]] = relationship("TestCase", back_populates="web_tests")  # noqa: F821
    function: Mapped[Optional["WebFunction"]] = relationship("WebFunction", back_populates="web_tests")  # noqa: F821
    sub_function: Mapped[Optional["WebSubFunction"]] = relationship("WebSubFunction", back_populates="web_tests")  # noqa: F821
    test_runs: Mapped[list["WebTestRun"]] = relationship(
        "WebTestRun",
        back_populates="web_test",
        cascade="all, delete-orphan",
        order_by="WebTestRun.created_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<WebTest(id={self.id}, identifier={self.identifier}, name={self.name})>"


class WebTestRun(Base):
    """Web test run table - stores execution records for web tests."""

    __tablename__ = "web_test_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    web_test_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("web_tests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identity
    identifier: Mapped[str] = mapped_column(String(50), nullable=False)

    # Execution status
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True,
    )

    # Execution config
    execution_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Stats
    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed_tests: Mapped[int] = mapped_column(Integer, default=0)
    failed_tests: Mapped[int] = mapped_column(Integer, default=0)
    skipped_tests: Mapped[int] = mapped_column(Integer, default=0)

    # Duration
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # Report paths
    report_path: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    screenshots_path: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project")  # noqa: F821
    web_test: Mapped["WebTest"] = relationship("WebTest", back_populates="test_runs")
    test_results: Mapped[list["WebTestResult"]] = relationship(
        "WebTestResult",
        back_populates="test_run",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<WebTestRun(id={self.id}, identifier={self.identifier}, status={self.status})>"


class WebTestResult(Base):
    """Web test result table - stores individual test result details."""

    __tablename__ = "web_test_results"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    test_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("web_test_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    web_test_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("web_tests.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Test details
    scenario_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    page_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    test_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    # Result details
    test_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # Performance
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    test_run: Mapped["WebTestRun"] = relationship("WebTestRun", back_populates="test_results")
    web_test: Mapped[Optional["WebTest"]] = relationship("WebTest")  # noqa: F821

    def __repr__(self) -> str:
        return f"<WebTestResult(id={self.id}, status={self.status}, scenario_name={self.scenario_name})>"
