"""Web test Pydantic schemas.

Provides request/response schemas for web test CRUD, test run,
and result management operations.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# --- Web Test ---


class WebTestCreate(BaseModel):
    """Schema for creating a web test."""

    project_id: UUID = Field(..., description="Project UUID")
    folder_id: Optional[UUID] = Field(default=None, description="Folder UUID")
    function_id: Optional[UUID] = Field(default=None, description="Web function UUID")
    sub_function_id: Optional[UUID] = Field(default=None, description="Web sub-function UUID")
    name: str = Field(..., min_length=1, max_length=500, description="Test name")
    description: Optional[str] = Field(default=None, description="Description")
    base_url: Optional[str] = Field(default=None, max_length=2048, description="Base URL")
    test_config: Optional[dict] = Field(default=None, description="Test configuration")
    target_pages: Optional[list] = Field(default=None, description="Target pages")
    test_flows: Optional[list] = Field(default=None, description="Test flows")


class WebTestUpdate(BaseModel):
    """Schema for updating a web test."""

    folder_id: Optional[UUID] = None
    function_id: Optional[UUID] = None
    sub_function_id: Optional[UUID] = None
    name: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = None
    base_url: Optional[str] = Field(default=None, max_length=2048)
    script_path: Optional[str] = Field(default=None, max_length=2048)
    script_format: Optional[str] = Field(default=None, max_length=50)
    script_language: Optional[str] = Field(default=None, max_length=50)
    test_config: Optional[dict] = None
    target_pages: Optional[list] = None
    test_flows: Optional[list] = None
    generation_params: Optional[dict] = None
    total_pages: Optional[int] = None
    total_flows: Optional[int] = None


class WebTestInfo(BaseModel):
    """Schema for web test response."""

    id: UUID
    project_id: UUID
    folder_id: Optional[UUID] = None
    test_case_id: Optional[UUID] = None
    function_id: Optional[UUID] = None
    sub_function_id: Optional[UUID] = None
    identifier: str
    name: str
    description: Optional[str] = None
    base_url: Optional[str] = None
    script_path: Optional[str] = None
    script_format: str = "playwright"
    script_language: str = "typescript"
    test_config: dict = {}
    target_pages: Optional[list] = None
    test_flows: Optional[list] = None
    generated_by_agent: str = "web_agent"
    generation_params: Optional[dict] = None
    total_pages: int = 0
    total_flows: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Web Test Run ---


class WebTestRunCreate(BaseModel):
    """Schema for creating a web test run."""

    web_test_id: UUID = Field(..., description="Web test UUID")
    execution_config: Optional[dict] = Field(default=None, description="Execution configuration")


class WebTestRunInfo(BaseModel):
    """Schema for web test run response."""

    id: UUID
    project_id: UUID
    web_test_id: UUID
    identifier: str
    status: str = "pending"
    execution_config: Optional[dict] = None
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    duration_ms: Optional[int] = None
    report_path: Optional[str] = None
    screenshots_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Web Test Result ---


class WebTestResultInfo(BaseModel):
    """Schema for web test result response."""

    id: UUID
    test_run_id: UUID
    web_test_id: Optional[UUID] = None
    scenario_name: Optional[str] = None
    page_url: Optional[str] = None
    test_type: Optional[str] = None
    status: str
    test_summary: Optional[dict] = None
    error_details: Optional[dict] = None
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None
    duration_ms: Optional[int] = None
    retry_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}
