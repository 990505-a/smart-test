"""API dependency injection.

Provides FastAPI dependency factories and type aliases for
services, pagination, and database sessions.
Adapted from classroom deps.py:
- Removed MongoDB, User auth dependencies (D-04)
- Removed CurrentUserIdDep (no auth per D-04)
"""

from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.database import get_db
from src.app.db.schemas.pagination import PaginationParams
from src.app.db.services.project_service import ProjectService
from src.app.db.services.folder_service import FolderService


async def get_project_service(
    db: AsyncSession = Depends(get_db),
) -> ProjectService:
    """Create ProjectService instance with injected DB session."""
    return ProjectService(db)


async def get_folder_service(
    db: AsyncSession = Depends(get_db),
) -> FolderService:
    """Create FolderService instance with injected DB session."""
    return FolderService(db)


def get_pagination_params(
    p: int = Query(
        default=1,
        ge=1,
        description="Page number, starting from 1",
    ),
    page_size: int = Query(
        default=30,
        ge=1,
        le=300,
        description="Per-page count, default 30, max 300",
    ),
) -> PaginationParams:
    """Extract pagination parameters from query string."""
    return PaginationParams(
        p=p,
        page_size=page_size,
    )


# Type aliases for dependency injection
DbSessionDep = Annotated[AsyncSession, Depends(get_db)]
PaginationDep = Annotated[PaginationParams, Depends(get_pagination_params)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
FolderServiceDep = Annotated[FolderService, Depends(get_folder_service)]
