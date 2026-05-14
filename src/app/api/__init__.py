"""API router registration.

Aggregates all v2 API routers under /api/v2 prefix.
"""

from fastapi import APIRouter

from src.app.api.v2 import projects, folders, test_cases, test_runs, attachments

api_router = APIRouter(prefix="/api/v2")
api_router.include_router(projects.router, tags=["Projects"])
api_router.include_router(folders.router, tags=["Folders"])
api_router.include_router(test_cases.router, tags=["Test Cases"])
api_router.include_router(test_runs.router, tags=["Test Runs"])
api_router.include_router(attachments.router, tags=["Attachments"])
