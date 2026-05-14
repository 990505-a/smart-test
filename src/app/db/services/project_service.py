"""Project service.

Business logic layer for project CRUD operations.
Follows classroom layered architecture: API routes -> Services -> Repositories -> Models.
"""

from src.app.db.models.project import DEFAULT_USER_ID
from src.app.db.repositories.project_repo import ProjectRepository
from src.app.db.schemas.project import ProjectCreate, ProjectInfo, ProjectUpdate
from src.app.db.utils.exceptions import NotFoundException
from src.app.db.utils.identifier import generate_identifier

from sqlalchemy.ext.asyncio import AsyncSession


class ProjectService:
    """Project service handling business logic for project CRUD."""

    def __init__(self, db: AsyncSession):
        self.repo = ProjectRepository(db)

    async def get_projects(
        self,
        offset: int = 0,
        limit: int = 30,
    ) -> tuple[list[ProjectInfo], int]:
        """Get paginated project list.

        Args:
            offset: Number of records to skip.
            limit: Maximum records to return.

        Returns:
            Tuple of (project info list, total count).
        """
        projects = await self.repo.get_all(offset=offset, limit=limit)
        total = await self.repo.count()
        project_infos = [ProjectInfo.model_validate(p) for p in projects]
        return project_infos, total

    async def get_project(self, identifier: str) -> ProjectInfo:
        """Get a project by its identifier.

        Args:
            identifier: Project identifier (e.g. PR-0001).

        Returns:
            ProjectInfo instance.

        Raises:
            NotFoundException: Project not found.
        """
        project = await self.repo.get_by_identifier(identifier)
        if not project:
            raise NotFoundException(resource="Project", identifier=identifier)
        return ProjectInfo.model_validate(project)

    async def create_project(self, data: ProjectCreate) -> ProjectInfo:
        """Create a new project with auto-generated identifier.

        Uses PostgreSQL advisory lock for concurrency-safe identifier generation.

        Args:
            data: Project creation data.

        Returns:
            Created ProjectInfo.
        """
        identifier = await generate_identifier(prefix="PR", lock_key="project_identifier_seq")
        project = await self.repo.create(
            identifier=identifier,
            name=data.name,
            description=data.description,
            created_by=DEFAULT_USER_ID,
        )
        return ProjectInfo.model_validate(project)

    async def update_project(
        self,
        identifier: str,
        data: ProjectUpdate,
    ) -> ProjectInfo:
        """Update a project by identifier.

        Only updates fields that are explicitly provided (non-None).

        Args:
            identifier: Project identifier.
            data: Update data with optional fields.

        Returns:
            Updated ProjectInfo.

        Raises:
            NotFoundException: Project not found.
        """
        project = await self.repo.get_by_identifier(identifier)
        if not project:
            raise NotFoundException(resource="Project", identifier=identifier)

        update_data = data.model_dump(exclude_unset=True)
        project = await self.repo.update(project, **update_data)
        return ProjectInfo.model_validate(project)

    async def delete_project(self, identifier: str) -> str:
        """Delete a project by identifier.

        Args:
            identifier: Project identifier.

        Returns:
            Confirmation message.

        Raises:
            NotFoundException: Project not found.
        """
        project = await self.repo.get_by_identifier(identifier)
        if not project:
            raise NotFoundException(resource="Project", identifier=identifier)

        await self.repo.delete(project)
        return f"Project {identifier} deleted successfully"
