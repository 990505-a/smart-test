"""Test case API routes.

Provides test case CRUD endpoints with step management.
Per D-04: no auth, uses DEFAULT_USER_ID.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query, status

from src.app.api.deps import DbSessionDep, PaginationDep, TestCaseServiceDep
from src.app.db.schemas.common import SuccessResponse, MessageResponse
from src.app.db.schemas.enums import Priority, TestCaseState
from src.app.db.schemas.pagination import PaginatedResponse, PaginationInfo
from src.app.db.schemas.test_case import TestCaseCreate, TestCaseInfo, TestCaseUpdate

router = APIRouter(prefix="/test-cases")


@router.get(
    "",
    response_model=PaginatedResponse[TestCaseInfo],
    summary="List test cases",
    description="List test cases with filtering and pagination",
)
async def list_test_cases(
    service: TestCaseServiceDep,
    pagination: PaginationDep,
    project_id: Optional[UUID] = Query(default=None, description="Filter by project"),
    folder_id: Optional[UUID] = Query(default=None, description="Filter by folder"),
    priority: Optional[str] = Query(default=None, description="Filter by priority"),
    state: Optional[str] = Query(default=None, description="Filter by state"),
):
    """List test cases with filtering and pagination."""
    cases, total = await service.list_with_filters(
        project_id=project_id,
        folder_id=folder_id,
        priority=priority,
        state=state,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return PaginatedResponse(
        success=True,
        data=cases,
        info=PaginationInfo.create(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
            base_url="/api/v2/test-cases",
        ),
    )


@router.get(
    "/{test_case_id}",
    response_model=SuccessResponse[TestCaseInfo],
    summary="Get test case",
    description="Get a test case with its steps",
)
async def get_test_case(
    test_case_id: UUID,
    service: TestCaseServiceDep,
):
    """Get a test case with eagerly loaded steps."""
    test_case = await service.get_with_steps(test_case_id)
    return SuccessResponse(success=True, data=test_case)


@router.post(
    "",
    response_model=SuccessResponse[TestCaseInfo],
    status_code=status.HTTP_201_CREATED,
    summary="Create test case",
    description="Create a test case with steps",
)
async def create_test_case(
    data: TestCaseCreate,
    service: TestCaseServiceDep,
    db: DbSessionDep,
):
    """Create a test case with steps in a single transaction."""
    test_case = await service.create_with_steps(data)
    await db.commit()
    return SuccessResponse(success=True, data=test_case)


@router.patch(
    "/{test_case_id}",
    response_model=SuccessResponse[TestCaseInfo],
    summary="Update test case",
    description="Update a test case's fields",
)
async def update_test_case(
    test_case_id: UUID,
    data: TestCaseUpdate,
    service: TestCaseServiceDep,
    db: DbSessionDep,
):
    """Update a test case."""
    test_case = await service.update(test_case_id, data)
    await db.commit()
    return SuccessResponse(success=True, data=test_case)


@router.delete(
    "/{test_case_id}",
    response_model=MessageResponse,
    summary="Delete test case",
    description="Delete a test case and its steps",
)
async def delete_test_case(
    test_case_id: UUID,
    service: TestCaseServiceDep,
    db: DbSessionDep,
):
    """Delete a test case."""
    message = await service.delete(test_case_id)
    await db.commit()
    return MessageResponse(success=True, message=message)
