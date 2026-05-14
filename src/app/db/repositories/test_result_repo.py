"""Test result repository.

Provides test result-specific database queries extending BaseRepository.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.db.models.test_result import TestResult, TestStepResult
from src.app.db.repositories.base import BaseRepository


class TestResultRepository(BaseRepository[TestResult]):
    """Repository for test result CRUD with step results."""

    def __init__(self, session: AsyncSession):
        super().__init__(TestResult, session)

    async def get_by_test_run(self, test_run_id: UUID) -> list[TestResult]:
        """Get all test results for a test run."""
        result = await self.session.execute(
            select(TestResult)
            .options(selectinload(TestResult.step_results))
            .where(TestResult.test_run_id == test_run_id)
            .order_by(TestResult.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_test_case(self, test_case_id: UUID) -> list[TestResult]:
        """Get all test results for a test case."""
        result = await self.session.execute(
            select(TestResult)
            .options(selectinload(TestResult.step_results))
            .where(TestResult.test_case_id == test_case_id)
            .order_by(TestResult.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_with_steps(self, test_result_id: UUID) -> Optional[TestResult]:
        """Get a test result with eagerly loaded step results."""
        result = await self.session.execute(
            select(TestResult)
            .options(selectinload(TestResult.step_results))
            .where(TestResult.id == test_result_id)
        )
        return result.scalar_one_or_none()

    async def create_with_steps(
        self,
        data: dict,
        step_results_data: list[dict],
    ) -> TestResult:
        """Create a test result with step results in a single operation."""
        test_result = TestResult(**data)
        self.session.add(test_result)
        await self.session.flush()

        for step_data in step_results_data:
            step_result = TestStepResult(
                test_result_id=test_result.id,
                **step_data,
            )
            self.session.add(step_result)

        await self.session.flush()
        await self.session.refresh(test_result)
        return test_result
