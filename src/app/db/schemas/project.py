"""Project Pydantic schemas.

Provides request/response schemas for project CRUD operations.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    """Schema for creating a project."""

    name: str = Field(..., min_length=1, max_length=255, description="Project name")
    description: Optional[str] = Field(default=None, description="Description")


class ProjectUpdate(BaseModel):
    """Schema for updating a project."""

    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None


class ProjectInfo(BaseModel):
    """Schema for project response."""

    id: UUID
    identifier: str
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
