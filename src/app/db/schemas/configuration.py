"""Configuration Pydantic schemas.

Provides request/response schemas for configuration CRUD operations.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ConfigurationCreate(BaseModel):
    """Schema for creating a configuration."""

    name: str = Field(..., min_length=1, max_length=500, description="Configuration name")
    os: Optional[str] = Field(default=None, max_length=100, description="Operating system")
    os_version: Optional[str] = Field(default=None, max_length=100, description="OS version")
    device: Optional[str] = Field(default=None, max_length=200, description="Device name")
    browser: Optional[str] = Field(default=None, max_length=100, description="Browser name")
    browser_version: Optional[str] = Field(default=None, max_length=100, description="Browser version")
    is_system: bool = Field(default=False, description="System-provided configuration")
    description: Optional[str] = Field(default=None, description="Description")


class ConfigurationUpdate(BaseModel):
    """Schema for updating a configuration."""

    name: Optional[str] = Field(default=None, max_length=500)
    os: Optional[str] = Field(default=None, max_length=100)
    os_version: Optional[str] = Field(default=None, max_length=100)
    device: Optional[str] = Field(default=None, max_length=200)
    browser: Optional[str] = Field(default=None, max_length=100)
    browser_version: Optional[str] = Field(default=None, max_length=100)
    is_system: Optional[bool] = None
    description: Optional[str] = None


class ConfigurationInfo(BaseModel):
    """Schema for configuration response."""

    id: int
    name: str
    os: Optional[str] = None
    os_version: Optional[str] = None
    device: Optional[str] = None
    browser: Optional[str] = None
    browser_version: Optional[str] = None
    is_system: bool = False
    description: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
