"""Web test management routes.

Provides 9 endpoints for web test CRUD, test execution,
and result retrieval.
Per D-04: no auth, uses DEFAULT_USER_ID.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from src.app.api.deps import DbSessionDep, PaginationDep
from src.app.db.schemas.common import MessageResponse, SuccessResponse
from src.app.db.schemas.pagination import PaginatedResponse, PaginationInfo


router = APIRouter(prefix="/projects/{project_id}/web-tests")


# ---------------------------------------------------------------------------
# Service dependency (lazy import to avoid circular deps)
# ---------------------------------------------------------------------------

async def _get_web_test_service(db: DbSessionDep):
    from src.app.db.services.web_test_service import WebTestService
    return WebTestService(db)


# ---------------------------------------------------------------------------
# Web Test CRUD endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create web test",
    description="Create a new web test under a project",
)
async def create_web_test(
    project_id: UUID,
    data: dict,
    db: DbSessionDep,
):
    """Create a new web test."""
    svc = await _get_web_test_service(db)
    result = await svc.create_web_test(project_id, data)
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.get(
    "",
    response_model=PaginatedResponse,
    summary="List web tests",
    description="List web tests for a project with optional filters",
)
async def list_web_tests(
    project_id: UUID,
    db: DbSessionDep,
    pagination: PaginationDep,
    function_id: Optional[UUID] = Query(default=None, description="Filter by web function"),
    sub_function_id: Optional[UUID] = Query(default=None, description="Filter by sub-function"),
    search: Optional[str] = Query(default=None, description="Search by name"),
):
    """List web tests with pagination and filtering."""
    svc = await _get_web_test_service(db)
    items, total = await svc.list_web_tests(
        project_id=project_id,
        function_id=function_id,
        sub_function_id=sub_function_id,
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
            base_url=f"/api/v2/projects/{project_id}/web-tests",
        ),
    )


@router.get(
    "/{id}",
    response_model=SuccessResponse,
    summary="Get web test",
    description="Get a single web test by ID",
)
async def get_web_test(
    project_id: UUID,
    id: UUID,
    db: DbSessionDep,
):
    """Get a web test by ID."""
    svc = await _get_web_test_service(db)
    result = await svc.get_web_test(id)
    if result is None:
        raise HTTPException(status_code=404, detail="Web test not found")
    return SuccessResponse(success=True, data=result)


@router.patch(
    "/{id}",
    response_model=SuccessResponse,
    summary="Update web test",
    description="Update a web test",
)
async def update_web_test(
    project_id: UUID,
    id: UUID,
    data: dict,
    db: DbSessionDep,
):
    """Update a web test."""
    svc = await _get_web_test_service(db)
    result = await svc.update_web_test(id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Web test not found")
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.delete(
    "/{id}",
    response_model=MessageResponse,
    summary="Delete web test",
    description="Delete a web test",
)
async def delete_web_test(
    project_id: UUID,
    id: UUID,
    db: DbSessionDep,
):
    """Delete a web test."""
    svc = await _get_web_test_service(db)
    deleted = await svc.delete_web_test(id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Web test not found")
    await db.commit()
    return MessageResponse(success=True, message="Web test deleted")


# ---------------------------------------------------------------------------
# Test execution endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/{id}/run",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Execute web test",
    description="Trigger execution of a web test",
)
async def run_web_test(
    project_id: UUID,
    id: UUID,
    data: Optional[dict] = None,
    db: DbSessionDep = None,
):
    """Execute a web test. Creates a run record with status=pending."""
    svc = await _get_web_test_service(db)
    execution_config = data.get("execution_config", {}) if data else {}
    run = await svc.create_test_run(id, execution_config)
    await db.commit()
    return SuccessResponse(success=True, data=run)


@router.get(
    "/{id}/runs",
    response_model=SuccessResponse,
    summary="List test runs",
    description="List execution history for a web test",
)
async def list_test_runs(
    project_id: UUID,
    id: UUID,
    db: DbSessionDep,
    limit: int = Query(default=20, ge=1, le=100, description="Max runs to return"),
):
    """List test run history for a web test."""
    svc = await _get_web_test_service(db)
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
    svc = await _get_web_test_service(db)
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
    svc = await _get_web_test_service(db)
    results = await svc.get_test_results(run_id)
    return SuccessResponse(success=True, data=results)
