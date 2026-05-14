"""Test result service.

Business logic layer for test result and step result management.
Updates TestRunTestCase latest_status after each result.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.test_result import TestResult, TestStepResult
from src.app.db.models.test_run import TestRunTestCase
from src.app.db.repositories.test_result_repo import TestResultRepository
from src.app.db.schemas.enums import TestResultStatus
from src.app.db.schemas.test_result import (
    TestResultCreate,
    TestResultInfo,
)
from src.app.db.utils.exceptions import NotFoundException


class TestResultService:
    """Service for test result business logic."""

    def __init__(self, db: AsyncSession):
        self.repo = TestResultRepository(db)
        self.db = db

    async def create_result(self, data: TestResultCreate) -> TestResultInfo:
        """Create a test result with step results and update run stats."""
        # Create the main result
        result_data = {
            "test_run_id": data.test_run_id,
            "test_case_id": data.test_case_id,
            "status": data.status,
            "description": data.description,
            "duration_ms": data.duration_ms,
        }

        step_results_data = [
            {
                "step_index": sr.step_index,
                "status": sr.status,
                "description": sr.description,
            }
            for sr in data.step_results
        ]

        test_result = await self.repo.create_with_steps(result_data, step_results_data)

        # Update TestRunTestCase latest_status
        result = await self.db.execute(
            select(TestRunTestCase).where(
                TestRunTestCase.test_run_id == data.test_run_id,
                TestRunTestCase.test_case_id == data.test_case_id,
            )
        )
        run_case = result.scalar_one_or_none()
        if run_case:
            run_case.latest_status = data.status
            run_case.latest_result_id = test_result.id
            await self.db.flush()

        # Update test run denormalized stats
        from src.app.db.services.test_run_service import TestRunService

        run_service = TestRunService(self.db)
        await run_service.update_stats(data.test_run_id)

        # Reload with step results
        test_result = await self.repo.get_with_steps(test_result.id)
        return TestResultInfo.model_validate(test_result)

    async def get_results_by_run(self, test_run_id: UUID) -> list[TestResultInfo]:
        """Get all test results for a test run."""
        results = await self.repo.get_by_test_run(test_run_id)
        return [TestResultInfo.model_validate(r) for r in results]
