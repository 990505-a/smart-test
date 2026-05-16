"""API test Pydantic schemas.

Provides request/response schemas for API test CRUD operations,
including test run and result management.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# --- API Test ---


class APITestCreate(BaseModel):
    """Schema for creating an API test."""

    project_id: UUID = Field(..., description="Project UUID")
    folder_id: Optional[UUID] = Field(default=None, description="Folder UUID")
    name: str = Field(..., min_length=1, max_length=500, description="Test name")
    description: Optional[str] = Field(default=None, description="Description")
    schema_url: Optional[str] = Field(default=None, max_length=2048, description="OpenAPI schema URL")
    schema_type: Optional[str] = Field(default="openapi", max_length=50, description="Schema type")
    script_format: Optional[str] = Field(default="playwright", max_length=50, description="Script format")
    script_language: Optional[str] = Field(default="typescript", max_length=50, description="Script language")
    test_config: Optional[dict] = Field(default=None, description="Test configuration")


class APITestUpdate(BaseModel):
    """Schema for updating an API test."""

    name: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = None
    schema_url: Optional[str] = Field(default=None, max_length=2048)
    schema_path: Optional[str] = Field(default=None, max_length=2048)
    script_path: Optional[str] = Field(default=None, max_length=2048)
    test_config: Optional[dict] = None


class APITestInfo(BaseModel):
    """Schema for API test response."""

    id: UUID
    project_id: UUID
    folder_id: Optional[UUID] = None
    test_case_id: Optional[UUID] = None
    identifier: str
    name: str
    description: Optional[str] = None
    schema_url: Optional[str] = None
    schema_path: Optional[str] = None
    schema_type: str = "openapi"
    script_path: Optional[str] = None
    script_format: str = "playwright"
    script_language: str = "typescript"
    test_config: dict = {}
    generated_by_agent: Optional[str] = None
    generation_params: dict = {}
    total_endpoints: int = 0
    total_scenarios: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- API Test Run ---


class APITestRunCreate(BaseModel):
    """Schema for creating an API test run."""

    api_test_id: UUID = Field(..., description="API test UUID")
    execution_config: Optional[dict] = Field(default=None, description="Execution configuration")


class APITestRunInfo(BaseModel):
    """Schema for API test run response."""

    id: UUID
    project_id: UUID
    api_test_id: UUID
    identifier: str
    status: str = "pending"
    execution_config: dict = {}
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    duration_ms: Optional[int] = None
    report_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- API Test Result ---


class APITestResultInfo(BaseModel):
    """Schema for API test result response."""

    id: UUID
    test_run_id: UUID
    api_test_id: Optional[UUID] = None
    scenario_name: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    status: str
    request_summary: Optional[dict] = None
    response_summary: Optional[dict] = None
    error_message: Optional[str] = None
    detail_log_id: Optional[str] = None
    duration_ms: Optional[int] = None
    retry_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Script Upload ---


class APITestScriptUpload(BaseModel):
    """Schema for uploading/updating an API test script."""

    content: str = Field(..., min_length=1, description="Script content")
    script_format: Optional[str] = Field(default=None, max_length=50, description="Script format override")
