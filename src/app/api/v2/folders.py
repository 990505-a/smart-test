"""Folder API routes.

Provides folder CRUD endpoints with hierarchical tree support.
"""

from uuid import UUID

from fastapi import APIRouter, status

from src.app.api.deps import DbSessionDep, FolderServiceDep
from src.app.db.schemas.common import SuccessResponse, MessageResponse
from src.app.db.schemas.folder import (
    FolderCreate,
    FolderInfo,
    FolderTreeNode,
    FolderUpdate,
)

router = APIRouter(prefix="/folders")


@router.get(
    "/project/{project_id}",
    response_model=SuccessResponse[list[FolderInfo]],
    summary="List folders by project",
)
async def list_folders(
    project_id: UUID,
    service: FolderServiceDep,
):
    """List all folders in a project."""
    folders = await service.get_folders(project_id)
    return SuccessResponse(success=True, data=folders)


@router.get(
    "/project/{project_id}/tree",
    response_model=SuccessResponse[list[FolderTreeNode]],
    summary="Get folder tree",
)
async def get_folder_tree(
    project_id: UUID,
    service: FolderServiceDep,
):
    """Get folder tree structure for a project."""
    tree = await service.get_folder_tree(project_id)
    return SuccessResponse(success=True, data=tree)


@router.post(
    "",
    response_model=SuccessResponse[FolderInfo],
    status_code=status.HTTP_201_CREATED,
    summary="Create folder",
)
async def create_folder(
    data: FolderCreate,
    service: FolderServiceDep,
    db: DbSessionDep,
):
    """Create a new folder."""
    folder = await service.create_folder(data)
    await db.commit()
    return SuccessResponse(success=True, data=folder)


@router.patch(
    "/{folder_id}",
    response_model=SuccessResponse[FolderInfo],
    summary="Update folder",
)
async def update_folder(
    folder_id: UUID,
    data: FolderUpdate,
    service: FolderServiceDep,
    db: DbSessionDep,
):
    """Update a folder."""
    folder = await service.update_folder(folder_id, data)
    await db.commit()
    return SuccessResponse(success=True, data=folder)


@router.delete(
    "/{folder_id}",
    response_model=MessageResponse,
    summary="Delete folder",
)
async def delete_folder(
    folder_id: UUID,
    service: FolderServiceDep,
    db: DbSessionDep,
):
    """Delete a folder."""
    message = await service.delete_folder(folder_id)
    await db.commit()
    return MessageResponse(success=True, message=message)
