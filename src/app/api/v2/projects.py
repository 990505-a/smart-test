"""Project CRUD API endpoints.

Provides project list, get, create, update, delete endpoints
under /projects prefix.
Follows classroom projects.py pattern exactly.
"""

from fastapi import APIRouter, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import (
    ProjectServiceDep,
    PaginationDep,
    DbSessionDep,
)
from src.app.db.schemas.project import ProjectCreate, ProjectUpdate, ProjectInfo
from src.app.db.schemas.common import SuccessResponse, MessageResponse
from src.app.db.schemas.pagination import PaginatedResponse, PaginationInfo

router = APIRouter(prefix="/projects")


@router.get(
    "",
    response_model=PaginatedResponse[ProjectInfo],
    summary="List projects",
    description="Get all projects with pagination support",
)
async def get_projects(
    service: ProjectServiceDep,
    pagination: PaginationDep,
) -> PaginatedResponse[ProjectInfo]:
    """List all projects with pagination.

    - **p**: Page number, starting from 1
    - **page_size**: Per-page count, default 30, max 300
    """
    offset = (pagination.page - 1) * pagination.page_size
    projects, total = await service.get_projects(offset, pagination.page_size)

    # Calculate pagination info
    total_pages = (total + pagination.page_size - 1) // pagination.page_size if total > 0 else 0
    base_url = "/api/v2/projects"

    prev_url = None
    if pagination.page > 1:
        prev_url = f"{base_url}?p={pagination.page - 1}&page_size={pagination.page_size}"

    next_url = None
    if pagination.page < total_pages:
        next_url = f"{base_url}?p={pagination.page + 1}&page_size={pagination.page_size}"

    return PaginatedResponse(
        success=True,
        data=projects,
        info=PaginationInfo(
            page=pagination.page,
            page_size=pagination.page_size,
            count=len(projects),
            total=total,
            prev=prev_url,
            next=next_url,
        ),
    )


@router.get(
    "/{project_identifier}",
    response_model=SuccessResponse[ProjectInfo],
    summary="Get project",
    description="Get project details by identifier",
)
async def get_project(
    project_identifier: str,
    service: ProjectServiceDep,
) -> SuccessResponse[ProjectInfo]:
    """Get project details by identifier.

    - **project_identifier**: Project identifier, e.g. PR-0001
    """
    project = await service.get_project(project_identifier)
    return SuccessResponse(success=True, data=project)


@router.post(
    "",
    response_model=SuccessResponse[ProjectInfo],
    status_code=status.HTTP_201_CREATED,
    summary="Create project",
    description="Create a new project",
)
async def create_project(
    data: ProjectCreate,
    service: ProjectServiceDep,
    db: DbSessionDep,
) -> SuccessResponse[ProjectInfo]:
    """Create a new project.

    - **name**: Project name (required)
    - **description**: Project description (optional)
    """
    project = await service.create_project(data)
    await db.commit()
    return SuccessResponse(success=True, data=project)


@router.patch(
    "/{project_identifier}",
    response_model=SuccessResponse[ProjectInfo],
    summary="Update project",
    description="Update project information",
)
async def update_project(
    project_identifier: str,
    data: ProjectUpdate,
    service: ProjectServiceDep,
    db: DbSessionDep,
) -> SuccessResponse[ProjectInfo]:
    """Update a project.

    - **project_identifier**: Project identifier, e.g. PR-0001
    - **name**: Project name (optional)
    - **description**: Project description (optional)

    Only updates fields provided in the request body.
    """
    project = await service.update_project(project_identifier, data)
    await db.commit()
    return SuccessResponse(success=True, data=project)


@router.delete(
    "/{project_identifier}",
    response_model=MessageResponse,
    summary="Delete project",
    description="Delete a project and all associated data",
)
async def delete_project(
    project_identifier: str,
    service: ProjectServiceDep,
    db: DbSessionDep,
) -> MessageResponse:
    """Delete a project.

    - **project_identifier**: Project identifier, e.g. PR-0001

    Note: Deleting a project also deletes all folders and test cases within it.
    """
    message = await service.delete_project(project_identifier)
    await db.commit()
    return MessageResponse(success=True, message=message)
