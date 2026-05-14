"""Common response schemas.

Generic API response models following the BrowserStack Test Management
API pattern for consistent response structures.
"""

from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class BaseResponse(BaseModel):
    """Base response model."""

    success: bool = Field(..., description="Whether the API call succeeded")


class SuccessResponse(BaseResponse, Generic[T]):
    """Success response with optional data payload."""

    success: bool = Field(default=True, description="API call succeeded")
    data: Optional[T] = Field(default=None, description="Response data")

    model_config = {"from_attributes": True}


class MessageResponse(BaseResponse):
    """Message-only response."""

    success: bool = Field(default=True, description="API call succeeded")
    message: str = Field(..., description="Response message")


class ErrorDetail(BaseModel):
    """Error detail for validation failures."""

    field: Optional[str] = Field(default=None, description="Error field")
    message: str = Field(..., description="Error message")
    code: Optional[str] = Field(default=None, description="Error code")


class ErrorResponse(BaseResponse):
    """Error response model for API failures."""

    success: bool = Field(default=False, description="API call failed")
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[list[ErrorDetail]] = Field(
        default=None,
        description="Error detail list",
    )


class LinkInfo(BaseModel):
    """HATEOAS-style links for API responses."""

    self: Optional[str] = Field(default=None, description="Current resource link")
    project: Optional[str] = Field(default=None, description="Project link")
    folder: Optional[str] = Field(default=None, description="Folder link")
    parent: Optional[str] = Field(default=None, description="Parent resource link")
    sub_folders: Optional[str] = Field(default=None, description="Sub-folders link")
    test_cases: Optional[str] = Field(default=None, description="Test cases link")


class TimestampMixin(BaseModel):
    """Timestamp mixin for Pydantic response schemas."""

    created_at: datetime = Field(..., description="Creation time")
    updated_at: Optional[datetime] = Field(default=None, description="Update time")
