"""FastAPI application factory.

Creates the FastAPI app with lifespan management, CORS middleware,
and API router registration. Per D-08: runs on port 8000 with /api/v2 prefix.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.app.api import api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialize DB on startup, dispose engine on shutdown."""
    from src.app.db.database import engine, init_db
    from src.app.core.config import settings

    # Auto-create tables in development
    await init_db()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Smart Test Platform API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": "1.0.0"}

    @app.get("/")
    async def root():
        return {"message": "Smart Test Platform API", "docs": "/docs"}

    return app


app = create_app()
