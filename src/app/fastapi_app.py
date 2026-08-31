"""FastAPI application factory.

Creates the FastAPI app with lifespan management, CORS middleware,
and API router registration. Per D-08: runs on port 8000 with /api/v2 prefix.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.app.api import api_router
from src.app.core.config import settings
from src.app.db.utils.exceptions import AppException

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialize DB on startup, dispose engine on shutdown."""
    from src.app.db.database import async_session_factory, engine, init_db
    from src.app.services.auth_service import AuthService
    from src.app.services.scheduler import start_scheduler, stop_scheduler
    from src.app.services.settings_service import SettingsService

    # Auto-create tables in development
    await init_db()

    # Ensure the default admin account exists (用户模块)
    async with async_session_factory() as db:
        await AuthService(db).ensure_default_admin()
        await db.commit()

    # Restore the persisted schedules before creating the in-process scheduler.
    async with async_session_factory() as db:
        schedule = await SettingsService(db).get_namespace(
            "platform", {"evolution_cron_hour": "", "evolution_cron_minute": "",
                         "codebase_schedule_enabled": "", "codebase_interval_hours": ""}
        )
    try:
        hour = int(schedule.get("evolution_cron_hour") or settings.evolution_cron_hour)
        minute = int(schedule.get("evolution_cron_minute") or settings.evolution_cron_minute)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            settings.evolution_cron_hour = hour
            settings.evolution_cron_minute = minute
    except (TypeError, ValueError):
        logger.warning("Invalid persisted evolution schedule; using configured defaults")
    try:
        settings.codebase_schedule_enabled = str(
            schedule.get("codebase_schedule_enabled") or settings.codebase_schedule_enabled
        ).lower() in ("1", "true", "yes")
        settings.codebase_interval_hours = int(
            str(schedule.get("codebase_interval_hours") or settings.codebase_interval_hours))
    except (TypeError, ValueError):
        logger.warning("Invalid persisted codebase schedule; using configured defaults")

    # Nightly self-evolution scheduler (自进化模块)
    start_scheduler()

    # 代码图谱：清理上次进程遗留的 running 索引记录（进程重启即任务已死）
    from src.app.services.codebase_service import mark_stale_runs_failed
    stale = await mark_stale_runs_failed()
    if stale:
        logger.info("Marked %d stale codebase index run(s) as failed", stale)

    yield

    stop_scheduler()
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

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": exc.error,
                "message": exc.message,
                "details": exc.details,
            },
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
