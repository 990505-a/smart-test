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


# Folder service
async def get_folder_service(db: DbSessionDep) -> "FolderService":
    from src.app.db.services.folder_service import FolderService

    return FolderService(db)


FolderServiceDep = Annotated["FolderService", Depends(get_folder_service)]


# Test case service
async def get_test_case_service(db: DbSessionDep) -> "TestCaseService":
    from src.app.db.services.test_case_service import TestCaseService

    return TestCaseService(db)


TestCaseServiceDep = Annotated["TestCaseService", Depends(get_test_case_service)]


# Test run service
async def get_test_run_service(db: DbSessionDep) -> "TestRunService":
    from src.app.db.services.test_run_service import TestRunService

    return TestRunService(db)


TestRunServiceDep = Annotated["TestRunService", Depends(get_test_run_service)]


# Test result service
async def get_test_result_service(db: DbSessionDep) -> "TestResultService":
    from src.app.db.services.test_result_service import TestResultService

    return TestResultService(db)


TestResultServiceDep = Annotated["TestResultService", Depends(get_test_result_service)]


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
