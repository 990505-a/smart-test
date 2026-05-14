"""Folder Pydantic schemas.

Provides request/response schemas for folder CRUD operations
with hierarchical tree support.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from src.app.db.schemas.enums import FolderType


class FolderCreate(BaseModel):
    """Schema for creating a folder."""

    project_id: UUID = Field(..., description="Project UUID")
    parent_id: Optional[UUID] = Field(default=None, description="Parent folder UUID")
    name: str = Field(..., min_length=1, max_length=255, description="Folder name")
    description: Optional[str] = Field(default=None, description="Description")
    folder_type: FolderType = Field(
        default=FolderType.TEST_CASE, description="Folder type"
    )


class FolderUpdate(BaseModel):
    """Schema for updating a folder."""

    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    parent_id: Optional[UUID] = None


class FolderInfo(BaseModel):
    """Schema for folder response."""

    id: UUID
    project_id: UUID
    parent_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    folder_type: FolderType
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class FolderTreeNode(FolderInfo):
    """Recursive folder tree node."""

    children: list["FolderTreeNode"] = []

    model_config = {"from_attributes": True}
