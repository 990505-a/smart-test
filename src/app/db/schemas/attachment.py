"""Attachment Pydantic schemas.

Provides request/response schemas for attachment upload and management.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from src.app.db.schemas.enums import AttachmentEntityType


class AttachmentUpload(BaseModel):
    """Schema for attachment upload request metadata."""

    entity_type: AttachmentEntityType = Field(..., description="Entity type")
    entity_id: UUID = Field(..., description="Entity UUID")
    project_id: UUID = Field(..., description="Project UUID")
    description: Optional[str] = Field(default=None, description="Description")
    step_index: Optional[int] = Field(default=None, description="Step index")


class AttachmentInfo(BaseModel):
    """Schema for attachment response."""

    id: UUID
    entity_type: AttachmentEntityType
    entity_id: UUID
    project_id: UUID
    file_name: str
    file_size: int
    content_type: str
    object_name: str
    description: Optional[str] = None
    step_index: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
