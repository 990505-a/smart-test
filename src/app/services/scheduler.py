"""APScheduler-based scheduler (代码图谱定时任务).

Started inside the FastAPI lifespan. Jobs:
- codebase incremental indexing every ``CODEBASE_INTERVAL_HOURS`` (default 24h;
  only repos that already have a full index — see codebase_service).

自进化模块已移除（2026-08-31 记忆系统 EverOS 化）：经验沉淀由 EverOS 的
OME 离线进化策略接管（workspace/default/memory/ome.toml，热加载）。
"""

from __future__ import annotations

import logging

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.app.core.config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


async def _codebase_incremental() -> None:
    from src.app.services.codebase_service import run_incremental_round

    logger.info("Codebase incremental index round starting…")
    result = await run_incremental_round(trigger="scheduled")
    logger.info("Codebase incremental round: %s", result.get("summary"))


def _ensure_codebase_job(enabled: bool, hours: int) -> None:
    if not enabled:
        try:
            scheduler.remove_job("codebase_incremental_index")
        except JobLookupError:
            pass
        return
    scheduler.add_job(
        _codebase_incremental,
        IntervalTrigger(hours=hours),
        id="codebase_incremental_index",
        name="代码图谱定时增量索引",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )


def start_scheduler() -> None:
    """Register jobs and start the scheduler (idempotent)."""
    if scheduler.running:
        return
    _ensure_codebase_job(settings.codebase_schedule_enabled, settings.codebase_interval_hours)
    if settings.codebase_schedule_enabled:
        logger.info("Scheduled codebase incremental index every %dh", settings.codebase_interval_hours)
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def scheduler_info() -> dict:
    jobs = [
        {
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        }
        for job in scheduler.get_jobs()
    ]
    return {"running": scheduler.running, "jobs": jobs}


def reschedule_codebase(enabled: bool, hours: int) -> None:
    """Apply a new codebase incremental-index interval, creating the job if needed."""
    _ensure_codebase_job(enabled, hours)
