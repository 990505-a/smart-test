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
            "platform", {"codebase_schedule_enabled": "", "codebase_interval_hours": "",
                         "codebase_analyze_enabled": ""}
        )
    try:
        settings.codebase_schedule_enabled = str(
            schedule.get("codebase_schedule_enabled") or settings.codebase_schedule_enabled
        ).lower() in ("1", "true", "yes")
        settings.codebase_interval_hours = int(
            str(schedule.get("codebase_interval_hours") or settings.codebase_interval_hours))
        settings.codebase_analyze_enabled = str(
            schedule.get("codebase_analyze_enabled") or settings.codebase_analyze_enabled
        ).lower() in ("1", "true", "yes")
    except (TypeError, ValueError):
        logger.warning("Invalid persisted codebase schedule; using configured defaults")

    start_scheduler()

    # 代码图谱：清理上次进程遗留的 running 记录（进程重启即任务已死）
    from src.app.services.codebase_service import mark_stale_runs_failed
    stale = await mark_stale_runs_failed()
    if stale:
        logger.info("Marked %d stale codebase index run(s) as failed", stale)
    from src.app.services.codebase_analysis_service import mark_stale_reports_failed
    stale_reports = await mark_stale_reports_failed()
    if stale_reports:
        logger.info("Marked %d stale impact report(s) as failed", stale_reports)

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
        # 平台刻意不做登录（见 api/v2/auth.py：无 token 时返回内置本地用户），
        # 认证只走请求头（X-Auth-Token / Authorization: Bearer），**没有 cookie**。
        #
        # 所以 allow_credentials 必须是 False。它的语义是"允许跨域请求携带凭据"，
        # 而 Starlette 在 allow_origins=["*"] + allow_credentials=True 时会**回显
        # 请求的 Origin**（而不是发 "*"）——等于告诉浏览器任何网页都能对本服务发
        # 带凭据的跨域请求。现在没有 cookie 所以实际打不穿，但这是个埋着的雷：
        # 哪天有人把登录改回 cookie 会话，它就直接变成 CSRF 通道。
        #
        # allow_origins 保留 "*"：本机模式下前端(5013)与 API(5012)是跨端口的，
        # 反代模式(Caddy)下是同源——收紧成白名单会按部署方式各断一半，而这里
        # 本来就没有凭据可保护。前端 fetch 也没有用 credentials: "include"
        # （保持默认的 same-origin），所以关掉它不影响任何现有调用。
        allow_origins=["*"],
        allow_credentials=False,
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
