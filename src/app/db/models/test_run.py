"""Test run model definition.

Contains TestRun and TestRunTestCase models.
Adapted from classroom reference:
- Removed TestPlan FK (D-03: no TestPlan table), made test_plan_id a plain UUID
- Kept denormalized stats fields for query performance
"""

from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin
from src.app.db.schemas.enums import TestResultStatus, TestRunActiveState, TestRunState


class TestRun(Base, UUIDMixin, TimestampMixin):
    """Test run table - stores test execution sessions with denormalized stats."""

    __tablename__ = "test_runs"
    __table_args__ = {"comment": "Test run table"}

    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Project ID",
    )
    identifier: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Test run identifier, e.g. TR-123",
    )
    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Test run name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Test run description",
    )
    run_state: Mapped[TestRunState] = mapped_column(
        SQLEnum(TestRunState),
        default=TestRunState.NEW_RUN,
        nullable=False,
        comment="Run state",
    )
    active_state: Mapped[TestRunActiveState] = mapped_column(
        SQLEnum(TestRunActiveState),
        default=TestRunActiveState.ACTIVE,
        nullable=False,
        comment="Active state",
    )
    assignee: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Assignee email",
    )
    # No TestPlan FK per D-03 - store as plain UUID reference
    test_plan_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        nullable=True,
        index=True,
        comment="Associated test plan ID (reference only, no FK)",
    )
    tags: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Tags list",
    )
    issues: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Linked issues list",
    )
    configurations: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Configuration ID list",
    )
    # Denormalized stats for query performance
    test_cases_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Total test cases count",
    )
    passed_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Passed count",
    )
    failed_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Failed count",
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Skipped count",
    )
    blocked_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Blocked count",
    )
    not_executed_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Not executed count",
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="test_runs")
    test_run_cases: Mapped[list["TestRunTestCase"]] = relationship(
        "TestRunTestCase",
        back_populates="test_run",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<TestRun(id={self.id}, identifier={self.identifier}, name={self.name})>"


class TestRunTestCase(Base, UUIDMixin, TimestampMixin):
    """Test run - test case association table with execution status."""

    __tablename__ = "test_run_test_cases"
    __table_args__ = {"comment": "Test run test case association table"}

    test_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("test_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Test run ID",
    )
    test_case_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("test_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Test case ID",
    )
    configuration_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Configuration ID",
    )
    assignee: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Assignee email",
    )
    latest_status: Mapped[TestResultStatus] = mapped_column(
        SQLEnum(TestResultStatus),
        default=TestResultStatus.NOT_EXECUTED,
        nullable=False,
        comment="Latest test result status",
    )
    latest_result_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        nullable=True,
        comment="Latest test result ID",
    )

    # Relationships
    test_run: Mapped["TestRun"] = relationship(
        "TestRun",
        back_populates="test_run_cases",
    )
    test_case: Mapped["TestCase"] = relationship(
        "TestCase",
        back_populates="test_run_cases",
    )

    def __repr__(self) -> str:
        return f"<TestRunTestCase(test_run_id={self.test_run_id}, test_case_id={self.test_case_id})>"
