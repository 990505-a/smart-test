"""Project API routes.

Provides project CRUD endpoints following the BrowserStack Test Management API pattern.
"""

from fastapi import APIRouter, status

from src.app.api.deps import DbSessionDep, PaginationDep, ProjectServiceDep
from src.app.db.schemas.common import SuccessResponse, MessageResponse
from src.app.db.schemas.pagination import PaginatedResponse, PaginationInfo
from src.app.db.schemas.project import ProjectCreate, ProjectUpdate, ProjectInfo

router = APIRouter(prefix="/projects")


@router.get(
    "",
    response_model=PaginatedResponse[ProjectInfo],
    summary="List projects",
)
async def list_projects(
    service: ProjectServiceDep,
    pagination: PaginationDep,
):
    """List projects with pagination."""
    projects, total = await service.get_projects(
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return PaginatedResponse(
        success=True,
        data=projects,
        info=PaginationInfo.create(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
            base_url="/api/v2/projects",
        ),
    )


@router.get(
    "/{project_identifier}",
    response_model=SuccessResponse[ProjectInfo],
    summary="Get project",
)
async def get_project(
    project_identifier: str,
    service: ProjectServiceDep,
):
    """Get a project by identifier."""
    project = await service.get_project(project_identifier)
    return SuccessResponse(success=True, data=project)


@router.post(
    "",
    response_model=SuccessResponse[ProjectInfo],
    status_code=status.HTTP_201_CREATED,
    summary="Create project",
)
async def create_project(
    data: ProjectCreate,
    service: ProjectServiceDep,
    db: DbSessionDep,
):
    """Create a new project."""
    project = await service.create_project(data)
    await db.commit()
    return SuccessResponse(success=True, data=project)


@router.patch(
    "/{project_identifier}",
    response_model=SuccessResponse[ProjectInfo],
    summary="Update project",
)
async def update_project(
    project_identifier: str,
    data: ProjectUpdate,
    service: ProjectServiceDep,
    db: DbSessionDep,
):
    """Update a project."""
    project = await service.update_project(project_identifier, data)
    await db.commit()
    return SuccessResponse(success=True, data=project)


@router.delete(
    "/{project_identifier}",
    response_model=MessageResponse,
    summary="Delete project",
)
async def delete_project(
    project_identifier: str,
    service: ProjectServiceDep,
    db: DbSessionDep,
):
    """Delete a project."""
    message = await service.delete_project(project_identifier)
    await db.commit()
    return MessageResponse(success=True, message=message)
