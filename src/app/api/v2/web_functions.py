"""Web function management routes.

Provides 10 endpoints for web function and sub-function CRUD operations.
Per D-04: no auth, uses DEFAULT_USER_ID.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from src.app.api.deps import DbSessionDep, PaginationDep
from src.app.db.schemas.common import MessageResponse, SuccessResponse
from src.app.db.schemas.pagination import PaginatedResponse, PaginationInfo


router = APIRouter(prefix="/projects/{project_id}/web-functions")


# ---------------------------------------------------------------------------
# Service dependency (lazy import to avoid circular deps)
# ---------------------------------------------------------------------------

async def _get_web_function_service(db: DbSessionDep):
    from src.app.db.services.web_function_service import WebFunctionService
    return WebFunctionService(db)


# ---------------------------------------------------------------------------
# Web Function CRUD endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create web function",
    description="Create a new web function under a project",
)
async def create_web_function(
    project_id: UUID,
    data: dict,
    db: DbSessionDep,
):
    """Create a new web function."""
    svc = await _get_web_function_service(db)
    result = await svc.create_web_function(project_id, data)
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.get(
    "",
    response_model=PaginatedResponse,
    summary="List web functions",
    description="List web functions for a project with optional filters",
)
async def list_web_functions(
    project_id: UUID,
    db: DbSessionDep,
    pagination: PaginationDep,
    folder_id: Optional[UUID] = Query(default=None, description="Filter by folder"),
    search: Optional[str] = Query(default=None, description="Search by name"),
):
    """List web functions with pagination and filtering."""
    svc = await _get_web_function_service(db)
    items, total = await svc.list_web_functions(
        project_id=project_id,
        folder_id=folder_id,
        search=search,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        success=True,
        data=items,
        info=PaginationInfo.create(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
            base_url=f"/api/v2/projects/{project_id}/web-functions",
        ),
    )


@router.get(
    "/{id}",
    response_model=SuccessResponse,
    summary="Get web function",
    description="Get a single web function by ID with sub-functions",
)
async def get_web_function(
    project_id: UUID,
    id: UUID,
    db: DbSessionDep,
):
    """Get a web function by ID."""
    svc = await _get_web_function_service(db)
    result = await svc.get_web_function(id)
    if result is None:
        raise HTTPException(status_code=404, detail="Web function not found")
    return SuccessResponse(success=True, data=result)


@router.patch(
    "/{id}",
    response_model=SuccessResponse,
    summary="Update web function",
    description="Update a web function",
)
async def update_web_function(
    project_id: UUID,
    id: UUID,
    data: dict,
    db: DbSessionDep,
):
    """Update a web function."""
    svc = await _get_web_function_service(db)
    result = await svc.update_web_function(id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Web function not found")
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.delete(
    "/{id}",
    response_model=MessageResponse,
    summary="Delete web function",
    description="Delete a web function",
)
async def delete_web_function(
    project_id: UUID,
    id: UUID,
    db: DbSessionDep,
):
    """Delete a web function."""
    svc = await _get_web_function_service(db)
    deleted = await svc.delete_web_function(id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Web function not found")
    await db.commit()
    return MessageResponse(success=True, message="Web function deleted")


# ---------------------------------------------------------------------------
# Sub-Function endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/{id}/sub-functions",
    response_model=PaginatedResponse,
    summary="List sub-functions",
    description="List sub-functions for a web function",
)
async def list_sub_functions(
    project_id: UUID,
    id: UUID,
    db: DbSessionDep,
    pagination: PaginationDep,
):
    """List sub-functions for a web function."""
    svc = await _get_web_function_service(db)
    items, total = await svc.list_sub_functions(
        function_id=id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        success=True,
        data=items,
        info=PaginationInfo.create(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
            base_url=f"/api/v2/projects/{project_id}/web-functions/{id}/sub-functions",
        ),
    )


@router.post(
    "/{id}/sub-functions",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create sub-function",
    description="Create a new sub-function within a web function",
)
async def create_sub_function(
    project_id: UUID,
    id: UUID,
    data: dict,
    db: DbSessionDep,
):
    """Create a sub-function."""
    svc = await _get_web_function_service(db)
    data["function_id"] = id
    result = await svc.create_sub_function(id, data)
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.get(
    "/sub-functions/{sub_id}",
    response_model=SuccessResponse,
    summary="Get sub-function",
    description="Get a single sub-function by ID",
)
async def get_sub_function(
    project_id: UUID,
    sub_id: UUID,
    db: DbSessionDep,
):
    """Get a sub-function by ID."""
    svc = await _get_web_function_service(db)
    result = await svc.get_sub_function(sub_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Sub-function not found")
    return SuccessResponse(success=True, data=result)


@router.patch(
    "/sub-functions/{sub_id}",
    response_model=SuccessResponse,
    summary="Update sub-function",
    description="Update a sub-function",
)
async def update_sub_function(
    project_id: UUID,
    sub_id: UUID,
    data: dict,
    db: DbSessionDep,
):
    """Update a sub-function."""
    svc = await _get_web_function_service(db)
    result = await svc.update_sub_function(sub_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Sub-function not found")
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.delete(
    "/sub-functions/{sub_id}",
    response_model=MessageResponse,
    summary="Delete sub-function",
    description="Delete a sub-function",
)
async def delete_sub_function(
    project_id: UUID,
    sub_id: UUID,
    db: DbSessionDep,
):
    """Delete a sub-function."""
    svc = await _get_web_function_service(db)
    deleted = await svc.delete_sub_function(sub_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Sub-function not found")
    await db.commit()
    return MessageResponse(success=True, message="Sub-function deleted")
