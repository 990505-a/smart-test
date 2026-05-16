"""API test management routes.

Provides 13 endpoints for API test CRUD, script management,
test execution, and result retrieval.
Per D-04: no auth, uses DEFAULT_USER_ID.
"""

import os
import shutil
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from src.app.api.deps import DbSessionDep, PaginationDep
from src.app.db.schemas.common import MessageResponse, SuccessResponse
from src.app.db.schemas.pagination import PaginatedResponse, PaginationInfo


router = APIRouter(prefix="/projects/{project_id}/api-tests")


# ---------------------------------------------------------------------------
# Service dependency (lazy import to avoid circular deps with Plan 01)
# ---------------------------------------------------------------------------

async def _get_api_test_service(db: DbSessionDep):
    from src.app.db.services.api_test_service import APITestService
    return APITestService(db)


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create API test",
    description="Create a new API test under a project",
)
async def create_api_test(
    project_id: UUID,
    data: dict,
    db: DbSessionDep,
):
    """Create a new API test."""
    svc = await _get_api_test_service(db)
    result = await svc.create_api_test(project_id, data)
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.get(
    "",
    response_model=PaginatedResponse,
    summary="List API tests",
    description="List API tests for a project with optional filters",
)
async def list_api_tests(
    project_id: UUID,
    db: DbSessionDep,
    pagination: PaginationDep,
    search: Optional[str] = Query(default=None, description="Search by name"),
    script_format: Optional[str] = Query(
        default=None, description="Filter by script format"
    ),
):
    """List API tests with pagination and filtering."""
    svc = await _get_api_test_service(db)
    items, total = await svc.list_api_tests(
        project_id=project_id,
        search=search,
        script_format=script_format,
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
            base_url=f"/api/v2/projects/{project_id}/api-tests",
        ),
    )


@router.get(
    "/{id}",
    response_model=SuccessResponse,
    summary="Get API test",
    description="Get a single API test by ID",
)
async def get_api_test(
    project_id: UUID,
    id: UUID,
    db: DbSessionDep,
):
    """Get an API test by ID."""
    svc = await _get_api_test_service(db)
    result = await svc.get_api_test(id)
    if result is None:
        raise HTTPException(status_code=404, detail="API test not found")
    return SuccessResponse(success=True, data=result)


@router.patch(
    "/{id}",
    response_model=SuccessResponse,
    summary="Update API test",
    description="Update an API test",
)
async def update_api_test(
    project_id: UUID,
    id: UUID,
    data: dict,
    db: DbSessionDep,
):
    """Update an API test."""
    svc = await _get_api_test_service(db)
    result = await svc.update_api_test(id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="API test not found")
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.delete(
    "/{id}",
    response_model=MessageResponse,
    summary="Delete API test",
    description="Delete an API test",
)
async def delete_api_test(
    project_id: UUID,
    id: UUID,
    db: DbSessionDep,
):
    """Delete an API test."""
    svc = await _get_api_test_service(db)
    deleted = await svc.delete_api_test(id)
    if not deleted:
        raise HTTPException(status_code=404, detail="API test not found")
    await db.commit()
    return MessageResponse(success=True, message="API test deleted")


# ---------------------------------------------------------------------------
# Schema upload & AI generation
# ---------------------------------------------------------------------------

@router.post(
    "/upload-schema",
    response_model=SuccessResponse,
    summary="Upload OpenAPI/Swagger schema",
    description="Upload an OpenAPI/Swagger schema file for the project",
)
async def upload_schema(
    project_id: UUID,
    file: UploadFile = File(..., description="Schema file (.yaml/.json)"),
    db: DbSessionDep = None,
):
    """Upload an OpenAPI/Swagger schema file to workspace."""
    # Determine workspace path
    from src.app.core.config import settings

    schema_dir = os.path.join(
        settings.workspace_dir, str(project_id), "api", "schemas"
    )
    os.makedirs(schema_dir, exist_ok=True)

    dest = os.path.join(schema_dir, file.filename)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return SuccessResponse(
        success=True,
        data={"filename": file.filename, "path": dest},
    )


