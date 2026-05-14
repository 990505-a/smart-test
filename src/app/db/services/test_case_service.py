"""Test case service.

Business logic layer for test case CRUD with step management.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.test_case import TestCase, TestStep
from src.app.db.repositories.test_case_repo import TestCaseRepository
from src.app.db.schemas.enums import TestCaseState
from src.app.db.schemas.test_case import (
    TestCaseCreate,
    TestCaseFilterParams,
    TestCaseInfo,
    TestCaseUpdate,
)
from src.app.db.utils.exceptions import NotFoundException
from src.app.db.utils.identifier import generate_identifier_simple


class TestCaseService:
    """Service for test case business logic with step management."""

    def __init__(self, db: AsyncSession):
        self.repo = TestCaseRepository(db)
        self.db = db

    async def create_with_steps(self, data: TestCaseCreate) -> TestCaseInfo:
        """Create a test case with steps in a single transaction."""
        identifier = generate_identifier_simple("TC")
        test_case = TestCase(
            project_id=data.project_id,
            folder_id=data.folder_id,
            identifier=identifier,
            name=data.name,
            description=data.description,
            preconditions=data.preconditions,
            priority=data.priority,
            test_case_type=data.test_case_type,
            template=data.template,
            custom_fields=data.custom_fields,
        )
        self.db.add(test_case)
        await self.db.flush()

        for i, step_data in enumerate(data.steps, 1):
            step = TestStep(
                test_case_id=test_case.id,
                step_number=step_data.step_number or i,
                action=step_data.action,
                expected_result=step_data.expected_result,
            )
            self.db.add(step)

        await self.db.flush()
        # Reload with steps
        test_case = await self.repo.get_with_steps(test_case.id)
        return TestCaseInfo.model_validate(test_case)

    async def get_with_steps(self, test_case_id: UUID) -> TestCaseInfo:
        """Get a test case with eagerly loaded steps."""
        test_case = await self.repo.get_with_steps(test_case_id)
        if not test_case:
            raise NotFoundException("Test case", str(test_case_id))
        return TestCaseInfo.model_validate(test_case)

    async def get_by_identifier(self, identifier: str) -> TestCaseInfo:
        """Get a test case by its identifier."""
        test_case = await self.repo.get_by_identifier(identifier)
        if not test_case:
            raise NotFoundException("Test case", identifier)
        return TestCaseInfo.model_validate(test_case)

    async def update(
        self, test_case_id: UUID, data: TestCaseUpdate
    ) -> TestCaseInfo:
        """Update a test case."""
        test_case = await self.repo.get_with_steps(test_case_id)
        if not test_case:
            raise NotFoundException("Test case", str(test_case_id))

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if hasattr(test_case, key):
                setattr(test_case, key, value)

        await self.db.flush()
        await self.db.refresh(test_case)
        # Reload with steps
        test_case = await self.repo.get_with_steps(test_case.id)
        return TestCaseInfo.model_validate(test_case)

    async def delete(self, test_case_id: UUID) -> str:
        """Delete a test case."""
        test_case = await self.repo.get_by_id(test_case_id)
        if not test_case:
            raise NotFoundException("Test case", str(test_case_id))
        identifier = test_case.identifier
        await self.repo.delete(test_case)
        return f"Test case {identifier} deleted successfully"

    async def list_with_filters(
        self,
        project_id: Optional[UUID] = None,
        folder_id: Optional[UUID] = None,
        priority: Optional[str] = None,
        state: Optional[str] = None,
        offset: int = 0,
        limit: int = 30,
    ) -> tuple[list[TestCaseInfo], int]:
        """List test cases with filtering and pagination."""
        from sqlalchemy import func, select
        from sqlalchemy.orm import selectinload

        query = select(TestCase).options(selectinload(TestCase.steps))
        count_query = select(func.count()).select_from(TestCase)

        if project_id:
            query = query.where(TestCase.project_id == project_id)
            count_query = count_query.where(TestCase.project_id == project_id)
        if folder_id:
            query = query.where(TestCase.folder_id == folder_id)
            count_query = count_query.where(TestCase.folder_id == folder_id)
        if priority:
            from src.app.db.schemas.enums import Priority

            query = query.where(TestCase.priority == Priority(priority))
            count_query = count_query.where(TestCase.priority == Priority(priority))
        if state:
            query = query.where(TestCase.state == TestCaseState(state))
            count_query = count_query.where(TestCase.state == TestCaseState(state))

        # Get total count
        result = await self.db.execute(count_query)
        total = result.scalar_one()

        # Get paginated results
        query = query.order_by(TestCase.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(query)
        cases = result.scalars().all()

        return (
            [TestCaseInfo.model_validate(c) for c in cases],
            total,
        )
