"""Folder CRUD API endpoints.

Provides folder list, tree, create, update, delete endpoints.
Will be fully implemented in Task 2.
"""

from uuid import UUID

from fastapi import APIRouter, status

from src.app.api.deps import (
    FolderServiceDep,
    DbSessionDep,
)
from src.app.db.schemas.folder import FolderCreate, FolderUpdate, FolderInfo, FolderTreeNode
from src.app.db.schemas.common import SuccessResponse, MessageResponse

router = APIRouter(prefix="/folders")


@router.get(
    "/project/{project_id}",
    response_model=SuccessResponse[list[FolderInfo]],
    summary="List folders by project",
    description="Get all folders in a project as a flat list",
)
async def get_folders(
    project_id: UUID,
    service: FolderServiceDep,
) -> SuccessResponse[list[FolderInfo]]:
    """List all folders in a project."""
    folders = await service.get_folders(project_id)
    return SuccessResponse(success=True, data=folders)


@router.get(
    "/project/{project_id}/tree",
    response_model=SuccessResponse[list[FolderTreeNode]],
    summary="Get folder tree",
    description="Get hierarchical folder tree for a project",
)
async def get_folder_tree(
    project_id: UUID,
    service: FolderServiceDep,
) -> SuccessResponse[list[FolderTreeNode]]:
    """Get folder tree structure for a project."""
    tree = await service.get_folder_tree(project_id)
    return SuccessResponse(success=True, data=tree)


@router.post(
    "",
    response_model=SuccessResponse[FolderInfo],
    status_code=status.HTTP_201_CREATED,
    summary="Create folder",
    description="Create a new folder in a project",
)
async def create_folder(
    data: FolderCreate,
    service: FolderServiceDep,
    db: DbSessionDep,
) -> SuccessResponse[FolderInfo]:
    """Create a new folder."""
    folder = await service.create_folder(data)
    await db.commit()
    return SuccessResponse(success=True, data=folder)


@router.patch(
    "/{folder_id}",
    response_model=SuccessResponse[FolderInfo],
    summary="Update folder",
    description="Update folder information",
)
async def update_folder(
    folder_id: UUID,
    data: FolderUpdate,
    service: FolderServiceDep,
    db: DbSessionDep,
) -> SuccessResponse[FolderInfo]:
    """Update a folder."""
    folder = await service.update_folder(folder_id, data)
    await db.commit()
    return SuccessResponse(success=True, data=folder)


@router.delete(
    "/{folder_id}",
    response_model=MessageResponse,
    summary="Delete folder",
    description="Delete a folder and all its children",
)
async def delete_folder(
    folder_id: UUID,
    service: FolderServiceDep,
    db: DbSessionDep,
) -> MessageResponse:
    """Delete a folder."""
    message = await service.delete_folder(folder_id)
    await db.commit()
    return MessageResponse(success=True, message=message)
