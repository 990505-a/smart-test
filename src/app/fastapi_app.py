"""FastAPI application factory.

Creates and configures the FastAPI application with:
- CORS middleware for development
- /api/v2 router prefix
- Health check and root endpoints
- Lifespan for database initialization

Adapted from classroom main.py:
- Removed MongoDB, User, RateLimiterMiddleware references
- Removed ensure_default_user function (per D-04)
- Import models directly from their modules for correct initialization order
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.app.api import api_router
from src.app.core.config import settings
from src.app.db.database import Base, engine, init_db

# Import all models DIRECTLY from their modules (not through __init__.py)
# This ensures correct initialization order for SQLAlchemy foreign key resolution.
# Models referenced by foreign keys must be imported FIRST.

from src.app.db.models.base import UUIDMixin, TimestampMixin  # noqa: F401
from src.app.db.models.project import Project  # noqa: F401
from src.app.db.models.folder import Folder  # noqa: F401
from src.app.db.models.test_case import TestCase, TestStep, Tag, TestCaseTag  # noqa: F401
from src.app.db.models.test_run import TestRun, TestRunTestCase  # noqa: F401
from src.app.db.models.test_result import TestResult, TestStepResult  # noqa: F401
from src.app.db.models.attachment import Attachment  # noqa: F401
from src.app.db.models.api_endpoint import APIEndpoint  # noqa: F401
from src.app.db.models.test_scenario import (  # noqa: F401
    TestScenario,
    ScenarioStep,
    StepDataMapping,
    ScenarioVariable,
    ScenarioRun,
    ScenarioStepResult,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager.

    On startup: create database tables in debug mode.
    On shutdown: dispose of the database engine.
    """
    # Startup: create tables in dev mode
    await init_db()

    yield

    # Shutdown: close database connection pool
    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="Smart Test Platform API",
        description="Smart Test Platform REST API for test case management.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS middleware -- allow all origins for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API v2 routes
    app.include_router(api_router)

    # Health check endpoint
    @app.get("/health", tags=["System"])
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "version": "1.0.0",
        }

    # Root endpoint
    @app.get("/", tags=["System"])
    async def root():
        """API root endpoint."""
        return {
            "message": "Smart Test Platform API",
            "docs": "/docs",
        }

    return app


# Module-level app instance for uvicorn
app = create_app()
