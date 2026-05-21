"""Web test service.

Business logic layer for web test CRUD, test run, and result management.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.db.models.web_test import WebTest, WebTestResult, WebTestRun
from src.app.db.repositories.web_test_repo import (
    WebTestRepository,
    WebTestResultRepository,
    WebTestRunRepository,
)
from src.app.db.schemas.web_test import (
    WebTestInfo,
    WebTestResultInfo,
    WebTestRunInfo,
)
from src.app.db.utils.exceptions import NotFoundException
from src.app.db.utils.identifier import generate_identifier_simple


class WebTestService:
    """Service for web test business logic with run and result management."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = WebTestRepository(db)
        self.run_repo = WebTestRunRepository(db)
        self.result_repo = WebTestResultRepository(db)

    # --- Web Test CRUD ---

    async def create_web_test(
        self,
        project_id: UUID,
        data: dict,
    ) -> WebTestInfo:
        """Create a new web test."""
        identifier = generate_identifier_simple("WT")
        web_test = WebTest(
            project_id=project_id,
            folder_id=data.get("folder_id"),
            function_id=data.get("function_id"),
            sub_function_id=data.get("sub_function_id"),
            identifier=identifier,
            name=data.get("name", ""),
            description=data.get("description"),
            base_url=data.get("base_url"),
            test_config=data.get("test_config", {}),
            target_pages=data.get("target_pages"),
            test_flows=data.get("test_flows"),
        )
        self.db.add(web_test)
        await self.db.flush()
        await self.db.refresh(web_test)
        return WebTestInfo.model_validate(web_test)

    async def get_web_test(self, test_id: UUID) -> WebTestInfo:
        """Get a web test by ID."""
        result = await self.db.execute(
            select(WebTest)
            .options(selectinload(WebTest.test_runs))
            .where(WebTest.id == test_id)
        )
        web_test = result.scalar_one_or_none()
        if not web_test:
            raise NotFoundException("Web test", str(test_id))
        return WebTestInfo.model_validate(web_test)

    async def update_web_test(
        self,
        test_id: UUID,
        data: dict,
    ) -> WebTestInfo:
        """Update a web test."""
        web_test = await self.repo.get_by_id(test_id)
        if not web_test:
            raise NotFoundException("Web test", str(test_id))

        for key, value in data.items():
            if hasattr(web_test, key) and value is not None:
                setattr(web_test, key, value)

        await self.db.flush()
        await self.db.refresh(web_test)
        return WebTestInfo.model_validate(web_test)

    async def delete_web_test(self, test_id: UUID) -> str:
        """Delete a web test."""
        web_test = await self.repo.get_by_id(test_id)
        if not web_test:
            raise NotFoundException("Web test", str(test_id))
        identifier = web_test.identifier
        await self.repo.delete(web_test)
        return f"Web test {identifier} deleted successfully"

    async def list_web_tests(
        self,
        project_id: UUID,
        function_id: Optional[UUID] = None,
        sub_function_id: Optional[UUID] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 30,
    ) -> tuple[list[WebTestInfo], int]:
        """List web tests with filtering and pagination."""
        offset = (page - 1) * page_size

        tests = await self.repo.list_by_project(
            project_id, function_id=function_id, sub_function_id=sub_function_id,
            search=search, offset=offset, limit=page_size,
        )
        total = await self.repo.count_by_project(
            project_id, function_id=function_id, sub_function_id=sub_function_id,
            search=search,
        )
        return ([WebTestInfo.model_validate(t) for t in tests], total)

    # --- Test Run Management ---

    async def create_test_run(
        self,
        web_test_id: UUID,
        execution_config: Optional[dict] = None,
    ) -> WebTestRunInfo:
        """Create a new test run for a web test."""
        web_test = await self.repo.get_by_id(web_test_id)
        if not web_test:
            raise NotFoundException("Web test", str(web_test_id))

        identifier = generate_identifier_simple("WTR")
        test_run = WebTestRun(
            project_id=web_test.project_id,
            web_test_id=web_test_id,
            identifier=identifier,
            status="pending",
            execution_config=execution_config,
        )
        self.db.add(test_run)
        await self.db.flush()
        await self.db.refresh(test_run)
        return WebTestRunInfo.model_validate(test_run)

    async def get_test_run(self, run_id: UUID) -> WebTestRunInfo:
        """Get a test run by ID."""
        result = await self.db.execute(
            select(WebTestRun)
            .options(selectinload(WebTestRun.test_results))
            .where(WebTestRun.id == run_id)
        )
        test_run = result.scalar_one_or_none()
        if not test_run:
            raise NotFoundException("Web test run", str(run_id))
        return WebTestRunInfo.model_validate(test_run)

    async def list_test_runs(
        self,
        web_test_id: UUID,
        limit: int = 30,
    ) -> list[WebTestRunInfo]:
        """List test runs for a web test."""
        runs = await self.run_repo.list_by_web_test(web_test_id, limit)
        return [WebTestRunInfo.model_validate(r) for r in runs]

    async def get_test_results(self, run_id: UUID) -> list[WebTestResultInfo]:
        """Get all test results for a run."""
        results = await self.result_repo.list_by_run(run_id)
        return [WebTestResultInfo.model_validate(r) for r in results]
