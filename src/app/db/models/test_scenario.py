"""Test scenario model definition.

Contains TestScenario, ScenarioStep, StepDataMapping, ScenarioVariable,
ScenarioRun, and ScenarioStepResult models for multi-API business flow testing.
Adapted from classroom reference:
- Removed User FK (D-04), replaced with DEFAULT_USER_ID for created_by/executed_by
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.database import Base
from src.app.db.models.project import DEFAULT_USER_ID


class TestScenario(Base):
    """Test scenario main table - defines multi-API business flow tests."""

    __tablename__ = "test_scenarios"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    folder_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="SET NULL"),
    )

    # Identity
    identifier: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Global config
    global_variables: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    setup_config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    teardown_config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    # Execution config
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    parallel_execution: Mapped[bool] = mapped_column(Boolean, default=False)

    # Status
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True)

    # Stats
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    last_run_status: Mapped[Optional[str]] = mapped_column(String(50))
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        default=lambda: DEFAULT_USER_ID,
    )

    # Relationships
    steps: Mapped[list["ScenarioStep"]] = relationship(
        "ScenarioStep",
        back_populates="scenario",
        cascade="all, delete-orphan",
        order_by="ScenarioStep.step_order",
    )
    variables: Mapped[list["ScenarioVariable"]] = relationship(
        "ScenarioVariable",
        back_populates="scenario",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list["ScenarioRun"]] = relationship(
        "ScenarioRun",
        back_populates="scenario",
        cascade="all, delete-orphan",
    )


class ScenarioStep(Base):
    """Scenario step table - individual API call steps within a scenario."""

    __tablename__ = "scenario_steps"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    scenario_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("test_scenarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("api_endpoints.id", ondelete="SET NULL"),
        index=True,
    )

    # Step info
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Request override config
    request_override: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    headers_override: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    # Data extractors
    extractors: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")

    # Assertions
    assertions: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")

    # Conditional execution
    condition_expression: Mapped[Optional[str]] = mapped_column(String(1000))
    continue_on_failure: Mapped[bool] = mapped_column(Boolean, default=False)

    # Delay and retry
    delay_ms: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    scenario: Mapped["TestScenario"] = relationship("TestScenario", back_populates="steps")
    data_mappings: Mapped[list["StepDataMapping"]] = relationship(
        "StepDataMapping",
        back_populates="step",
        cascade="all, delete-orphan",
        foreign_keys="[StepDataMapping.step_id]",
    )
    step_results: Mapped[list["ScenarioStepResult"]] = relationship(
        "ScenarioStepResult", back_populates="step"
    )


class StepDataMapping(Base):
    """Step data mapping table - defines data flow between scenario steps."""

    __tablename__ = "step_data_mappings"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    step_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("scenario_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Data source
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_step_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("scenario_steps.id"),
        index=True,
    )
    source_path: Mapped[Optional[str]] = mapped_column(String(500))

    # Target
    target_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # Transform
    transform_expression: Mapped[Optional[str]] = mapped_column(String(1000))

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    step: Mapped["ScenarioStep"] = relationship(
        "ScenarioStep", back_populates="data_mappings", foreign_keys=[step_id]
    )


class ScenarioVariable(Base):
    """Scenario variable definition table."""

    __tablename__ = "scenario_variables"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    scenario_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("test_scenarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    default_value: Mapped[Optional[dict]] = mapped_column(JSONB)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Scope
    scope: Mapped[str] = mapped_column(String(50), default="scenario")
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    scenario: Mapped["TestScenario"] = relationship("TestScenario", back_populates="variables")


class ScenarioRun(Base):
    """Scenario execution record table."""

    __tablename__ = "scenario_runs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    scenario_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("test_scenarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identity
    identifier: Mapped[str] = mapped_column(String(50), nullable=False)

    # Execution status
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)

    # Runtime data
    runtime_variables: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    execution_config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    # Stats
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    passed_steps: Mapped[int] = mapped_column(Integer, default=0)
    failed_steps: Mapped[int] = mapped_column(Integer, default=0)
    skipped_steps: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # Report
    report_path: Mapped[Optional[str]] = mapped_column(String(2048))
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Executor (no User FK per D-04)
    executed_by: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        default=lambda: DEFAULT_USER_ID,
    )

    # Relationships
    scenario: Mapped["TestScenario"] = relationship("TestScenario", back_populates="runs")
    step_results: Mapped[list["ScenarioStepResult"]] = relationship(
        "ScenarioStepResult", back_populates="run", cascade="all, delete-orphan"
    )


class ScenarioStepResult(Base):
    """Scenario step execution result table."""

    __tablename__ = "scenario_step_results"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("scenario_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("scenario_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("api_endpoints.id", ondelete="SET NULL"),
    )

    # Execution info
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    # Request/response data
    request_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    response_data: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Extracted data
    extracted_data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    # Assertion results
    assertion_results: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")

    # Performance
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # Error
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_stack: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    run: Mapped["ScenarioRun"] = relationship("ScenarioRun", back_populates="step_results")
    step: Mapped["ScenarioStep"] = relationship("ScenarioStep", back_populates="step_results")
