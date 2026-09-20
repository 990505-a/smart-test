"""Unity 自动化路由（Unity 自动化模块）。

薄层：转发给 ``services/unity_service.py``（操作走标准 MCP 桥，见
``services/unity_bridge.py``）。用例脚本的落库/执行也从这里进出。

**存证**与 Web-UI 模块口径一致：执行记录带产物清单（截图/录像/步骤轨迹/失败现场），
浏览器按**签名 URL** 回取 —— `<img>`、`<video>` 都是浏览器自己发的请求，带不上
前端设置的 ``X-Auth-Token``（见 ``core/share_link.py``）。
"""

import json
import mimetypes
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from src.app.api.deps import DbSessionDep
from src.app.api.v2.auth import CurrentUserDep
from src.app.core import share_link
from src.app.db.models.unity_script import UnityScript, UnityScriptRun
from src.app.db.schemas.common import SuccessResponse
from src.app.services import unity_service

router = APIRouter(prefix="/unity-auto")

#: 产物类型 -> 前端渲染方式（图片看大图、录像播放器、文本预览）。
_ARTIFACT_KINDS = {
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".gif": "image",
    ".mp4": "video", ".webm": "video", ".mov": "video",
    ".html": "html", ".zip": "trace",
    ".txt": "text", ".md": "text", ".log": "text", ".json": "text", ".jsonl": "text",
}

#: MIME 写死：slim 镜像的 mimetypes 库不保证认识 .webm/.jsonl，猜错会让浏览器
#: 静默不播（<video> 拿到 octet-stream 就是一块黑框）。
_MEDIA_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".html": "text/html; charset=utf-8", ".txt": "text/plain; charset=utf-8",
    ".log": "text/plain; charset=utf-8", ".md": "text/markdown; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".jsonl": "application/x-ndjson; charset=utf-8", ".zip": "application/zip",
}

#: 卡在 running 超过这个时长（进程被杀/容器重启）就不该继续显示"运行中"。
#: 与"删除时判不判正在执行"共用同一个口径（unity_service.RUN_STALE_AFTER_S），
#: 比 runner 自己的执行上限（unity_service._RUN_TIMEOUT_S）再宽一点。
_STALE_AFTER_S = unity_service.RUN_STALE_AFTER_S


def _media_type(path: Path) -> str:
    return (_MEDIA_TYPES.get(path.suffix.lower())
            or mimetypes.guess_type(path.name)[0] or "application/octet-stream")


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


class ExecCSharpRequest(BaseModel):
    code: str


def _script_dict(s: UnityScript, *, full: bool = False) -> dict:
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


def _artifact_paths(run: UnityScriptRun) -> list[Path]:
    """这次执行的产物路径。

    两条来源：
    - 跑完的记录：``screenshots`` 里那份 JSON 数组（权威清单，含"被清理"的事实）；
    - **还在跑的记录**：直接读 ``workdir`` 里现存的文件 —— 文件是边跑边落盘的，
      执行期间不给前端看一眼，那句"轨迹实时刷新"就是假的（实测：跑着的记录一直
      显示 0 步 0 图，人以为卡死了）。
    """
    if run.screenshots:
        try:
            items = json.loads(run.screenshots)
        except json.JSONDecodeError:
            items = []
        if isinstance(items, list) and items:
            return [Path(str(p)) for p in items]
    if run.workdir:
        return unity_service.live_artifacts(Path(run.workdir))
    return []


def _artifacts(run: UnityScriptRun) -> list[dict]:
    """产物清单：名字/大小/类型/回取 URL。

    ``url`` 指向按序号取产物的接口 —— 序号到路径的映射只有平台知道，既省得把
    （可能很长的）绝对路径塞进 URL，也顺带没有目录穿越这回事。
    """
    sig = share_link.sign(str(run.id))
    out: list[dict] = []
    for index, path in enumerate(_artifact_paths(run)):
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        out.append({
            "index": index, "name": path.name, "path": str(path), "size": size,
            "kind": _ARTIFACT_KINDS.get(path.suffix.lower(), "file"),
            # 文件被人工清理/磁盘回收后给前端一个明确信号，而不是画一排破图
            "pruned": size is None,
            "url": f"/unity-auto/artifact/{run.id}/{index}?sig={sig}",
        })
    return out


def _steps_of(run: UnityScriptRun) -> list[dict]:
    """步骤轨迹（用例执行期间每个动作一行 JSONL）。"""
    for path in _artifact_paths(run):
        if path.name != "steps.jsonl":
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        steps: list[dict] = []
        for line in lines[-500:]:
            try:
                steps.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return steps
    return []


