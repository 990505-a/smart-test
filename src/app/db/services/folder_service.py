"""Folder service.

Business logic layer for folder CRUD with hierarchical tree support.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.folder import Folder
from src.app.db.repositories.folder_repo import FolderRepository
from src.app.db.repositories.project_repo import ProjectRepository
from src.app.db.schemas.enums import FolderType
from src.app.db.schemas.folder import (
    FolderCreate,
    FolderInfo,
    FolderTreeNode,
    FolderUpdate,
)
from src.app.db.utils.exceptions import NotFoundException


class FolderService:
    """Service for folder business logic."""

    def __init__(self, db: AsyncSession):
        self.repo = FolderRepository(db)
        self.project_repo = ProjectRepository(db)
        self.db = db

    def _build_tree(self, folders: list[Folder]) -> list[FolderTreeNode]:
        """Build tree from flat folder list by parent_id relationships."""
        folder_map: dict[str, FolderTreeNode] = {}
        roots: list[FolderTreeNode] = []
        for f in folders:
            node = FolderTreeNode.model_validate(f)
            node.children = []
            folder_map[str(f.id)] = node
        for f in folders:
            node = folder_map[str(f.id)]
            if f.parent_id and str(f.parent_id) in folder_map:
                folder_map[str(f.parent_id)].children.append(node)
            else:
                roots.append(node)
        return roots

    async def get_folders(self, project_id: UUID) -> list[FolderInfo]:
        """Get all folders for a project."""
        folders = await self.repo.get_by_project(project_id)
        return [FolderInfo.model_validate(f) for f in folders]

    async def get_folder_tree(self, project_id: UUID) -> list[FolderTreeNode]:
        """Get folder tree structure for a project."""
        folders = await self.repo.get_by_project(project_id)
        return self._build_tree(folders)

    async def create_folder(self, data: FolderCreate) -> FolderInfo:
        """Create a folder."""
        project = await self.project_repo.get_by_id(data.project_id)
        if not project:
            raise NotFoundException("Project", str(data.project_id))

        folder = Folder(
            project_id=data.project_id,
            parent_id=data.parent_id,
            name=data.name,
            description=data.description,
            folder_type=data.folder_type,
        )
        self.db.add(folder)
        await self.db.flush()
        await self.db.refresh(folder)
        return FolderInfo.model_validate(folder)

    async def update_folder(
        self, folder_id: UUID, data: FolderUpdate
    ) -> FolderInfo:
        """Update a folder."""
        folder = await self.repo.get_by_id(folder_id)
        if not folder:
            raise NotFoundException("Folder", str(folder_id))

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if hasattr(folder, key) and value is not None:
                setattr(folder, key, value)

        await self.db.flush()
        await self.db.refresh(folder)
        return FolderInfo.model_validate(folder)

    async def delete_folder(self, folder_id: UUID) -> str:
        """Delete a folder."""
        folder = await self.repo.get_by_id(folder_id)
        if not folder:
            raise NotFoundException("Folder", str(folder_id))
        await self.repo.delete(folder)
        return f"Folder {folder_id} deleted successfully"
