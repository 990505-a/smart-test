"""Test run Pydantic schemas.

Provides request/response schemas for test run CRUD operations
and test run-test case association management.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from src.app.db.schemas.enums import TestRunState, TestRunActiveState, TestResultStatus


class TestRunCreate(BaseModel):
    """Schema for creating a test run."""

    project_id: UUID = Field(..., description="Project UUID")
    name: str = Field(..., min_length=1, max_length=500, description="Test run name")
    description: Optional[str] = Field(default=None, description="Description")
    test_case_ids: list[UUID] = Field(
        default_factory=list, description="Test case UUIDs to include"
    )


class TestRunUpdate(BaseModel):
    """Schema for updating a test run."""

    name: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = None
    run_state: Optional[TestRunState] = None


class TestRunTestCaseInfo(BaseModel):
    """Schema for test run-test case association."""

    id: UUID
    test_run_id: UUID
    test_case_id: UUID
    latest_status: TestResultStatus
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TestRunInfo(BaseModel):
    """Schema for test run response with associated test cases."""

    id: UUID
    project_id: UUID
    identifier: str
    name: str
    description: Optional[str] = None
    run_state: TestRunState
    active_state: TestRunActiveState
    test_cases_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    blocked_count: int = 0
    not_executed_count: int = 0
    test_run_cases: list[TestRunTestCaseInfo] = []
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
