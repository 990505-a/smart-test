"""Test case Pydantic schemas.

Provides request/response schemas for test case CRUD operations,
including step management and filtering.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from src.app.db.schemas.enums import (
    Priority,
    TestCaseState,
    TestCaseTemplate,
    TestCaseType,
)
from src.app.db.schemas.pagination import PaginationParams


class TestStepCreate(BaseModel):
    """Schema for creating a test step."""

    step_number: int = Field(..., ge=1, description="Step number")
    action: str = Field(..., min_length=1, description="Action description")
    expected_result: Optional[str] = Field(default=None, description="Expected result")


class TestStepInfo(BaseModel):
    """Schema for test step response."""

    id: UUID
    step_number: int
    action: str
    expected_result: Optional[str] = None

    model_config = {"from_attributes": True}


class TestCaseCreate(BaseModel):
    """Schema for creating a test case with steps."""

    project_id: UUID = Field(..., description="Project UUID")
    folder_id: Optional[UUID] = Field(default=None, description="Folder UUID")
    name: str = Field(..., min_length=1, max_length=500, description="Test case name")
    description: Optional[str] = Field(default=None, description="Description")
    preconditions: Optional[str] = Field(default=None, description="Preconditions")
    priority: Priority = Field(default=Priority.MEDIUM, description="Priority")
    test_case_type: TestCaseType = Field(
        default=TestCaseType.FUNCTIONAL, description="Test case type"
    )
    template: TestCaseTemplate = Field(
        default=TestCaseTemplate.TEST_CASE, description="Template type"
    )
    custom_fields: Optional[dict] = Field(default=None, description="Custom fields")
    steps: list[TestStepCreate] = Field(
        default_factory=list, description="Test steps"
    )


class TestCaseUpdate(BaseModel):
    """Schema for updating a test case."""

    name: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = None
    preconditions: Optional[str] = None
    priority: Optional[Priority] = None
    state: Optional[TestCaseState] = None
    folder_id: Optional[UUID] = None
    custom_fields: Optional[dict] = None


class TestCaseInfo(BaseModel):
    """Schema for test case response with steps."""

    id: UUID
    project_id: UUID
    folder_id: Optional[UUID] = None
    identifier: str
    name: str
    description: Optional[str] = None
    preconditions: Optional[str] = None
    priority: Priority
    state: TestCaseState
    test_case_type: TestCaseType
    template: TestCaseTemplate
    feature: Optional[str] = None
    scenario: Optional[str] = None
    background: Optional[str] = None
    automation_status: Optional[str] = None
    custom_fields: Optional[dict] = None
    issues: Optional[list] = None
    created_by: UUID
    version: int
    steps: list[TestStepInfo] = []
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TestCaseFilterParams(PaginationParams):
    """Schema for filtering test cases with pagination."""

    project_id: Optional[UUID] = Field(default=None, description="Filter by project")
    folder_id: Optional[UUID] = Field(default=None, description="Filter by folder")
    priority: Optional[Priority] = Field(default=None, description="Filter by priority")
    state: Optional[TestCaseState] = Field(default=None, description="Filter by state")
