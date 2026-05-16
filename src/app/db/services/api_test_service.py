"""API test service.

Business logic layer for API test CRUD with script management
and test run operations.
"""

import os
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.db.models.api_test import APITest, APITestResult, APITestRun
from src.app.db.repositories.api_test_repo import (
    APITestRepository,
    APITestResultRepository,
    APITestRunRepository,
)
from src.app.db.schemas.api_test import (
    APITestCreate,
    APITestInfo,
    APITestResultInfo,
    APITestRunInfo,
    APITestUpdate,
)
from src.app.db.utils.exceptions import NotFoundException
from src.app.db.utils.identifier import generate_identifier_simple
from src.app.core.config import settings


class APITestService:
    """Service for API test business logic with script and run management."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = APITestRepository(db)
        self.run_repo = APITestRunRepository(db)
        self.result_repo = APITestResultRepository(db)

    # --- API Test CRUD ---

    async def create_api_test(
        self,
        project_id: UUID,
        data: APITestCreate,
    ) -> APITestInfo:
        """Create a new API test."""
        identifier = generate_identifier_simple("AT")
        api_test = APITest(
            project_id=project_id,
            folder_id=data.folder_id,
            name=data.name,
            description=data.description,
            identifier=identifier,
            schema_url=data.schema_url,
            schema_type=data.schema_type or "openapi",
            script_format=data.script_format or "playwright",
            script_language=data.script_language or "typescript",
            test_config=data.test_config or {},
        )
        self.db.add(api_test)
        await self.db.flush()
        await self.db.refresh(api_test)
        return APITestInfo.model_validate(api_test)

    async def get_api_test(self, test_id: UUID) -> APITestInfo:
        """Get an API test by ID."""
        result = await self.db.execute(
            select(APITest)
            .options(selectinload(APITest.test_runs))
            .where(APITest.id == test_id)
        )
        api_test = result.scalar_one_or_none()
        if not api_test:
            raise NotFoundException("API test", str(test_id))
        return APITestInfo.model_validate(api_test)

    async def list_api_tests(
        self,
        project_id: UUID,
        search: Optional[str] = None,
        script_format: Optional[str] = None,
        page: int = 1,
        page_size: int = 30,
    ) -> tuple[list[APITestInfo], int]:
        """List API tests with filtering and pagination."""
        offset = (page - 1) * page_size

        tests = await self.repo.list_by_project(
            project_id, search=search, script_format=script_format,
            offset=offset, limit=page_size,
        )
        total = await self.repo.count_by_project(
            project_id, search=search, script_format=script_format,
        )
        return ([APITestInfo.model_validate(t) for t in tests], total)

    async def update_api_test(
        self,
        test_id: UUID,
        data: APITestUpdate,
    ) -> APITestInfo:
        """Update an API test."""
        api_test = await self.repo.get_by_id(test_id)
        if not api_test:
            raise NotFoundException("API test", str(test_id))

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if hasattr(api_test, key):
                setattr(api_test, key, value)

        await self.db.flush()
        await self.db.refresh(api_test)
        return APITestInfo.model_validate(api_test)

    async def delete_api_test(self, test_id: UUID) -> str:
        """Delete an API test."""
        api_test = await self.repo.get_by_id(test_id)
        if not api_test:
            raise NotFoundException("API test", str(test_id))
        identifier = api_test.identifier
        await self.repo.delete(api_test)
        return f"API test {identifier} deleted successfully"

    # --- Script Management ---

    async def save_script(
        self,
        project_id: UUID,
        test_id: UUID,
        content: str,
        script_format: Optional[str] = None,
    ) -> str:
        """Save script content to file and update test record."""
        api_test = await self.repo.get_by_id(test_id)
        if not api_test:
            raise NotFoundException("API test", str(test_id))

        # Determine file extension
        ext = ".spec.ts"
        if script_format == "python" or (not script_format and api_test.script_language == "python"):
            ext = "_test.py"

        # Build script path under workspace
        scripts_dir = settings.workspace_dir / "api" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        script_path = scripts_dir / f"{api_test.identifier}{ext}"
        script_path.write_text(content, encoding="utf-8")

        # Update model with relative path
        api_test.script_path = str(script_path)
        if script_format:
            api_test.script_format = script_format
        await self.db.flush()
        await self.db.refresh(api_test)

        return str(script_path)

    async def get_script(self, test_id: UUID) -> str:
        """Read script file content for an API test."""
        api_test = await self.repo.get_by_id(test_id)
        if not api_test:
            raise NotFoundException("API test", str(test_id))
        if not api_test.script_path:
            raise NotFoundException("API test script", str(test_id))

        script_path = api_test.script_path
        if not os.path.exists(script_path):
            raise NotFoundException("API test script file", script_path)

        with open(script_path, "r", encoding="utf-8") as f:
            return f.read()

    # --- Test Run Management ---

    async def create_test_run(
        self,
        api_test_id: UUID,
        execution_config: Optional[dict] = None,
    ) -> APITestRunInfo:
        """Create a new test run for an API test."""
        api_test = await self.repo.get_by_id(api_test_id)
        if not api_test:
            raise NotFoundException("API test", str(api_test_id))

        identifier = generate_identifier_simple("ATR")
        test_run = APITestRun(
            project_id=api_test.project_id,
            api_test_id=api_test_id,
            identifier=identifier,
            status="pending",
            execution_config=execution_config or {},
        )
        self.db.add(test_run)
        await self.db.flush()
        await self.db.refresh(test_run)
        return APITestRunInfo.model_validate(test_run)

    async def get_test_run(self, run_id: UUID) -> APITestRunInfo:
        """Get a test run by ID."""
        result = await self.db.execute(
            select(APITestRun)
            .options(selectinload(APITestRun.test_results))
            .where(APITestRun.id == run_id)
        )
        test_run = result.scalar_one_or_none()
        if not test_run:
            raise NotFoundException("API test run", str(run_id))
        return APITestRunInfo.model_validate(test_run)

    async def list_test_runs(
        self,
        api_test_id: UUID,
        limit: int = 30,
    ) -> list[APITestRunInfo]:
        """List test runs for an API test."""
        runs = await self.run_repo.list_by_api_test(api_test_id, limit)
        return [APITestRunInfo.model_validate(r) for r in runs]

    async def update_run_status(
        self,
        run_id: UUID,
        status: str,
        **stats,
    ) -> APITestRunInfo:
        """Update test run status and stats."""
        test_run = await self.run_repo.update_status(run_id, status, **stats)
        if not test_run:
            raise NotFoundException("API test run", str(run_id))
        return APITestRunInfo.model_validate(test_run)

    async def save_test_results(
        self,
        run_id: UUID,
        results: list[dict],
    ) -> list[APITestResultInfo]:
        """Save batch of test results for a run."""
        # Verify run exists
        test_run = await self.run_repo.get_by_id(run_id)
        if not test_run:
            raise NotFoundException("API test run", str(run_id))

        # Add run_id to each result dict
        for r in results:
            r["test_run_id"] = run_id

        instances = await self.result_repo.create_batch(results)
        return [APITestResultInfo.model_validate(i) for i in instances]

    async def get_test_results(self, run_id: UUID) -> list[APITestResultInfo]:
        """Get all test results for a run."""
        results = await self.result_repo.list_by_run(run_id)
        return [APITestResultInfo.model_validate(r) for r in results]