def _run_dict(r: UnityScriptRun) -> dict:
    artifacts = _artifacts(r)
    age_s = unity_service.run_age_s(r)
    stale = r.status == "running" and age_s > _STALE_AFTER_S
    return {
        "id": str(r.id), "script_id": str(r.script_id), "status": r.status,
        "exit_code": r.exit_code, "output": r.output,
        # screenshots 保持原样（老前端/老记录仍在读它），新前端用 artifacts
        "screenshots": r.screenshots,
        "artifacts": artifacts,
        "steps": _steps_of(r),
        "share_sig": share_link.sign(str(r.id)),
        "artifacts_pruned": bool(artifacts) and all(a["pruned"] for a in artifacts),
        "stale_running": stale,
        # 在跑的记录没有 duration_ms（那是跑完才写的）——给一个"已经跑了多久"，
        # 让详情页显示"进行中 42s"，而不是一个看不出死活的 "-"。
        "elapsed_ms": int(age_s * 1000) if r.status == "running" and not stale else None,
        "duration_ms": r.duration_ms, "triggered_by": r.triggered_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


async def _require_run(db: DbSessionDep, run_id: str) -> UnityScriptRun:
    try:
        uid = UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    row = (await db.execute(
        select(UnityScriptRun).where(UnityScriptRun.id == uid))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return row


# --- Unity 桥 ----------------------------------------------------------------

@router.get("/status", response_model=SuccessResponse, summary="Unity 桥状态")
async def unity_status(user: CurrentUserDep):
    return SuccessResponse(success=True, data=await unity_service.status())


@router.get("/tools", response_model=SuccessResponse, summary="MCP 服务器提供的工具清单")
async def unity_tools(user: CurrentUserDep, refresh: bool = False):
    return SuccessResponse(success=True, data=await unity_service.mcp_tools(refresh))


@router.post("/screenshot", response_model=SuccessResponse, summary="游戏截图")
async def unity_screenshot(user: CurrentUserDep, save_path: str | None = None):
    result = await unity_service.screenshot(save_path)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "截图失败"))
    return SuccessResponse(success=True, data=result)


@router.post("/exec-csharp", response_model=SuccessResponse, summary="执行 C# 语句")
async def exec_csharp(data: ExecCSharpRequest, user: CurrentUserDep):
    return SuccessResponse(success=True, data=await unity_service.exec_csharp(data.code))


# --- 用例 CRUD + 执行 ---------------------------------------------------------

@router.post("/scripts", response_model=SuccessResponse, status_code=201, summary="创建 Unity 用例")
async def create_script(data: ScriptCreate, user: CurrentUserDep, db: DbSessionDep):
    row = await unity_service.save_script(
        db, name=data.name, module=data.module, description=data.description,
        content=data.content)
    return SuccessResponse(success=True, data=_script_dict(row, full=True))


@router.get("/scripts", response_model=SuccessResponse, summary="Unity 用例列表")
async def list_scripts(user: CurrentUserDep, db: DbSessionDep):
    rows = await unity_service.list_scripts(db, limit=100)
    return SuccessResponse(success=True, data=[_script_dict(s) for s in rows])


@router.get("/scripts/{script_id}", response_model=SuccessResponse, summary="Unity 用例详情")
async def get_script(script_id: str, user: CurrentUserDep, db: DbSessionDep):
    row = await unity_service.get_script(db, script_id)
    if row is None:
        raise HTTPException(status_code=404, detail="脚本不存在")
    return SuccessResponse(success=True, data=_script_dict(row, full=True))


@router.put("/scripts/{script_id}", response_model=SuccessResponse, summary="更新 Unity 用例")
async def update_script(script_id: str, data: ScriptUpdate, user: CurrentUserDep,
                        db: DbSessionDep):
    try:
        row = await unity_service.save_script(
            db, script_id=script_id, name=data.name, module=data.module,
            description=data.description, content=data.content, status=data.status)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SuccessResponse(success=True, data=_script_dict(row))


