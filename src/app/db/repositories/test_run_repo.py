"""Test run repository.

Provides test run-specific database queries extending BaseRepository.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.db.models.test_run import TestRun, TestRunTestCase
from src.app.db.repositories.base import BaseRepository


class TestRunRepository(BaseRepository[TestRun]):
    """Repository for test run CRUD with denormalized stats."""

    def __init__(self, session: AsyncSession):
        super().__init__(TestRun, session)

    async def get_by_identifier(self, identifier: str) -> Optional[TestRun]:
        """Get a test run by its identifier (e.g. TR-123)."""
        result = await self.session.execute(
            select(TestRun)
            .options(selectinload(TestRun.test_run_cases))
            .where(TestRun.identifier == identifier)
        )
        return result.scalar_one_or_none()

    async def get_by_project(
        self,
        project_id: UUID,
        offset: int = 0,
        limit: int = 30,
    ) -> list[TestRun]:
        """Get test runs by project with pagination."""
        result = await self.session.execute(
            select(TestRun)
            .options(selectinload(TestRun.test_run_cases))
            .where(TestRun.project_id == project_id)
            .order_by(TestRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_project(self, project_id: UUID) -> int:
        """Count test runs in a project."""
        result = await self.session.execute(
            select(func.count())
            .select_from(TestRun)
            .where(TestRun.project_id == project_id)
        )
        return result.scalar_one()

    async def get_with_cases(self, test_run_id: UUID) -> Optional[TestRun]:
        """Get a test run with eagerly loaded test case associations."""
        result = await self.session.execute(
            select(TestRun)
            .options(selectinload(TestRun.test_run_cases))
            .where(TestRun.id == test_run_id)
        )
        return result.scalar_one_or_none()

    async def add_test_cases(
        self, test_run_id: UUID, test_case_ids: list[UUID]
    ) -> list[TestRunTestCase]:
        """Add test cases to a test run."""
        from src.app.db.schemas.enums import TestResultStatus

        associations = []
        for tc_id in test_case_ids:
            run_case = TestRunTestCase(
                test_run_id=test_run_id,
                test_case_id=tc_id,
                latest_status=TestResultStatus.NOT_EXECUTED,
            )
            self.session.add(run_case)
            associations.append(run_case)
        await self.session.flush()
        return associations
