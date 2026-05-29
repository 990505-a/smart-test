"""Test run service.

Business logic layer for test run CRUD with test case association
and denormalized stats management.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.test_run import TestRun, TestRunTestCase
from src.app.db.repositories.test_run_repo import TestRunRepository
from src.app.db.schemas.enums import TestResultStatus
from src.app.db.schemas.test_run import (
    TestRunCreate,
    TestRunInfo,
    TestRunUpdate,
)
from src.app.db.utils.exceptions import NotFoundException
from src.app.db.utils.identifier import generate_identifier_simple


class TestRunService:
    """Service for test run business logic."""

    def __init__(self, db: AsyncSession):
        self.repo = TestRunRepository(db)
        self.db = db

    async def create_run(self, data: TestRunCreate) -> TestRunInfo:
        """Create a test run with test cases from test_case_ids."""
        identifier = generate_identifier_simple("TR")
        test_run = TestRun(
            project_id=data.project_id,
            identifier=identifier,
            name=data.name,
            description=data.description,
            test_cases_count=len(data.test_case_ids),
            not_executed_count=len(data.test_case_ids),
        )
        self.db.add(test_run)
        await self.db.flush()

        # Add test case associations
        if data.test_case_ids:
            for tc_id in data.test_case_ids:
                run_case = TestRunTestCase(
                    test_run_id=test_run.id,
                    test_case_id=tc_id,
                    latest_status=TestResultStatus.NOT_EXECUTED,
                )
                self.db.add(run_case)
            await self.db.flush()

        # Reload with cases
        test_run = await self.repo.get_with_cases(test_run.id)
        return TestRunInfo.model_validate(test_run)

    async def get_with_cases(self, test_run_id: UUID) -> TestRunInfo:
        """Get a test run with its test case associations."""
        test_run = await self.repo.get_with_cases(test_run_id)
        if not test_run:
            raise NotFoundException("Test run", str(test_run_id))
        return TestRunInfo.model_validate(test_run)

    async def get_by_identifier(self, identifier: str) -> TestRunInfo:
        """Get a test run by its identifier."""
        test_run = await self.repo.get_by_identifier(identifier)
        if not test_run:
            raise NotFoundException("Test run", identifier)
        return TestRunInfo.model_validate(test_run)

    async def update_status(
        self, test_run_id: UUID, data: TestRunUpdate
    ) -> TestRunInfo:
        """Update a test run's status and metadata."""
        test_run = await self.repo.get_by_id(test_run_id)
        if not test_run:
            raise NotFoundException("Test run", str(test_run_id))

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if hasattr(test_run, key) and value is not None:
                setattr(test_run, key, value)

        await self.db.flush()
        test_run = await self.repo.get_with_cases(test_run.id)
        return TestRunInfo.model_validate(test_run)

    async def delete(self, test_run_id: UUID) -> str:
        """Delete a test run."""
        test_run = await self.repo.get_by_id(test_run_id)
        if not test_run:
            raise NotFoundException("Test run", str(test_run_id))
        identifier = test_run.identifier
        await self.repo.delete(test_run)
        return f"Test run {identifier} deleted successfully"

    async def list_by_project(
        self,
        project_id: UUID | None = None,
        offset: int = 0,
        limit: int = 30,
    ) -> tuple[list[TestRunInfo], int]:
        """List test runs by project with pagination. If project_id is None, list all."""
        from sqlalchemy import func, select

        base_q = select(func.count()).select_from(TestRun)
        if project_id:
            base_q = base_q.where(TestRun.project_id == project_id)
        count_result = await self.db.execute(base_q)
        total = count_result.scalar_one()

        if project_id:
            runs = await self.repo.get_by_project(project_id, offset, limit)
        else:
            runs = await self.repo.get_all(offset=offset, limit=limit)
        return ([TestRunInfo.model_validate(r) for r in runs], total)

    async def update_stats(self, test_run_id: UUID) -> None:
        """Recalculate denormalized stats for a test run."""
        from sqlalchemy import func, select

        test_run = await self.repo.get_by_id(test_run_id)
        if not test_run:
            return

        result = await self.db.execute(
            select(
                TestRunTestCase.latest_status,
                func.count(TestRunTestCase.id),
            )
            .where(TestRunTestCase.test_run_id == test_run_id)
            .group_by(TestRunTestCase.latest_status)
        )
        status_counts = dict(result.all())

        test_run.passed_count = status_counts.get(TestResultStatus.PASSED, 0)
        test_run.failed_count = status_counts.get(TestResultStatus.FAILED, 0)
        test_run.skipped_count = status_counts.get(TestResultStatus.SKIPPED, 0)
        test_run.blocked_count = status_counts.get(TestResultStatus.BLOCKED, 0)
        test_run.not_executed_count = status_counts.get(
            TestResultStatus.NOT_EXECUTED, 0
        )
        test_run.test_cases_count = sum(status_counts.values())
        await self.db.flush()
