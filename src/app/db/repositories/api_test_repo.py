"""API test repository.

Provides API test-specific database queries extending BaseRepository.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.db.models.api_test import APITest, APITestResult, APITestRun
from src.app.db.repositories.base import BaseRepository


class APITestRepository(BaseRepository[APITest]):
    """Repository for API test CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(APITest, session)

    async def list_by_project(
        self,
        project_id: UUID,
        search: Optional[str] = None,
        script_format: Optional[str] = None,
        offset: int = 0,
        limit: int = 30,
    ) -> list[APITest]:
        """List API tests by project with optional filters."""
        query = select(APITest).where(APITest.project_id == project_id)

        if search:
            query = query.where(APITest.name.ilike(f"%{search}%"))
        if script_format:
            query = query.where(APITest.script_format == script_format)

        query = query.order_by(APITest.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_by_project(
        self,
        project_id: UUID,
        search: Optional[str] = None,
        script_format: Optional[str] = None,
    ) -> int:
        """Count API tests in a project with optional filters."""
        query = select(func.count()).select_from(APITest).where(
            APITest.project_id == project_id
        )

        if search:
            query = query.where(APITest.name.ilike(f"%{search}%"))
        if script_format:
            query = query.where(APITest.script_format == script_format)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_by_identifier(self, identifier: str) -> Optional[APITest]:
        """Get an API test by its identifier."""
        result = await self.session.execute(
            select(APITest).where(APITest.identifier == identifier)
        )
        return result.scalar_one_or_none()


class APITestRunRepository(BaseRepository[APITestRun]):
    """Repository for API test run CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(APITestRun, session)

    async def list_by_api_test(
        self,
        api_test_id: UUID,
        limit: int = 30,
    ) -> list[APITestRun]:
        """List test runs for an API test."""
        result = await self.session.execute(
            select(APITestRun)
            .options(selectinload(APITestRun.test_results))
            .where(APITestRun.api_test_id == api_test_id)
            .order_by(APITestRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        run_id: UUID,
        status: str,
        **stats,
    ) -> Optional[APITestRun]:
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


class APITestResultRepository(BaseRepository[APITestResult]):
    """Repository for API test result CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(APITestResult, session)

    async def create_batch(
        self, results: list[dict]
    ) -> list[APITestResult]:
        """Create multiple test results in batch."""
        instances = []
        for data in results:
            instance = APITestResult(**data)
            self.session.add(instance)
            instances.append(instance)
        await self.session.flush()
        for instance in instances:
            await self.session.refresh(instance)
        return instances

    async def list_by_run(self, run_id: UUID) -> list[APITestResult]:
        """List test results for a run."""
        result = await self.session.execute(
            select(APITestResult)
            .where(APITestResult.test_run_id == run_id)
            .order_by(APITestResult.created_at)
        )
        return list(result.scalars().all())
