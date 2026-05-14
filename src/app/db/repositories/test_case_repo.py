"""Test case repository.

Provides test case-specific database queries extending BaseRepository.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.db.models.test_case import TestCase, TestStep
from src.app.db.repositories.base import BaseRepository


class TestCaseRepository(BaseRepository[TestCase]):
    """Repository for test case CRUD with step management."""

    def __init__(self, session: AsyncSession):
        super().__init__(TestCase, session)

    async def get_by_identifier(self, identifier: str) -> Optional[TestCase]:
        """Get a test case by its identifier (e.g. TC-1234)."""
        result = await self.session.execute(
            select(TestCase)
            .options(selectinload(TestCase.steps))
            .where(TestCase.identifier == identifier)
        )
        return result.scalar_one_or_none()

    async def get_by_project(
        self,
        project_id: UUID,
        offset: int = 0,
        limit: int = 30,
    ) -> list[TestCase]:
        """Get test cases by project with pagination."""
        result = await self.session.execute(
            select(TestCase)
            .options(selectinload(TestCase.steps))
            .where(TestCase.project_id == project_id)
            .order_by(TestCase.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_project(self, project_id: UUID) -> int:
        """Count test cases in a project."""
        result = await self.session.execute(
            select(func.count())
            .select_from(TestCase)
            .where(TestCase.project_id == project_id)
        )
        return result.scalar_one()

    async def get_by_folder(self, folder_id: UUID) -> list[TestCase]:
        """Get test cases by folder."""
        result = await self.session.execute(
            select(TestCase)
            .options(selectinload(TestCase.steps))
            .where(TestCase.folder_id == folder_id)
            .order_by(TestCase.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_with_steps(self, test_case_id: UUID) -> Optional[TestCase]:
        """Get a test case with eagerly loaded steps."""
        result = await self.session.execute(
            select(TestCase)
            .options(selectinload(TestCase.steps))
            .where(TestCase.id == test_case_id)
        )
        return result.scalar_one_or_none()
