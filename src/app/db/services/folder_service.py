"""Folder service.

Business logic layer for folder CRUD operations with hierarchical tree support.
Will be fully implemented in Task 2.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.folder import Folder
from src.app.db.repositories.folder_repo import FolderRepository
from src.app.db.repositories.project_repo import ProjectRepository
from src.app.db.schemas.folder import (
    FolderCreate,
    FolderInfo,
    FolderTreeNode,
    FolderUpdate,
)
from src.app.db.utils.exceptions import NotFoundException


class FolderService:
    """Folder service handling business logic for folder CRUD and tree building."""

    def __init__(self, db: AsyncSession):
        self.repo = FolderRepository(db)
        self.project_repo = ProjectRepository(db)

    def _build_tree(self, folders: list[Folder]) -> list[FolderTreeNode]:
        """Build a hierarchical tree from a flat folder list.

        Groups folders by parent_id relationships into a tree structure.

        Args:
            folders: Flat list of Folder model instances.

        Returns:
            List of FolderTreeNode roots with nested children.
        """
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
        """Get all folders for a project as flat list.

        Args:
            project_id: Project UUID.

        Returns:
            List of FolderInfo instances.
        """
        folders = await self.repo.get_by_project(project_id)
        return [FolderInfo.model_validate(f) for f in folders]

    async def get_folder_tree(self, project_id: UUID) -> list[FolderTreeNode]:
        """Get folder tree structure for a project.

        Args:
            project_id: Project UUID.

        Returns:
            List of FolderTreeNode roots with nested children.
        """
        folders = await self.repo.get_by_project(project_id)
        return self._build_tree(folders)

    async def create_folder(self, data: FolderCreate) -> FolderInfo:
        """Create a new folder.

        Validates that the project exists and the parent_id (if provided)
        belongs to the same project.

        Args:
            data: Folder creation data.

        Returns:
            Created FolderInfo.

        Raises:
            NotFoundException: Project or parent folder not found.
        """
        # Validate project exists
        project = await self.project_repo.get_by_id(data.project_id)
        if not project:
            raise NotFoundException(resource="Project", identifier=str(data.project_id))

        # Validate parent folder belongs to same project
        if data.parent_id:
            parent = await self.repo.get_by_id(data.parent_id)
            if not parent or parent.project_id != data.project_id:
                raise NotFoundException(resource="Parent folder", identifier=str(data.parent_id))

        folder = await self.repo.create(
            project_id=data.project_id,
            parent_id=data.parent_id,
            name=data.name,
            description=data.description,
            folder_type=data.folder_type,
        )
        return FolderInfo.model_validate(folder)

    async def update_folder(
        self,
        folder_id: UUID,
        data: FolderUpdate,
    ) -> FolderInfo:
        """Update a folder.

        Args:
            folder_id: Folder UUID.
            data: Update data with optional fields.

        Returns:
            Updated FolderInfo.

        Raises:
            NotFoundException: Folder not found.
        """
        folder = await self.repo.get_by_id(folder_id)
        if not folder:
            raise NotFoundException(resource="Folder", identifier=str(folder_id))

        update_data = data.model_dump(exclude_unset=True)
        # Remove parent_id from update if it's None and wasn't explicitly set
        if "parent_id" in update_data and update_data["parent_id"] is None:
            # Only move to root if explicitly set to None
            folder.parent_id = None
            del update_data["parent_id"]

        folder = await self.repo.update(folder, **update_data)
        return FolderInfo.model_validate(folder)

    async def delete_folder(self, folder_id: UUID) -> str:
        """Delete a folder. Cascade handles children.

        Args:
            folder_id: Folder UUID.

        Returns:
            Confirmation message.

        Raises:
            NotFoundException: Folder not found.
        """
        folder = await self.repo.get_by_id(folder_id)
        if not folder:
            raise NotFoundException(resource="Folder", identifier=str(folder_id))

        await self.repo.delete(folder)
        return f"Folder {folder_id} deleted successfully"