@router.delete("/scripts/{script_id}", response_model=SuccessResponse, summary="删除 Unity 用例")
async def delete_script(script_id: str, user: CurrentUserDep, db: DbSessionDep):
    """删掉一条用例：执行记录 + 磁盘产物（截图/录像/轨迹/起跑线）一起清。

    正在执行中不让删（409）：后台任务还在往回写、产物还在生成。
    """
    try:
        out = await unity_service.delete_script(db, script_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SuccessResponse(success=True, data=out)


async def _execute_run(script_id: str, run_id: str, name: str, content: str) -> None:
    """后台跑一次用例，把结果写回执行记录。

    执行记录**在入队前就建好了**（见 run_script），所以这里只负责更新：前端拿到
    run_id 就能立刻打开详情看步骤轨迹一条条冒出来，而不是"等 3 秒再刷新列表"。
    """
    from src.app.db.database import async_session_factory

    async with async_session_factory() as db:
        run = (await db.execute(
            select(UnityScriptRun).where(UnityScriptRun.id == UUID(run_id)))).scalars().first()
        script = (await db.execute(
            select(UnityScript).where(UnityScript.id == UUID(script_id)))).scalars().first()
        if run is None:
            return
        workdir = Path(run.workdir) if run.workdir else None
        try:
            result = await unity_service.run_unity_script(script_id, name, content,
                                                          workdir=workdir)
            run.status = result["status"]
            run.exit_code = result["exit_code"]
            run.output = result["output"]
            run.duration_ms = result["duration_ms"]
            run.screenshots = result.get("screenshots")
            if script is not None:
                script.status = "active" if result["status"] == "passed" else "broken"
        except Exception as exc:  # noqa: BLE001
            run.status = "error"
            run.exit_code = -2
            run.output = str(exc)
            if script is not None:
                script.status = "broken"
        finally:
            await db.commit()


@router.post("/scripts/{script_id}/run", response_model=SuccessResponse,
             summary="执行 Unity 用例(后台)")
async def run_script(script_id: str, user: CurrentUserDep, db: DbSessionDep,
                     background: BackgroundTasks):
    row = await unity_service.get_script(db, script_id)
    if row is None:
        raise HTTPException(status_code=404, detail="脚本不存在")
    # 运行目录**入队前就定好并落库**：前端打开详情看"轨迹实时刷新"靠它 ——
    # 产物清单要跑完才写回 screenshots，光看那一列，运行中永远是 0 步 0 图。
    workdir = unity_service._run_dir(str(row.id), row.name)
    run = UnityScriptRun(script_id=row.id, status="running", workdir=str(workdir))
    db.add(run)
    await db.commit()
    await db.refresh(run)
    background.add_task(_execute_run, str(row.id), str(run.id), row.name, row.content)
    return SuccessResponse(success=True, data={"started": True, "run_id": str(run.id)})


@router.get("/scripts/{script_id}/runs", response_model=SuccessResponse,
            summary="Unity 用例执行历史")
async def list_runs(script_id: str, user: CurrentUserDep, db: DbSessionDep):
    rows = await unity_service.list_runs(db, script_id, limit=30)
    return SuccessResponse(success=True, data=[_run_dict(r) for r in rows])


@router.get("/runs/{run_id}", response_model=SuccessResponse, summary="Unity 用例执行详情")
async def get_run(run_id: str, user: CurrentUserDep, db: DbSessionDep):
    """单条执行记录（含产物清单与步骤轨迹）。

    执行是后台跑的，前端轮询这一条：跑完那一刻状态、产物、轨迹一起变。
    """
    row = await _require_run(db, run_id)
    return SuccessResponse(success=True, data=_run_dict(row))


# --- 产物回取（签名 URL，供浏览器直接取用）------------------------------------

@router.get("/artifact/{run_id}/{index}", include_in_schema=False)
async def get_artifact(run_id: str, index: int, db: DbSessionDep, sig: str = Query("")):
    """回取一次执行的单个产物（截图 / 录像 / 步骤轨迹 / 失败现场文本）。

    鉴权靠 URL 签名而不是 token：``<img>``、``<video>``、新标签页打开都是浏览器
    自己发的请求，带不上前端的自定义头。签名覆盖 run_id，所以一次执行的签名换
    不到另一次执行的产物。**按序号取文件**：清单本就存在执行记录里，序号→路径
    只有平台知道，顺带没有目录穿越。
    """
    run = await _require_run(db, run_id)
    if not share_link.verify(sig, run_id):
        raise HTTPException(status_code=403, detail="链接无效或已过期")
    paths = _artifact_paths(run)
    if index < 0 or index >= len(paths):
        raise HTTPException(status_code=404, detail="产物不存在")
    target = paths[index]
    if not target.is_file():
        raise HTTPException(
            status_code=410,
            detail="该次执行的产物文件已被清理，无法回看；重新执行即可重新生成存证")
    return FileResponse(target, media_type=_media_type(target))
