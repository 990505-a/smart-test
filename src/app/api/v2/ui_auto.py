"""Unity UI automation routes (UI 自动化模块)."""

import json

from fastapi import APIRouter, BackgroundTasks, HTTPException
from uuid import UUID
from pydantic import BaseModel
from sqlalchemy import select

from src.app.api.deps import DbSessionDep
from src.app.api.v2.auth import CurrentUserDep
from src.app.db.models.ui_script import UiScript, UiScriptRun
from src.app.db.schemas.common import SuccessResponse
from src.app.services import unity_service

router = APIRouter(prefix="/ui-auto")


class ScriptCreate(BaseModel):
    name: str
    module: str | None = None
    description: str | None = None
    content: str
    project_id: str | None = None


class ScriptUpdate(BaseModel):
    name: str | None = None
    module: str | None = None
    description: str | None = None
    content: str | None = None
    status: str | None = None


class ExecLuaRequest(BaseModel):
    code: str
    sync: bool = False


def _script_dict(s: UiScript, *, full: bool = False) -> dict:
    data = {
        "id": str(s.id), "name": s.name, "module": s.module,
        "description": s.description, "version": s.version, "status": s.status,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
    if full:
        data["content"] = s.content
        data["repair_history"] = json.loads(s.repair_history) if s.repair_history else []
    return data


def _run_dict(r: UiScriptRun) -> dict:
    return {
        "id": str(r.id), "script_id": str(r.script_id), "status": r.status,
        "exit_code": r.exit_code, "output": r.output, "screenshots": r.screenshots,
        "duration_ms": r.duration_ms, "triggered_by": r.triggered_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# --- Unity connection ---------------------------------------------------------

@router.get("/status", response_model=SuccessResponse, summary="Unity 连接状态")
async def unity_status(user: CurrentUserDep):
    return SuccessResponse(success=True, data=await unity_service.status())


@router.post("/screenshot", response_model=SuccessResponse, summary="游戏截图")
async def unity_screenshot(user: CurrentUserDep, save_path: str | None = None):
    result = await unity_service.screenshot(save_path)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "截图失败"))
    return SuccessResponse(success=True, data=result)


@router.post("/exec-lua", response_model=SuccessResponse, summary="执行 Lua 代码")
async def exec_lua(data: ExecLuaRequest, user: CurrentUserDep):
    return SuccessResponse(success=True, data=await unity_service.exec_lua(data.code, sync=data.sync))


@router.get("/windows", response_model=SuccessResponse, summary="当前 UI 窗口列表")
async def windows(user: CurrentUserDep):
    return SuccessResponse(success=True, data=await unity_service.shown_windows())


# --- Script CRUD + execution --------------------------------------------------

@router.post("/scripts", response_model=SuccessResponse, status_code=201, summary="创建 UI 脚本")
async def create_script(data: ScriptCreate, user: CurrentUserDep, db: DbSessionDep):
    script = UiScript(**data.model_dump())
    db.add(script)
    await db.commit()
    return SuccessResponse(success=True, data=_script_dict(script, full=True))


@router.get("/scripts", response_model=SuccessResponse, summary="UI 脚本列表")
async def list_scripts(user: CurrentUserDep, db: DbSessionDep):
    rows = list((await db.execute(
        select(UiScript).order_by(UiScript.updated_at.desc()).limit(100)
    )).scalars().all())
    return SuccessResponse(success=True, data=[_script_dict(s) for s in rows])


@router.get("/scripts/{script_id}", response_model=SuccessResponse, summary="UI 脚本详情")
async def get_script(script_id: str, user: CurrentUserDep, db: DbSessionDep):
    row = (await db.execute(
        select(UiScript).where(UiScript.id == UUID(script_id)))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="脚本不存在")
    return SuccessResponse(success=True, data=_script_dict(row, full=True))


@router.put("/scripts/{script_id}", response_model=SuccessResponse, summary="更新 UI 脚本")
async def update_script(script_id: str, data: ScriptUpdate, user: CurrentUserDep, db: DbSessionDep):
    row = (await db.execute(
        select(UiScript).where(UiScript.id == UUID(script_id)))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="脚本不存在")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    if data.content is not None:
        row.version += 1
    await db.commit()
    return SuccessResponse(success=True, data=_script_dict(row))


async def _run_and_record(script_id: str) -> None:
    from src.app.db.database import async_session_factory

    async with async_session_factory() as db:
        script = (await db.execute(
            select(UiScript).where(UiScript.id == UUID(script_id)))).scalars().first()
        if script is None:
            return
        run = UiScriptRun(script_id=script.id)
        db.add(run)
        await db.flush()
        try:
            result = await unity_service.run_ui_script(str(script.id), script.name, script.content)
            run.status = result["status"]
            run.exit_code = result["exit_code"]
            run.output = result["output"]
            run.duration_ms = result["duration_ms"]
            script.status = "active" if result["status"] == "passed" else "broken"
        except Exception as exc:  # noqa: BLE001
            run.status = "error"
            run.exit_code = -2
            run.output = str(exc)
            script.status = "broken"
        finally:
            await db.commit()


@router.post("/scripts/{script_id}/run", response_model=SuccessResponse, summary="执行 UI 脚本(后台)")
async def run_script(script_id: str, user: CurrentUserDep, db: DbSessionDep,
                     background: BackgroundTasks):
    row = (await db.execute(
        select(UiScript).where(UiScript.id == UUID(script_id)))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="脚本不存在")
    background.add_task(_run_and_record, script_id)
    return SuccessResponse(success=True, data={"started": True})


@router.get("/scripts/{script_id}/runs", response_model=SuccessResponse, summary="UI 脚本执行历史")
async def list_runs(script_id: str, user: CurrentUserDep, db: DbSessionDep):
    rows = list((await db.execute(
        select(UiScriptRun).where(UiScriptRun.script_id == UUID(script_id))
        .order_by(UiScriptRun.created_at.desc()).limit(30)
    )).scalars().all())
    return SuccessResponse(success=True, data=[_run_dict(r) for r in rows])
