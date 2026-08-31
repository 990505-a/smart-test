"""Self-evolution routes (自进化模块)."""

from fastapi import APIRouter, BackgroundTasks, HTTPException
from uuid import UUID
from sqlalchemy import select

from src.app.api.deps import DbSessionDep
from src.app.api.v2.auth import CurrentUserDep
from src.app.db.models.evolution import EvolutionRun
from src.app.db.schemas.common import SuccessResponse
from src.app.services import evolution_service
from src.app.services.scheduler import reschedule_evolution, scheduler_info
from src.app.services.settings_service import SettingsService

router = APIRouter(prefix="/evolution")


def _run_dict(run: EvolutionRun) -> dict:
    return {
        "id": str(run.id),
        "trigger": run.trigger,
        "status": run.status,
        "annotations_total": run.annotations_total,
        "good_count": run.good_count,
        "bad_count": run.bad_count,
        "modules_touched": run.modules_touched,
        "lessons": run.lessons,
        "skill_patches": run.skill_patches,
        "regression_summary": run.regression_summary,
        "error": run.error,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at,
    }


@router.get("/runs", response_model=SuccessResponse, summary="进化运行历史")
async def list_runs(user: CurrentUserDep, db: DbSessionDep, limit: int = 20):
    runs = list((await db.execute(
        select(EvolutionRun).order_by(EvolutionRun.created_at.desc()).limit(limit)
    )).scalars().all())
    return SuccessResponse(success=True, data=[_run_dict(r) for r in runs])


@router.get("/runs/{run_id}", response_model=SuccessResponse, summary="进化运行详情")
async def get_run(run_id: str, user: CurrentUserDep, db: DbSessionDep):
    run = (await db.execute(
        select(EvolutionRun).where(EvolutionRun.id == UUID(run_id)))).scalars().first()
    if run is None:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return SuccessResponse(success=True, data=_run_dict(run))


@router.post("/trigger", response_model=SuccessResponse, summary="手动触发一次进化")
async def trigger(user: CurrentUserDep, background: BackgroundTasks):
    background.add_task(evolution_service.run_evolution, "manual")
    return SuccessResponse(success=True, data={"started": True,
                                               "note": "进化已在后台运行，稍后刷新运行历史查看结果"})


@router.post("/trigger-sync", response_model=SuccessResponse, summary="同步触发进化(等待结果)")
async def trigger_sync(user: CurrentUserDep):
    result = await evolution_service.run_evolution(trigger="manual")
    return SuccessResponse(success=True, data=result)


@router.get("/schedule", response_model=SuccessResponse, summary="调度状态")
async def get_schedule(user: CurrentUserDep):
    return SuccessResponse(success=True, data=scheduler_info())


@router.put("/schedule", response_model=SuccessResponse, summary="调整每日进化时间")
async def put_schedule(user: CurrentUserDep, db: DbSessionDep, hour: int = 2, minute: int = 0):
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise HTTPException(status_code=400, detail="hour/minute 超出范围")
    svc = SettingsService(db)
    await svc.set_many("platform", {
        "evolution_cron_hour": str(hour),
        "evolution_cron_minute": str(minute),
    })
    await db.commit()
    reschedule_evolution(hour, minute)
    return SuccessResponse(success=True, data=scheduler_info())
