"""API router registration.

Aggregates all v2 API routers under /api/v2 prefix.
"""

from fastapi import APIRouter

from src.app.api.v2 import (
    api_tests,
    attachments,
    configurations,
    extract_pdf,
    folders,
    messages,
    projects,
    scenarios,
    test_cases,
    test_runs,
    web_functions,
    web_tests,
    wikis,
    workspaces,
)

api_router = APIRouter(prefix="/api/v2")
api_router.include_router(projects.router, tags=["Projects"])
api_router.include_router(folders.router, tags=["Folders"])
api_router.include_router(test_cases.router, tags=["Test Cases"])
api_router.include_router(test_runs.router, tags=["Test Runs"])
api_router.include_router(attachments.router, tags=["Attachments"])
api_router.include_router(api_tests.router, tags=["API Tests"])
api_router.include_router(scenarios.router, tags=["Scenarios"])
api_router.include_router(workspaces.router, tags=["Workspaces"])
api_router.include_router(web_functions.router, tags=["Web Functions"])
api_router.include_router(web_tests.router, tags=["Web Tests"])
api_router.include_router(configurations.router, tags=["Configurations"])
api_router.include_router(wikis.router, tags=["Wikis"])
api_router.include_router(messages.router, tags=["Messages"])
api_router.include_router(extract_pdf.router, tags=["PDF Extraction"])
