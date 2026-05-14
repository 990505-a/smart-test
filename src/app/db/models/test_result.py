"""Test result model definition.

Contains TestResult and TestStepResult models for tracking
test execution outcomes at case and step level.
"""

from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin
from src.app.db.schemas.enums import TestResultStatus


class TestResult(Base, UUIDMixin, TimestampMixin):
    """Test result table - stores execution results for a test case in a test run."""

    __tablename__ = "test_results"
    __table_args__ = {"comment": "Test result table"}

    test_run_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Test run ID",
    )
    test_case_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Test case ID",
    )
    test_run_test_case_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_run_test_cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Test run test case association ID",
    )
    configuration_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Configuration ID",
    )
    status: Mapped[TestResultStatus] = mapped_column(
        SQLEnum(TestResultStatus),
        nullable=False,
        comment="Test result status",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Test result description/notes",
    )
    created_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Creator email",
    )
    assignee: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Assignee email",
    )
    issues: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="Linked issues list",
    )
    issue_tracker: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Issue tracker config {name, host}",
    )
    custom_fields: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Custom fields",
    )
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Duration in milliseconds",
    )

    # Relationships
    test_run: Mapped["TestRun"] = relationship(
        "TestRun",
        backref="test_results",
    )
    test_case: Mapped["TestCase"] = relationship(
        "TestCase",
        backref="test_results",
    )
    step_results: Mapped[list["TestStepResult"]] = relationship(
        "TestStepResult",
        back_populates="test_result",
        cascade="all, delete-orphan",
        order_by="TestStepResult.step_index",
    )

    def __repr__(self) -> str:
        return f"<TestResult(id={self.id}, status={self.status})>"


class TestStepResult(Base, UUIDMixin, TimestampMixin):
    """Test step result table - stores execution results for individual steps."""

    __tablename__ = "test_step_results"
    __table_args__ = {"comment": "Test step result table"}

    test_result_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Test result ID",
    )
    step_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Step ID (permanent identifier)",
    )
    step_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Step index (starting from 1)",
    )
    status: Mapped[TestResultStatus] = mapped_column(
        SQLEnum(TestResultStatus),
        nullable=False,
        comment="Step execution status",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Step result description/notes",
    )
    issues: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="Linked issues list",
    )

    # Relationships
    test_result: Mapped["TestResult"] = relationship(
        "TestResult",
        back_populates="step_results",
    )

    def __repr__(self) -> str:
        return f"<TestStepResult(id={self.id}, step_index={self.step_index}, status={self.status})>"
