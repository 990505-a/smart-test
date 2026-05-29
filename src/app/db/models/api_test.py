"""API test model definition.

Contains APITest, APITestRun, and APITestResult models for API test
execution engine. Adapted from classroom reference:
- Removed User FK (D-04), replaced with DEFAULT_USER_ID
- Uses existing TimestampMixin/UUIDMixin patterns from base.py
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.database import Base


class APITest(Base):
    """API test table - stores API test definitions and generated scripts."""

    __tablename__ = "api_tests"

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
    )
    test_case_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("test_cases.id", ondelete="SET NULL"),
        nullable=True,
        comment="Link to existing TestCase for traceability",
    )

    # Identity
    identifier: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Schema info
    schema_url: Mapped[Optional[str]] = mapped_column(String(2048))
    schema_path: Mapped[Optional[str]] = mapped_column(String(2048))
    schema_type: Mapped[str] = mapped_column(String(50), default="openapi")

    # Script info
    script_path: Mapped[Optional[str]] = mapped_column(String(2048))
    script_format: Mapped[str] = mapped_column(String(50), default="playwright")
    script_language: Mapped[str] = mapped_column(String(50), default="typescript")

    # Configuration
    test_config: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")

    # Generation metadata
    generated_by_agent: Mapped[Optional[str]] = mapped_column(String(100))
    generation_params: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")

    # Stats
    total_endpoints: Mapped[int] = mapped_column(Integer, default=0)
    total_scenarios: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project")  # noqa: F821
    folder: Mapped[Optional["Folder"]] = relationship("Folder")  # noqa: F821
    test_case: Mapped[Optional["TestCase"]] = relationship("TestCase")  # noqa: F821
    test_runs: Mapped[list["APITestRun"]] = relationship(
        "APITestRun",
        back_populates="api_test",
        cascade="all, delete-orphan",
        order_by="APITestRun.created_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<APITest(id={self.id}, identifier={self.identifier}, name={self.name})>"


class APITestRun(Base):
    """API test run table - stores execution records for API tests."""

    __tablename__ = "api_test_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_test_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("api_tests.id", ondelete="CASCADE"),
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
    execution_config: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")

    # Stats
    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed_tests: Mapped[int] = mapped_column(Integer, default=0)
    failed_tests: Mapped[int] = mapped_column(Integer, default=0)
    skipped_tests: Mapped[int] = mapped_column(Integer, default=0)

    # Duration
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # Report
    report_path: Mapped[Optional[str]] = mapped_column(String(2048))
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project")  # noqa: F821
    api_test: Mapped["APITest"] = relationship("APITest", back_populates="test_runs")
    test_results: Mapped[list["APITestResult"]] = relationship(
        "APITestResult",
        back_populates="test_run",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<APITestRun(id={self.id}, identifier={self.identifier}, status={self.status})>"


class APITestResult(Base):
    """API test result table - stores individual test result details."""

    __tablename__ = "api_test_results"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    test_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("api_test_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_test_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("api_tests.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Test details
    scenario_name: Mapped[Optional[str]] = mapped_column(String(500))
    endpoint: Mapped[Optional[str]] = mapped_column(String(500))
    method: Mapped[Optional[str]] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    # Request/response summaries
    request_summary: Mapped[Optional[dict]] = mapped_column(JSON)
    response_summary: Mapped[Optional[dict]] = mapped_column(JSON)

    # Error info
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    detail_log_id: Mapped[Optional[str]] = mapped_column(String(100))

    # Performance
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    test_run: Mapped["APITestRun"] = relationship("APITestRun", back_populates="test_results")
    api_test: Mapped[Optional["APITest"]] = relationship("APITest")  # noqa: F821

    def __repr__(self) -> str:
        return f"<APITestResult(id={self.id}, status={self.status}, endpoint={self.endpoint})>"
