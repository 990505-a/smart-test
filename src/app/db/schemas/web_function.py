"""Web function Pydantic schemas.

Provides request/response schemas for web function and sub-function CRUD
operations.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# --- Web Function ---


class WebFunctionCreate(BaseModel):
    """Schema for creating a web function."""

    project_id: UUID = Field(..., description="Project UUID")
    folder_id: Optional[UUID] = Field(default=None, description="Folder UUID")
    display_name: str = Field(..., min_length=1, max_length=500, description="Display name")
    name: str = Field(..., min_length=1, max_length=500, description="Function name")
    description: Optional[str] = Field(default=None, description="Description")
    base_url: Optional[str] = Field(default=None, max_length=2048, description="Base URL")
    business_module: Optional[str] = Field(default=None, max_length=200, description="Business module")
    navigation: Optional[dict] = Field(default=None, description="Navigation config")
    pages: Optional[list] = Field(default=None, description="Page list")
    tags: Optional[list] = Field(default=None, description="Tags")
    custom_config: Optional[dict] = Field(default=None, description="Custom configuration")


class WebFunctionUpdate(BaseModel):
    """Schema for updating a web function."""

    folder_id: Optional[UUID] = None
    display_name: Optional[str] = Field(default=None, max_length=500)
    name: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = None
    base_url: Optional[str] = Field(default=None, max_length=2048)
    business_module: Optional[str] = Field(default=None, max_length=200)
    navigation: Optional[dict] = None
    pages: Optional[list] = None
    tags: Optional[list] = None
    custom_config: Optional[dict] = None
    sort_order: Optional[int] = None


class WebFunctionInfo(BaseModel):
    """Schema for web function response."""

    id: UUID
    project_id: UUID
    folder_id: Optional[UUID] = None
    identifier: str
    display_name: str
    name: str
    description: Optional[str] = None
    base_url: Optional[str] = None
    business_module: Optional[str] = None
    navigation: Optional[dict] = None
    pages: Optional[list] = None
    tags: Optional[list] = None
    custom_config: Optional[dict] = None
    total_sub_functions: int = 0
    total_test_cases: int = 0
    total_test_runs: int = 0
    last_run_status: Optional[str] = None
    sort_order: int = 0
    sub_functions: Optional[list["WebSubFunctionInfo"]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Web Sub-Function ---


class WebSubFunctionCreate(BaseModel):
    """Schema for creating a web sub-function."""

    function_id: UUID = Field(..., description="Web function UUID")
    folder_id: Optional[UUID] = Field(default=None, description="Folder UUID")
    display_name: str = Field(..., min_length=1, max_length=500, description="Display name")
    name: str = Field(..., min_length=1, max_length=500, description="Sub-function name")
    description: Optional[str] = Field(default=None, description="Description")
    test_type: Optional[str] = Field(default="functional", max_length=50, description="Test type")
    target_pages: Optional[list] = Field(default=None, description="Target pages")
    test_scenario: Optional[str] = Field(default=None, description="Test scenario")
    test_data: Optional[dict] = Field(default=None, description="Test data")
    expected_results: Optional[list] = Field(default=None, description="Expected results")
    priority: Optional[str] = Field(default="medium", max_length=20, description="Priority")
    tags: Optional[list] = Field(default=None, description="Tags")
    custom_config: Optional[dict] = Field(default=None, description="Custom configuration")


class WebSubFunctionUpdate(BaseModel):
    """Schema for updating a web sub-function."""

    folder_id: Optional[UUID] = None
    display_name: Optional[str] = Field(default=None, max_length=500)
    name: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = None
    test_type: Optional[str] = Field(default=None, max_length=50)
    target_pages: Optional[list] = None
    test_scenario: Optional[str] = None
    test_data: Optional[dict] = None
    expected_results: Optional[list] = None
    priority: Optional[str] = Field(default=None, max_length=20)
    tags: Optional[list] = None
    custom_config: Optional[dict] = None
    sort_order: Optional[int] = None


class WebSubFunctionInfo(BaseModel):
    """Schema for web sub-function response."""

    id: UUID
    project_id: UUID
    function_id: UUID
    folder_id: Optional[UUID] = None
    identifier: str
    display_name: str
    name: str
    description: Optional[str] = None
    test_type: str = "functional"
    target_pages: Optional[list] = None
    test_scenario: Optional[str] = None
    test_data: Optional[dict] = None
    expected_results: Optional[list] = None
    priority: str = "medium"
    tags: Optional[list] = None
    custom_config: Optional[dict] = None
    total_test_cases: int = 0
    total_test_runs: int = 0
    last_run_status: Optional[str] = None
    sort_order: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
