"""API dependency injection.

Provides FastAPI dependency factories and type aliases for
database sessions, pagination, and service instances.
Per D-04: no auth dependencies, uses DEFAULT_USER_ID.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.database import get_db
from src.app.db.schemas.pagination import PaginationParams


# Pagination dependency
def get_pagination_params(
    p: int = 1,
    page_size: int = 30,
) -> PaginationParams:
    """Create pagination parameters from query params."""
    return PaginationParams(p=p, page_size=page_size)


PaginationDep = Annotated[PaginationParams, Depends(get_pagination_params)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db)]


# Project service
async def get_project_service(db: DbSessionDep) -> "ProjectService":
    from src.app.db.services.project_service import ProjectService

    return ProjectService(db)


ProjectServiceDep = Annotated["ProjectService", Depends(get_project_service)]


# Attachment service
async def get_attachment_service(db: DbSessionDep) -> "AttachmentService":
    from src.app.db.services.attachment_service import AttachmentService

    return AttachmentService(db)


AttachmentServiceDep = Annotated["AttachmentService", Depends(get_attachment_service)]


# Workspace service
async def get_workspace_service(db: DbSessionDep) -> "WorkspaceService":
    from src.app.db.services.workspace_service import WorkspaceService

    return WorkspaceService(db)


WorkspaceServiceDep = Annotated["WorkspaceService", Depends(get_workspace_service)]


# Configuration service
async def get_configuration_service(db: DbSessionDep) -> "ConfigurationService":
    from src.app.db.services.configuration_service import ConfigurationService

    return ConfigurationService(db)


ConfigurationServiceDep = Annotated["ConfigurationService", Depends(get_configuration_service)]


# Memory service
async def get_memory_service(db: DbSessionDep) -> "MemoryService":
    from src.app.db.services.memory_service import MemoryService

    return MemoryService(db)


MemoryServiceDep = Annotated["MemoryService", Depends(get_memory_service)]
