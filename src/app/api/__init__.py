"""API router module.

Registers all API v2 endpoint routers under the /api/v2 prefix.
"""

from fastapi import APIRouter

from src.app.api.v2 import projects, folders

api_router = APIRouter(prefix="/api/v2")

api_router.include_router(projects.router, tags=["Projects"])
api_router.include_router(folders.router, tags=["Folders"])

__all__ = ["api_router"]
