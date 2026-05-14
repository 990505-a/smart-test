"""Folder Pydantic schemas.

Request/response models for folder CRUD endpoints with hierarchical tree support.
Will be fully implemented in Task 2.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from src.app.db.schemas.enums import FolderType


class FolderCreate(BaseModel):
    """Create folder request model."""

    project_id: UUID = Field(..., description="Project ID")
    parent_id: Optional[UUID] = Field(default=None, description="Parent folder ID, null means root")
    name: str = Field(..., min_length=1, max_length=255, description="Folder name")
    description: Optional[str] = Field(default=None, description="Folder description")
    folder_type: FolderType = Field(default=FolderType.TEST_CASE, description="Folder type")


class FolderUpdate(BaseModel):
    """Update folder request model."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255, description="Folder name")
    description: Optional[str] = Field(default=None, description="Folder description")
    parent_id: Optional[UUID] = Field(default=None, description="Parent folder ID for move operation")


class FolderInfo(BaseModel):
    """Folder response model."""

    id: UUID = Field(..., description="Folder ID")
    project_id: UUID = Field(..., description="Project ID")
    parent_id: Optional[UUID] = Field(default=None, description="Parent folder ID")
    name: str = Field(..., description="Folder name")
    description: Optional[str] = Field(default=None, description="Folder description")
    folder_type: FolderType = Field(..., description="Folder type")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: Optional[datetime] = Field(default=None, description="Last update time")

    model_config = {"from_attributes": True}


class FolderTreeNode(FolderInfo):
    """Recursive tree node for folder hierarchy display."""

    children: list["FolderTreeNode"] = Field(default_factory=list, description="Child folders")

    model_config = {"from_attributes": True}
