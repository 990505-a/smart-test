"""Workspace Pydantic schemas.

Request/response models for workspace CRUD endpoints.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    """Create workspace request model."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Workspace display name",
    )
    slug: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="URL-safe slug (auto-generated from name if omitted)",
    )
    description: Optional[str] = Field(
        default=None,
        description="Workspace description",
    )


class WorkspaceUpdate(BaseModel):
    """Update workspace request model.

    All fields are optional -- only provided fields are updated.
    """

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Workspace name",
    )
    description: Optional[str] = Field(
        default=None,
        description="Workspace description",
    )


class WorkspaceInfo(BaseModel):
    """Workspace response model.

    Maps from SQLAlchemy Workspace model via from_attributes.
    """

    id: UUID = Field(..., description="Workspace ID")
    slug: str = Field(..., description="URL-safe slug")
    name: str = Field(..., description="Display name")
    description: Optional[str] = Field(default=None, description="Workspace description")
    is_default: bool = Field(default=False, description="Whether this is the default workspace")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: Optional[datetime] = Field(default=None, description="Last update time")

    model_config = {"from_attributes": True}
