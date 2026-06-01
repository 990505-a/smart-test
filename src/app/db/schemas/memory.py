"""Memory Pydantic schemas.

Request/response models for memory CRUD endpoints.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    """Create memory request model."""

    key: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Short identifier for this memory",
    )
    content: str = Field(
        ...,
        min_length=1,
        description="The actual content to remember",
    )
    category: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional category (e.g. preference, domain_knowledge, project_context)",
    )
    space_id: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Workspace scope (defaults to 'default')",
    )


class MemoryUpdate(BaseModel):
    """Update memory request model.

    All fields are optional -- only provided fields are updated.
    """

    key: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Short identifier for this memory",
    )
    content: Optional[str] = Field(
        default=None,
        min_length=1,
        description="The actual content to remember",
    )
    category: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional category",
    )


class MemoryInfo(BaseModel):
    """Memory response model.

    Maps from SQLAlchemy Memory model via from_attributes.
    """

    id: UUID = Field(..., description="Memory ID")
    space_id: str = Field(..., description="Workspace scope")
    key: str = Field(..., description="Short identifier")
    content: str = Field(..., description="Memory content")
    category: Optional[str] = Field(default=None, description="Category")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: Optional[datetime] = Field(default=None, description="Last update time")

    model_config = {"from_attributes": True}
