"""Workspace CRUD API endpoints.

Provides workspace list, create, delete endpoints
under /workspaces prefix.
"""

from fastapi import APIRouter, status

from src.app.api.deps import WorkspaceServiceDep, DbSessionDep
from src.app.db.schemas.workspace import WorkspaceCreate, WorkspaceUpdate, WorkspaceInfo
from src.app.db.schemas.common import SuccessResponse, MessageResponse

router = APIRouter(prefix="/workspaces")


@router.get(
    "",
    response_model=SuccessResponse[list[WorkspaceInfo]],
    summary="List workspaces",
    description="Get all workspaces",
)
async def list_workspaces(
    service: WorkspaceServiceDep,
) -> SuccessResponse[list[WorkspaceInfo]]:
    """List all workspaces.

    Auto-seeds the default workspace on first call.
    """
    workspaces = await service.list_workspaces()
    return SuccessResponse(success=True, data=workspaces)


@router.post(
    "",
    response_model=SuccessResponse[WorkspaceInfo],
    status_code=status.HTTP_201_CREATED,
    summary="Create workspace",
    description="Create a new workspace with directory auto-provisioning",
)
async def create_workspace(
    data: WorkspaceCreate,
    service: WorkspaceServiceDep,
    db: DbSessionDep,
) -> SuccessResponse[WorkspaceInfo]:
    """Create a new workspace.

    - **name**: Workspace display name (required)
    - **slug**: URL-safe slug (auto-generated from name if omitted)
    - **description**: Workspace description (optional)
    """
    workspace = await service.create_workspace(data)
    await db.commit()
    return SuccessResponse(success=True, data=workspace)


@router.delete(
    "/{slug}",
    response_model=MessageResponse,
    summary="Delete workspace",
    description="Delete a workspace and its directory",
)
async def delete_workspace(
    slug: str,
    service: WorkspaceServiceDep,
    db: DbSessionDep,
) -> MessageResponse:
    """Delete a workspace by slug.

    - **slug**: Workspace slug

    Note: The default workspace cannot be deleted.
    """
    message = await service.delete_workspace(slug)
    await db.commit()
    return MessageResponse(success=True, message=message)
