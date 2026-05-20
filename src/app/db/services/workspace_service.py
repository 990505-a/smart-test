"""Workspace service.

Business logic layer for workspace CRUD operations with directory
auto-provisioning and skill copying from the default workspace.
"""

import re
import shutil
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.config import settings
from src.app.db.repositories.workspace_repo import WorkspaceRepository
from src.app.db.schemas.workspace import WorkspaceCreate, WorkspaceInfo, WorkspaceUpdate
from src.app.db.utils.exceptions import ConflictException, NotFoundException

# Subdirectories provisioned for each workspace
SUBDIRS = ["api", "web", "testcase", "attachments", "scripts"]


class WorkspaceService:
    """Workspace service handling business logic for workspace CRUD."""

    def __init__(self, db: AsyncSession):
        self.repo = WorkspaceRepository(db)

    async def _ensure_default(self) -> None:
        """Auto-seed the default workspace if the table is empty.

        Creates a workspace with slug='default', name='Default',
        and is_default=True when no workspaces exist yet.
        """
        count = await self.repo.count()
        if count == 0:
            await self.repo.create(
                slug="default",
                name="Default",
                description="Default workspace",
                is_default=True,
            )

    @staticmethod
    def _slugify(name: str) -> str:
        """Convert a display name to a URL-safe slug.

        Args:
            name: Display name to slugify.

        Returns:
            URL-safe slug string, or 'workspace' if result is empty.
        """
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return slug if slug else "workspace"

    async def list_workspaces(self) -> list[WorkspaceInfo]:
        """List all workspaces.

        Auto-seeds the default workspace on first call if table is empty.

        Returns:
            List of WorkspaceInfo instances.
        """
        await self._ensure_default()
        workspaces = await self.repo.get_all(offset=0, limit=100)
        return [WorkspaceInfo.model_validate(w) for w in workspaces]

    async def create_workspace(self, data: WorkspaceCreate) -> WorkspaceInfo:
        """Create a new workspace with directory provisioning and skill copying.

        Args:
            data: Workspace creation data.

        Returns:
            Created WorkspaceInfo.

        Raises:
            ConflictException: Workspace with same slug already exists.
        """
        # 1. Derive slug
        slug = data.slug or self._slugify(data.name)

        # 2. Check uniqueness
        existing = await self.repo.get_by_slug(slug)
        if existing:
            raise ConflictException(f"Workspace with slug '{slug}' already exists")

        # 3. Create DB record
        workspace = await self.repo.create(
            slug=slug,
            name=data.name,
            description=data.description,
            is_default=False,
        )

        # 4. Provision directories
        workspace_dir: Path = settings.workspace_dir / slug
        for subdir in SUBDIRS:
            (workspace_dir / subdir).mkdir(parents=True, exist_ok=True)

        # 5. Copy skills from default workspace
        for agent_subdir in ["api/skills", "web/skills"]:
            src = settings.workspace_dir / "default" / agent_subdir
            dst = workspace_dir / agent_subdir
            if src.exists() and not dst.exists():
                shutil.copytree(src, dst)

        return WorkspaceInfo.model_validate(workspace)

    async def delete_workspace(self, slug: str) -> str:
        """Delete a workspace by slug.

        The default workspace cannot be deleted.

        Args:
            slug: Workspace slug.

        Returns:
            Confirmation message.

        Raises:
            NotFoundException: Workspace not found.
            ConflictException: Attempting to delete the default workspace.
        """
        # 1. Get workspace
        workspace = await self.repo.get_by_slug(slug)
        if not workspace:
            raise NotFoundException(resource="Workspace", identifier=slug)

        # 2. Protect default workspace
        if workspace.is_default:
            raise ConflictException("Cannot delete the default workspace")

        # 3. Remove directory
        workspace_dir: Path = settings.workspace_dir / slug
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir)

        # 4. Delete DB record
        await self.repo.delete(workspace)

        return f"Workspace '{slug}' deleted successfully"
