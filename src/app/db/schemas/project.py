"""Project Pydantic schemas.

Request/response models for project CRUD endpoints.
Adapted from classroom reference:
- Removed team_id, created_by fields (D-04, no auth/users)
- Removed test_cases_count, folders_count (simplified for initial CRUD)
- Removed LinkInfo (simplified for initial implementation)
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    """Create project request model."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Project name",
    )
    description: Optional[str] = Field(
        default=None,
        description="Project description",
    )


class ProjectUpdate(BaseModel):
    """Update project request model.

    All fields are optional -- only provided fields are updated.
    """

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Project name",
    )
    description: Optional[str] = Field(
        default=None,
        description="Project description",
    )


class ProjectInfo(BaseModel):
    """Project response model.

    Maps from SQLAlchemy Project model via from_attributes.
    """

    id: UUID = Field(..., description="Project ID")
    identifier: str = Field(..., description="Project identifier, e.g. PR-0001")
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(default=None, description="Project description")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: Optional[datetime] = Field(default=None, description="Last update time")

    model_config = {"from_attributes": True}
