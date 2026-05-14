"""Test result Pydantic schemas.

Provides request/response schemas for test result and step result management.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from src.app.db.schemas.enums import TestResultStatus


class TestStepResultCreate(BaseModel):
    """Schema for creating a test step result."""

    step_index: int = Field(..., ge=1, description="Step index")
    status: TestResultStatus = Field(..., description="Step result status")
    description: Optional[str] = Field(default=None, description="Description")


class TestResultCreate(BaseModel):
    """Schema for creating a test result with step results."""

    test_run_id: UUID = Field(..., description="Test run UUID")
    test_case_id: UUID = Field(..., description="Test case UUID")
    status: TestResultStatus = Field(..., description="Overall result status")
    description: Optional[str] = Field(default=None, description="Description")
    duration_ms: Optional[int] = Field(default=None, ge=0, description="Duration in ms")
    step_results: list[TestStepResultCreate] = Field(
        default_factory=list, description="Step results"
    )


class TestStepResultInfo(BaseModel):
    """Schema for test step result response."""

    id: UUID
    test_result_id: UUID
    step_index: int
    status: TestResultStatus
    description: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TestResultInfo(BaseModel):
    """Schema for test result response with step results."""

    id: UUID
    test_run_id: UUID
    test_case_id: UUID
    status: TestResultStatus
    description: Optional[str] = None
    duration_ms: Optional[int] = None
    step_results: list[TestStepResultInfo] = []
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
