"""Web test repository.

Provides web test, test run, and test result specific database queries
extending BaseRepository.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.db.models.web_test import WebTest, WebTestResult, WebTestRun
from src.app.db.repositories.base import BaseRepository


class WebTestRepository(BaseRepository[WebTest]):
    """Repository for web test CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(WebTest, session)

    async def list_by_project(
        self,
        project_id: UUID,
        function_id: Optional[UUID] = None,
        sub_function_id: Optional[UUID] = None,
        search: Optional[str] = None,
        offset: int = 0,
        limit: int = 30,
    ) -> list[WebTest]:
        """List web tests by project with optional filters."""
        query = select(WebTest).where(WebTest.project_id == project_id)

        if function_id:
            query = query.where(WebTest.function_id == function_id)
        if sub_function_id:
            query = query.where(WebTest.sub_function_id == sub_function_id)
        if search:
            query = query.where(WebTest.name.ilike(f"%{search}%"))

        query = query.order_by(WebTest.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_by_project(
        self,
        project_id: UUID,
        function_id: Optional[UUID] = None,
        sub_function_id: Optional[UUID] = None,
        search: Optional[str] = None,
    ) -> int:
        """Count web tests in a project with optional filters."""
        query = select(func.count()).select_from(WebTest).where(
            WebTest.project_id == project_id
        )

        if function_id:
            query = query.where(WebTest.function_id == function_id)
        if sub_function_id:
            query = query.where(WebTest.sub_function_id == sub_function_id)
        if search:
            query = query.where(WebTest.name.ilike(f"%{search}%"))

        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_by_identifier(self, identifier: str) -> Optional[WebTest]:
        """Get a web test by its identifier."""
        result = await self.session.execute(
            select(WebTest).where(WebTest.identifier == identifier)
        )
        return result.scalar_one_or_none()


class WebTestRunRepository(BaseRepository[WebTestRun]):
    """Repository for web test run CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(WebTestRun, session)

    async def list_by_web_test(
        self,
        web_test_id: UUID,
        limit: int = 30,
    ) -> list[WebTestRun]:
        """List test runs for a web test."""
        result = await self.session.execute(
            select(WebTestRun)
            .options(selectinload(WebTestRun.test_results))
            .where(WebTestRun.web_test_id == web_test_id)
            .order_by(WebTestRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        run_id: UUID,
        status: str,
        **stats,
    ) -> Optional[WebTestRun]:
        """Update test run status and stats."""
        run = await self.get_by_id(run_id)
        if not run:
            return None

        run.status = status
        for key, value in stats.items():
            if hasattr(run, key) and value is not None:
                setattr(run, key, value)

        await self.session.flush()
        await self.session.refresh(run)
        return run


class WebTestResultRepository(BaseRepository[WebTestResult]):
    """Repository for web test result CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(WebTestResult, session)

    async def create_batch(
        self, results: list[dict]
    ) -> list[WebTestResult]:
        """Create multiple test results in batch."""
        instances = []
        for data in results:
            instance = WebTestResult(**data)
            self.session.add(instance)
            instances.append(instance)
        await self.session.flush()
        for instance in instances:
            await self.session.refresh(instance)
        return instances

    async def list_by_run(self, run_id: UUID) -> list[WebTestResult]:
        """List test results for a run."""
        result = await self.session.execute(
            select(WebTestResult)
            .where(WebTestResult.test_run_id == run_id)
            .order_by(WebTestResult.created_at)
        )
        return list(result.scalars().all())
