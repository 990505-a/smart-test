"""Project service.

Business logic layer for project CRUD operations.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.project import DEFAULT_USER_ID, Project
from src.app.db.repositories.project_repo import ProjectRepository
from src.app.db.schemas.project import ProjectCreate, ProjectInfo, ProjectUpdate
from src.app.db.utils.exceptions import NotFoundException
from src.app.db.utils.identifier import generate_identifier_simple


class ProjectService:
    """Service for project business logic."""

    def __init__(self, db: AsyncSession):
        self.repo = ProjectRepository(db)
        self.db = db

    async def get_projects(
        self, offset: int = 0, limit: int = 30
    ) -> tuple[list[ProjectInfo], int]:
        """List projects with pagination."""
        total = await self.repo.count()
        projects = await self.repo.get_all(offset=offset, limit=limit)
        return ([ProjectInfo.model_validate(p) for p in projects], total)

    async def get_project(self, identifier: str) -> ProjectInfo:
        """Get a project by identifier."""
        project = await self.repo.get_by_identifier(identifier)
        if not project:
            raise NotFoundException("Project", identifier)
        return ProjectInfo.model_validate(project)

    async def create_project(self, data: ProjectCreate) -> ProjectInfo:
        """Create a new project."""
        identifier = generate_identifier_simple("PR")
        project = await self.repo.create(
            identifier=identifier,
            name=data.name,
            description=data.description,
            created_by=DEFAULT_USER_ID,
        )
        return ProjectInfo.model_validate(project)

    async def update_project(
        self, identifier: str, data: ProjectUpdate
    ) -> ProjectInfo:
        """Update a project."""
        project = await self.repo.get_by_identifier(identifier)
        if not project:
            raise NotFoundException("Project", identifier)
        update_data = data.model_dump(exclude_unset=True)
        project = await self.repo.update(project, **update_data)
        return ProjectInfo.model_validate(project)

    async def delete_project(self, identifier: str) -> str:
        """Delete a project."""
        project = await self.repo.get_by_identifier(identifier)
        if not project:
            raise NotFoundException("Project", identifier)
        await self.repo.delete(project)
        return f"Project {identifier} deleted successfully"
