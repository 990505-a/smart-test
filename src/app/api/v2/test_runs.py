"""Test run API routes.

Provides test run CRUD endpoints with result tracking.
Per D-04: no auth, uses DEFAULT_USER_ID.
"""

from uuid import UUID

from fastapi import APIRouter, Query, status

from src.app.api.deps import (
    DbSessionDep,
    PaginationDep,
    TestResultServiceDep,
    TestRunServiceDep,
)
from src.app.db.schemas.common import SuccessResponse, MessageResponse
from src.app.db.schemas.pagination import PaginatedResponse, PaginationInfo
from src.app.db.schemas.test_result import TestResultCreate, TestResultInfo
from src.app.db.schemas.test_run import TestRunCreate, TestRunInfo, TestRunUpdate

router = APIRouter(prefix="/test-runs")


@router.get(
    "",
    response_model=PaginatedResponse[TestRunInfo],
    summary="List test runs",
    description="List test runs by project with pagination",
)
async def list_test_runs(
    service: TestRunServiceDep,
    pagination: PaginationDep,
    project_id: UUID | None = Query(default=None),
):
    """List test runs by project with pagination."""
    runs, total = await service.list_by_project(
        project_id=project_id,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return PaginatedResponse(
        success=True,
        data=runs,
        info=PaginationInfo.create(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
            base_url="/api/v2/test-runs",
        ),
    )


@router.get(
    "/{test_run_id}",
    response_model=SuccessResponse[TestRunInfo],
    summary="Get test run",
    description="Get a test run with its test case associations",
)
async def get_test_run(
    test_run_id: UUID,
    service: TestRunServiceDep,
):
    """Get a test run with test case associations."""
    test_run = await service.get_with_cases(test_run_id)
    return SuccessResponse(success=True, data=test_run)


@router.post(
    "",
    response_model=SuccessResponse[TestRunInfo],
    status_code=status.HTTP_201_CREATED,
    summary="Create test run",
    description="Create a test run with test cases",
)
async def create_test_run(
    data: TestRunCreate,
    service: TestRunServiceDep,
    db: DbSessionDep,
):
    """Create a test run with test case associations."""
    test_run = await service.create_run(data)
    await db.commit()
    return SuccessResponse(success=True, data=test_run)


@router.patch(
    "/{test_run_id}",
    response_model=SuccessResponse[TestRunInfo],
    summary="Update test run",
    description="Update a test run's status",
)
async def update_test_run(
    test_run_id: UUID,
    data: TestRunUpdate,
    service: TestRunServiceDep,
    db: DbSessionDep,
):
    """Update a test run."""
    test_run = await service.update_status(test_run_id, data)
    await db.commit()
    return SuccessResponse(success=True, data=test_run)


@router.post(
    "/{test_run_id}/results",
    response_model=SuccessResponse[TestResultInfo],
    status_code=status.HTTP_201_CREATED,
    summary="Add test result",
    description="Record a test result with step-level detail",
)
async def add_test_result(
    test_run_id: UUID,
    data: TestResultCreate,
    result_service: TestResultServiceDep,
    db: DbSessionDep,
):
    """Create a test result with step results and update run stats."""
    # Ensure test_run_id from URL takes precedence
    data.test_run_id = test_run_id
    result = await result_service.create_result(data)
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.delete(
    "/{test_run_id}",
    response_model=MessageResponse,
    summary="Delete test run",
    description="Delete a test run and all associated data",
)
async def delete_test_run(
    test_run_id: UUID,
    service: TestRunServiceDep,
    db: DbSessionDep,
):
    """Delete a test run."""
    message = await service.delete(test_run_id)
    await db.commit()
    return MessageResponse(success=True, message=message)