@router.post(
    "/generate-from-schema",
    response_model=SuccessResponse,
    summary="AI-generate tests from schema",
    description="Trigger AI generation of API tests from an uploaded schema (placeholder)",
)
async def generate_from_schema(
    project_id: UUID,
    data: dict,
):
    """Placeholder for AI-based test generation from schema.

    Actual generation is handled by the Agent. This endpoint returns
    an accepted response indicating the request was received.
    """
    return SuccessResponse(
        success=True,
        data={
            "status": "accepted",
            "message": "Test generation request accepted. Agent will process the schema.",
            "project_id": str(project_id),
        },
    )


# ---------------------------------------------------------------------------
# Script management
# ---------------------------------------------------------------------------

@router.get(
    "/{id}/script",
    summary="Download test script",
    description="Get the test script content as plain text",
)
async def get_script(
    project_id: UUID,
    id: UUID,
    db: DbSessionDep,
):
    """Download test script content."""
    svc = await _get_api_test_service(db)
    content = await svc.get_script(id)
    if content is None:
        raise HTTPException(status_code=404, detail="Script not found")
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(content=content)


@router.put(
    "/{id}/script",
    response_model=SuccessResponse,
    summary="Update test script",
    description="Update the test script content and optionally the format",
)
async def update_script(
    project_id: UUID,
    id: UUID,
    data: dict,
    db: DbSessionDep,
):
    """Update test script content."""
    svc = await _get_api_test_service(db)
    content = data.get("content", "")
    script_format = data.get("script_format")
    path = await svc.save_script(project_id, id, content, script_format)
    await db.commit()
    return SuccessResponse(success=True, data={"path": path})


# ---------------------------------------------------------------------------
# Test execution
# ---------------------------------------------------------------------------

@router.post(
    "/{id}/run",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Execute API test",
    description="Trigger execution of an API test",
)
async def run_api_test(
    project_id: UUID,
    id: UUID,
    data: Optional[dict] = None,
    db: DbSessionDep = None,
):
    """Execute an API test. Creates a run record with status=pending."""
    svc = await _get_api_test_service(db)
    execution_config = data.get("execution_config", {}) if data else {}
    run = await svc.create_test_run(id, execution_config)
    await db.commit()
    return SuccessResponse(success=True, data=run)


@router.get(
    "/{id}/runs",
    response_model=SuccessResponse,
    summary="List test runs",
    description="List execution history for an API test",
)
async def list_test_runs(
    project_id: UUID,
    id: UUID,
    db: DbSessionDep,
    limit: int = Query(default=20, ge=1, le=100, description="Max runs to return"),
):
    """List test run history for an API test."""
    svc = await _get_api_test_service(db)
    runs = await svc.list_test_runs(id, limit)
    return SuccessResponse(success=True, data=runs)


@router.get(
    "/{id}/runs/{run_id}",
    response_model=SuccessResponse,
    summary="Get test run",
    description="Get a specific test run detail",
)
async def get_test_run(
    project_id: UUID,
    id: UUID,
    run_id: UUID,
    db: DbSessionDep,
):
    """Get a specific test run."""
    svc = await _get_api_test_service(db)
    run = await svc.get_test_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Test run not found")
    return SuccessResponse(success=True, data=run)


@router.get(
    "/{id}/runs/{run_id}/results",
    response_model=SuccessResponse,
    summary="Get test results",
    description="Get all test results for a specific run",
)
async def get_test_results(
    project_id: UUID,
    id: UUID,
    run_id: UUID,
    db: DbSessionDep,
):
    """Get test results for a run."""
    svc = await _get_api_test_service(db)
    results = await svc.get_test_results(run_id)
    return SuccessResponse(success=True, data=results)
