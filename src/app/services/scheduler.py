"""APScheduler-based scheduler (自进化 + 代码图谱定时任务).

Started inside the FastAPI lifespan. Jobs:
- nightly self-evolution at ``EVOLUTION_CRON_HOUR:EVOLUTION_CRON_MINUTE``
  (default 02:00, Beijing time), also manually triggerable via the API;
- codebase incremental indexing every ``CODEBASE_INTERVAL_HOURS`` (default 24h;
  only repos that already have a full index — see codebase_service).
"""

from __future__ import annotations

import logging

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.app.core.config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


async def _nightly_evolution() -> None:
    from src.app.services.evolution_service import run_evolution

    logger.info("Nightly self-evolution starting…")
    result = await run_evolution(trigger="scheduled")
    logger.info("Nightly self-evolution result: %s", result.get("status"))


async def _codebase_incremental() -> None:
    from src.app.services.codebase_service import run_incremental_round

    logger.info("Codebase incremental index round starting…")
    result = await run_incremental_round(trigger="scheduled")
    logger.info("Codebase incremental round: %s", result.get("summary"))


def _cron(hour: int, minute: int) -> CronTrigger:
    return CronTrigger(hour=hour, minute=minute, timezone="Asia/Shanghai")


def _ensure_evolution_job(hour: int, minute: int) -> None:
    scheduler.add_job(
        _nightly_evolution,
        _cron(hour, minute),
        id="nightly_evolution",
        name="每日自进化（沉淀用例自回归）",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )


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
    if settings.evolution_enabled:
        _ensure_evolution_job(settings.evolution_cron_hour, settings.evolution_cron_minute)
        logger.info("Scheduled nightly evolution at %02d:%02d Asia/Shanghai",
                    settings.evolution_cron_hour, settings.evolution_cron_minute)
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


def reschedule_evolution(hour: int, minute: int) -> None:
    """Apply a new evolution schedule, creating the job if needed."""
    try:
        scheduler.reschedule_job("nightly_evolution", trigger=_cron(hour, minute))
    except JobLookupError:
        _ensure_evolution_job(hour, minute)


def reschedule_codebase(enabled: bool, hours: int) -> None:
    """Apply a new codebase incremental-index interval, creating the job if needed."""
    _ensure_codebase_job(enabled, hours)
