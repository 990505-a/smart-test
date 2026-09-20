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
