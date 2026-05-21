"""Test case model definition.

Contains TestCase, TestStep, Tag, and TestCaseTag models.
Adapted from classroom reference:
- Removed User FK references (D-04), replaced with DEFAULT_USER_ID
- Removed APITest, WebTest relationships
"""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin
from src.app.db.models.project import DEFAULT_USER_ID
from src.app.db.schemas.enums import (
    AutomationStatus,
    Priority,
    TestCaseState,
    TestCaseTemplate,
    TestCaseType,
)


class TestCase(Base, UUIDMixin, TimestampMixin):
    """Test case table - supports standard and BDD test case templates."""

    __tablename__ = "test_cases"
    __table_args__ = {"comment": "Test case table"}

    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Project ID",
    )
    folder_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Folder ID",
    )
    identifier: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Test case identifier, e.g. TC-1234",
    )
    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Test case name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Test case description",
    )
    preconditions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Preconditions",
    )
    priority: Mapped[Priority] = mapped_column(
        SQLEnum(Priority),
        default=Priority.MEDIUM,
        nullable=False,
        index=True,
        comment="Priority",
    )
    state: Mapped[TestCaseState] = mapped_column(
        SQLEnum(TestCaseState, values_callable=lambda x: [e.value for e in x]),
        default=TestCaseState.NEW,
        nullable=False,
        index=True,
        comment="State",
    )
    test_case_type: Mapped[TestCaseType] = mapped_column(
        SQLEnum(TestCaseType),
        default=TestCaseType.FUNCTIONAL,
        nullable=False,
        index=True,
        comment="Test type",
    )
    # BDD test case template fields
    template: Mapped[TestCaseTemplate] = mapped_column(
        SQLEnum(TestCaseTemplate),
        default=TestCaseTemplate.TEST_CASE,
        nullable=False,
        comment="Test case template type",
    )
    feature: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="BDD Feature description",
    )
    scenario: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="BDD Scenario description",
    )
    background: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="BDD Background description",
    )
    # Automation status
    automation_status: Mapped[AutomationStatus] = mapped_column(
        SQLEnum(AutomationStatus),
        default=AutomationStatus.NOT_AUTOMATED,
        nullable=False,
        comment="Automation status",
    )
    # Custom fields (JSON)
    custom_fields: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
        comment="Custom fields",
    )
    # Linked Jira issues
    issues: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Linked Jira issues",
    )
    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        nullable=True,
        index=True,
        comment="Owner ID",
    )
    created_by: Mapped[UUID] = mapped_column(
        Uuid,
        default=lambda: DEFAULT_USER_ID,
        nullable=False,
        comment="Creator ID",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Version number",
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="test_cases")
    folder: Mapped["Folder | None"] = relationship("Folder", back_populates="test_cases")
    steps: Mapped[list["TestStep"]] = relationship(
        "TestStep",
        back_populates="test_case",
        cascade="all, delete-orphan",
        order_by="TestStep.step_number",
    )
    tags: Mapped[list["Tag"]] = relationship(
        "Tag",
        secondary="test_case_tags",
        back_populates="test_cases",
    )
    test_run_cases: Mapped[list["TestRunTestCase"]] = relationship(
        "TestRunTestCase",
        back_populates="test_case",
        cascade="all, delete-orphan",
    )
    web_tests: Mapped[list["WebTest"]] = relationship(
        "WebTest",
        back_populates="test_case",
    )

    def __repr__(self) -> str:
        return f"<TestCase(id={self.id}, identifier={self.identifier}, name={self.name})>"


class TestStep(Base, UUIDMixin):
    """Test step table - stores individual steps within a test case."""

    __tablename__ = "test_steps"
    __table_args__ = {"comment": "Test step table"}

    test_case_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("test_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Test case ID",
    )
    step_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Step number",
    )
    action: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Action description",
    )
    expected_result: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Expected result",
    )

    # Relationships
    test_case: Mapped["TestCase"] = relationship(
        "TestCase",
        back_populates="steps",
    )

    def __repr__(self) -> str:
        return f"<TestStep(id={self.id}, step_number={self.step_number})>"


class Tag(Base, UUIDMixin, TimestampMixin):
    """Tag table - project-level tags for categorizing test cases."""

    __tablename__ = "tags"
    __table_args__ = {"comment": "Tag table"}

    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Project ID",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Tag name",
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="tags",
    )
    test_cases: Mapped[list["TestCase"]] = relationship(
        "TestCase",
        secondary="test_case_tags",
        back_populates="tags",
    )

    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, name={self.name})>"


class TestCaseTag(Base):
    """Test case - tag association table (many-to-many)."""

    __tablename__ = "test_case_tags"
    __table_args__ = {"comment": "Test case tag association table"}

    test_case_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("test_cases.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Test case ID",
    )
    tag_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Tag ID",
    )
