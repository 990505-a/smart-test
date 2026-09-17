"""Web-UI automation routes (Web-UI 自动化模块).

Browser UI automation driven by the Playwright CLI. Mirrors the unity-auto
surface (status / scripts CRUD / run / run history) plus two endpoints that
only make sense on the browser side: an on-demand AI spec generator and a
one-shot screenshot.
"""

import json
import logging
import re
import mimetypes
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse
from uuid import UUID, uuid4
from pydantic import BaseModel
from sqlalchemy import and_, func, select

from src.app.api.deps import DbSessionDep
from src.app.api.v2.auth import CurrentUserDep
from src.app.core import share_link
from src.app.core.config import settings
from src.app.db.models.web_ui_script import WebUiScript, WebUiScriptRun
from src.app.db.schemas.common import SuccessResponse
from src.app.services import playwright_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/web-ui-auto")


class ScriptCreate(BaseModel):
    name: str
    module: str | None = None
    description: str | None = None
    content: str
    spec_file: str = "tests/spec.spec.ts"
    target_url: str | None = None
    options: dict | None = None
    project_id: str | None = None


class ScriptUpdate(BaseModel):
    name: str | None = None
    module: str | None = None
    description: str | None = None
    content: str | None = None
    spec_file: str | None = None
    target_url: str | None = None
    options: dict | None = None
    status: str | None = None


class RunRequest(BaseModel):
    auto_repair: bool | None = None


class GenerateRequest(BaseModel):
    intent: str
    name: str
    target_url: str | None = None
    module: str | None = None
    extra_requirements: str = ""
    save: bool = True


class ScreenshotRequest(BaseModel):
    url: str
    filename: str | None = None
    device: str | None = None
    full_page: bool = True


def _script_dict(s: WebUiScript, *, full: bool = False) -> dict:
    data = {
        "id": str(s.id), "name": s.name, "module": s.module,
        "description": s.description, "spec_file": s.spec_file,
        "target_url": s.target_url,
        "options": json.loads(s.options) if s.options else None,
        "version": s.version, "status": s.status,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
    if full:
        data["content"] = s.content
        data["repair_history"] = json.loads(s.repair_history) if s.repair_history else []
    return data


def _run_dict(r: WebUiScriptRun) -> dict:
    return {
        "id": str(r.id), "script_id": str(r.script_id), "status": r.status,
        "exit_code": r.exit_code, "output": r.output,
        "report": json.loads(r.report) if r.report else None,
        "artifacts": json.loads(r.artifacts) if r.artifacts else None,
        "duration_ms": r.duration_ms, "triggered_by": r.triggered_by,
        "repair_attempt": r.repair_attempt, "runner_run_id": r.runner_run_id,
        # 签名 URL：浏览器要看截图/trace/报告时带不上自定义头，所以把只读授权
        # 放进 URL（见 core/share_link.py）。
        "share_sig": share_link.sign(str(r.id)),
        "report_ready": _report_path(r) is not None,
        # 产物清单留在库里，文件却可能已经不在了（人工清理、磁盘回收）。不告诉
        # 前端的话，页面会画出一堆永远加载不出来的破图，看起来像"平台坏了"。
        "artifacts_pruned": bool(r.artifacts) and _run_dir_gone(r),
        # 卡在 running 太久的记录（容器重启、进程被杀）不能一直显示"运行中"
        "stale_running": r.status == "running" and _age_seconds(r) > settings.web_ui_run_timeout_s + 120,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _age_seconds(run: WebUiScriptRun) -> float:
    if run.created_at is None:
        return 0.0
    created = run.created_at
    if created.tzinfo is not None:
        created = created.astimezone(timezone.utc).replace(tzinfo=None)
    return (datetime.now(timezone.utc).replace(tzinfo=None) - created).total_seconds()


def _runs_root() -> Path:
    """runner 的工作目录（容器里是 compose 挂进后端的 workspace）。"""
    return playwright_service.workspace() / "runs"


def _run_dir_gone(run: WebUiScriptRun) -> bool:
    """整个运行目录不见了 = 产物已被清理。一次 stat 就够，不必逐个文件去 stat。"""
    if not run.runner_run_id:
        return True
    try:
        return not (_runs_root() / run.runner_run_id).is_dir()
    except OSError:
        return True


def _report_path(run: WebUiScriptRun) -> Path | None:
    """HTML 报告入口（存在才返回，供前端决定要不要显示按钮）。"""
    target = _artifact_path(run, "html-report/index.html")
    return target


def _artifact_path(run: WebUiScriptRun, relative_path: str) -> Path | None:
    """把 (执行记录, 运行目录内相对路径) 解析成磁盘路径，越界一律拒绝。"""
    if not run.runner_run_id:
        return None
    root = _runs_root() / run.runner_run_id
    try:
        resolved_root = root.resolve()
        target = (resolved_root / relative_path).resolve()
        target.relative_to(resolved_root)
    except (OSError, ValueError):
        return None
    return target if target.is_file() else None


def _dump(value) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


# --- Runner connectivity ------------------------------------------------------

@router.get("/status", response_model=SuccessResponse, summary="Playwright 运行器状态")
async def runner_status(user: CurrentUserDep):
    return SuccessResponse(success=True, data=await playwright_service.status())


@router.post("/screenshot", response_model=SuccessResponse, summary="网页截图（playwright screenshot）")
async def screenshot(data: ScreenshotRequest, user: CurrentUserDep):
    result = await playwright_service.screenshot(
        data.url, filename=data.filename, device=data.device, full_page=data.full_page)
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("stderr") or result.get("error") or "截图失败")
    return SuccessResponse(success=True, data=result)


# --- AI spec generation -------------------------------------------------------

@router.post("/generate", response_model=SuccessResponse, status_code=201,
             summary="AI 生成 Playwright spec")
async def generate(data: GenerateRequest, user: CurrentUserDep, db: DbSessionDep):
    """自然语言测试意图 → 可执行 Playwright spec（默认同时入库）。"""
    result = await playwright_service.generate_spec(
        intent=data.intent, target_url=data.target_url,
        extra_requirements=data.extra_requirements)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "生成失败"))

    payload = {"content": result["content"], "target_url": result["target_url"]}
    if data.save:
        script = WebUiScript(
            name=data.name, module=data.module, description=data.intent,
            content=result["content"], target_url=result["target_url"],
            options=json.dumps({"device": "iPhone 13"} if "douban" in result["target_url"] else {}),
            status="draft",
        )
        db.add(script)
        await db.commit()
        payload["script"] = _script_dict(script, full=True)
    return SuccessResponse(success=True, data=payload)


# --- Script CRUD + execution --------------------------------------------------

@router.post("/scripts", response_model=SuccessResponse, status_code=201, summary="创建 Web-UI 脚本")
async def create_script(data: ScriptCreate, user: CurrentUserDep, db: DbSessionDep):
    script = WebUiScript(
        name=data.name, module=data.module, description=data.description,
        content=data.content, spec_file=data.spec_file, target_url=data.target_url,
        options=_dump(data.options), project_id=data.project_id,
    )
    db.add(script)
    await db.commit()
    return SuccessResponse(success=True, data=_script_dict(script, full=True))


@router.get("/scripts", response_model=SuccessResponse, summary="Web-UI 脚本列表")
async def list_scripts(user: CurrentUserDep, db: DbSessionDep):
    rows = list((await db.execute(
        select(WebUiScript).order_by(WebUiScript.updated_at.desc()).limit(100)
    )).scalars().all())
    return SuccessResponse(success=True, data=[_script_dict(s) for s in rows])


@router.get("/scripts/{script_id}", response_model=SuccessResponse, summary="Web-UI 脚本详情")
async def get_script(script_id: str, user: CurrentUserDep, db: DbSessionDep):
    row = (await db.execute(
        select(WebUiScript).where(WebUiScript.id == UUID(script_id)))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="脚本不存在")
    return SuccessResponse(success=True, data=_script_dict(row, full=True))


@router.put("/scripts/{script_id}", response_model=SuccessResponse, summary="更新 Web-UI 脚本")
async def update_script(script_id: str, data: ScriptUpdate, user: CurrentUserDep, db: DbSessionDep):
    row = (await db.execute(
        select(WebUiScript).where(WebUiScript.id == UUID(script_id)))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="脚本不存在")
    changed = data.model_dump(exclude_none=True)
    if "options" in changed:
        changed["options"] = _dump(changed["options"])
    for field, value in changed.items():
        setattr(row, field, value)
    if data.content is not None:
        row.version += 1
    await db.commit()
    return SuccessResponse(success=True, data=_script_dict(row))


@router.delete("/scripts/{script_id}", response_model=SuccessResponse, summary="删除 Web-UI 脚本")
async def delete_script(script_id: str, user: CurrentUserDep, db: DbSessionDep):
    row = (await db.execute(
        select(WebUiScript).where(WebUiScript.id == UUID(script_id)))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="脚本不存在")
    await db.delete(row)
    await db.commit()
    return SuccessResponse(success=True, data={"deleted": True})


async def _run_and_record(script_id: str, auto_repair: bool | None,
                          triggered_by: str = "manual") -> None:
    """后台任务：跑 spec、必要时自修复、把每一轮结果落库。

    关键是**先把一条 running 记录写进库再开跑**：前端要能在执行的当下就看到
    「正在跑 + 跑到第几条」，而不是等整轮（含自修复）结束才凭空冒出一条结果。
    运行目录名由这里生成并交给 runner，这样进度文件的位置在跑之前就已知。
    """
    from src.app.db.database import async_session_factory

    async with async_session_factory() as db:
        script = (await db.execute(
            select(WebUiScript).where(WebUiScript.id == UUID(script_id)))).scalars().first()
        if script is None:
            return

        run_dir_name = f"run-{uuid4().hex[:16]}"
        pending = WebUiScriptRun(
            script_id=script.id, status="running", triggered_by=triggered_by,
            repair_attempt=0, runner_run_id=run_dir_name,
        )
        db.add(pending)
        await db.commit()

        try:
            attempts = await playwright_service.run_script(
                script, auto_repair=auto_repair, first_run_id=run_dir_name)
        except Exception as exc:  # noqa: BLE001
            pending.status = "error"
            pending.exit_code = -2
            pending.output = f"执行异常: {exc}"
            script.status = "broken"
            await db.commit()
            return

        # 第一轮回填到那条 running 记录上（前端正在看的就是它），自修复轮另起新行
        first, *repairs = attempts
        pending.status = first["status"]
        pending.exit_code = first["exit_code"]
        pending.output = first["output"]
        pending.report = _dump(first.get("report"))
        pending.artifacts = _dump(first.get("artifacts"))
        pending.duration_ms = first["duration_ms"]
        pending.runner_run_id = first.get("runner_run_id") or run_dir_name
        for attempt in repairs:
            db.add(WebUiScriptRun(
                script_id=script.id,
                status=attempt["status"],
                exit_code=attempt["exit_code"],
                output=attempt["output"],
                report=_dump(attempt.get("report")),
                artifacts=_dump(attempt.get("artifacts")),
                duration_ms=attempt["duration_ms"],
                triggered_by="self_repair",
                repair_attempt=attempt["repair_attempt"],
                runner_run_id=attempt.get("runner_run_id"),
            ))
        script.status = "active" if attempts[-1]["status"] == "passed" else "broken"
        await db.commit()


@router.post("/scripts/{script_id}/run", response_model=SuccessResponse,
             summary="执行 Web-UI 脚本(后台)")
async def run_script(script_id: str, user: CurrentUserDep, db: DbSessionDep,
                     background: BackgroundTasks, data: RunRequest | None = None):
    row = (await db.execute(
        select(WebUiScript).where(WebUiScript.id == UUID(script_id)))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="脚本不存在")
    background.add_task(_run_and_record, script_id, data.auto_repair if data else None)
    return SuccessResponse(success=True, data={
        "started": True,
        "max_repair": settings.web_ui_max_repair,
    })


@router.get("/scripts/{script_id}/runs", response_model=SuccessResponse,
            summary="Web-UI 脚本执行历史")
async def list_runs(script_id: str, user: CurrentUserDep, db: DbSessionDep):
    rows = list((await db.execute(
        select(WebUiScriptRun).where(WebUiScriptRun.script_id == UUID(script_id))
        .order_by(WebUiScriptRun.created_at.desc()).limit(30)
    )).scalars().all())
    script = (await db.execute(
        select(WebUiScript.name).where(WebUiScript.id == UUID(script_id)))).scalar()
    return SuccessResponse(success=True, data=[
        {**_run_dict(r), "script_name": script} for r in rows
    ])


@router.get("/runs/{run_id}", response_model=SuccessResponse, summary="单次执行详情")
async def get_run(run_id: str, user: CurrentUserDep, db: DbSessionDep):
    row = (await db.execute(
        select(WebUiScriptRun).where(WebUiScriptRun.id == UUID(run_id)))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return SuccessResponse(success=True, data=_run_dict(row))


# --- 执行中的实时进度 ----------------------------------------------------------

#: Playwright 的 list reporter 会输出 ANSI 颜色；日志尾直接给前端显示，先剥掉
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _tail_text(path: Path, limit: int = 6000) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _read_progress_events(path: Path) -> list[dict]:
    """只取最后若干行——一次执行最多几十条事件，不需要全读。"""
    if not path.is_file():
        return []
    try:
        lines = path.read_text("utf-8", errors="replace").splitlines()[-400:]
    except OSError:
        return []
    events: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # 正在写入的半行，跳过
    return events


@router.get("/runs/{run_id}/progress", response_model=SuccessResponse,
            summary="执行中的实时进度（供轮询）")
async def run_progress(run_id: str, user: CurrentUserDep, db: DbSessionDep):
    """执行过程中的实时状态。

    数据来自运行目录里由 sidecar 边跑边写的两份文件：
    - ``progress.ndjson``：自定义 reporter 逐条用例落的结构化事件（总数/状态/耗时）
    - ``stdout.log``：CLI 原样输出（给人看的"此刻在做什么"）

    后端容器与 sidecar 挂的是同一个 runs 目录，所以直接读磁盘即可，
    既不需要长连接，也不需要额外的代理层。
    """
    run = await _require_run(db, run_id)
    root = _runs_root() / (run.runner_run_id or "")
    events = _read_progress_events(root / "progress.ndjson")
    log_tail = _ANSI_RE.sub("", _tail_text(root / "stdout.log"))

    begin = next((e for e in events if e.get("event") == "begin"), None)
    results = [e for e in events if e.get("event") == "test"]
    finished = any(e.get("event") == "end" for e in events)
    passed = sum(1 for e in results if e.get("status") == "passed")
    failed = sum(1 for e in results
                 if e.get("status") in ("failed", "timedOut", "interrupted"))
    skipped = sum(1 for e in results if e.get("status") == "skipped")

    return SuccessResponse(success=True, data={
        "run_id": str(run.id),
        # 库状态与文件状态合起来判：进程刚死时文件里还没写 end，而记录可能已被标为失败
        "running": run.status == "running" and not finished,
        "stale": run.status == "running" and _age_seconds(run) > settings.web_ui_run_timeout_s + 120,
        "elapsed_ms": int(_age_seconds(run) * 1000),
        "total": (begin or {}).get("total"),
        "done": len(results),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "started": begin is not None,
        "events": results[-60:],
        "log_tail": log_tail,
    })


# --- 批量执行 -----------------------------------------------------------------

class BatchRunRequest(BaseModel):
    script_ids: list[str] = []
    module: str | None = None
    auto_repair: bool | None = None


async def _batch_runner(script_ids: list[str], auto_repair: bool | None) -> None:
    """串行跑一批脚本。

    故意不并发：sidecar 里的浏览器是重资源，同时开几个 spec 只会让首屏更慢、
    超时更容易触发；批量回归要的是稳定的总时长，不是最快的单次。
    """
    for script_id in script_ids:
        try:
            await _run_and_record(script_id, auto_repair, triggered_by="batch")
        except Exception:  # noqa: BLE001 — 一条挂了不能拖垮整批
            logger.warning("批量执行脚本 %s 失败", script_id, exc_info=True)


@router.post("/scripts/batch-run", response_model=SuccessResponse, summary="批量执行 Web-UI 脚本（后台串行）")
async def batch_run(data: BatchRunRequest, user: CurrentUserDep, db: DbSessionDep,
                    background: BackgroundTasks):
    query = select(WebUiScript)
    if data.script_ids:
        try:
            query = query.where(WebUiScript.id.in_([UUID(s) for s in data.script_ids]))
        except ValueError:
            raise HTTPException(status_code=400, detail="script_ids 里有非法 id")
    elif data.module:
        query = query.where(WebUiScript.module == data.module)
    else:
        raise HTTPException(status_code=400, detail="需要 script_ids 或 module")
    rows = list((await db.execute(query)).scalars().all())
    if not rows:
        raise HTTPException(status_code=404, detail="没有匹配的脚本")
    ids = [str(r.id) for r in rows]
    # 批量执行时把脚本标成 running 之外的状态没意义（每条执行自会写自己的行），
    # 这里只把任务排进后台队列。
    background.add_task(_batch_runner, ids, data.auto_repair)
    return SuccessResponse(success=True, data={
        "queued": len(ids),
        "scripts": [{"id": str(r.id), "name": r.name} for r in rows],
        "max_repair": settings.web_ui_max_repair,
    })


# --- 全局执行记录与统计 --------------------------------------------------------

@router.get("/runs", response_model=SuccessResponse, summary="全部执行记录（可按脚本/状态过滤）")
async def list_all_runs(user: CurrentUserDep, db: DbSessionDep,
                        script_id: str | None = None, status: str | None = None,
                        latest_per_script: bool = False,
                        limit: int = Query(50, ge=1, le=200)):
    """执行记录列表。

    ``latest_per_script=true`` 时每个脚本只返回**最近一次**执行——用例库列表要靠它
    显示「最近结果」。这件事必须在 SQL 里做：前端按 limit 截断后再去重的话，
    某个脚本若最近没跑，它的最近一次会被挤出窗口，显示成「未执行过」。
    """
    query = (select(WebUiScriptRun, WebUiScript.name)
             .join(WebUiScript, WebUiScript.id == WebUiScriptRun.script_id, isouter=True))
    if script_id:
        query = query.where(WebUiScriptRun.script_id == UUID(script_id))
    if status:
        query = query.where(WebUiScriptRun.status == status)
    if latest_per_script:
        newest = (select(WebUiScriptRun.script_id,
                         func.max(WebUiScriptRun.created_at).label("newest"))
                  .group_by(WebUiScriptRun.script_id).subquery())
        query = query.join(newest, and_(
            WebUiScriptRun.script_id == newest.c.script_id,
            WebUiScriptRun.created_at == newest.c.newest,
        ))
        rows = (await db.execute(query.limit(limit))).all()
    else:
        rows = (await db.execute(
            query.order_by(WebUiScriptRun.created_at.desc()).limit(limit))).all()
    return SuccessResponse(success=True, data=[
        {**_run_dict(run), "script_name": name} for run, name in rows
    ])


@router.get("/stats/overview", response_model=SuccessResponse, summary="执行概览与趋势")
async def stats_overview(user: CurrentUserDep, db: DbSessionDep,
                         days: int = Query(14, ge=1, le=90)):
    """给页面顶部的汇总卡片与趋势图用。

    趋势按「天」聚合 stats 里的 expected/unexpected（那是 CLI 真实跑出来的用例
    数），而不是按执行次数——一次执行跑 10 条用例和跑 1 条，意义完全不同。
    """
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    runs = list((await db.execute(
        select(WebUiScriptRun).where(WebUiScriptRun.created_at >= since)
        .order_by(WebUiScriptRun.created_at.asc())
    )).scalars().all())
    scripts_total = (await db.execute(
        select(WebUiScript.id))).scalars().all()

    buckets: dict[str, dict] = {}
    expected_total = unexpected_total = skipped_total = 0
    durations: list[int] = []
    failures: dict[str, int] = {}
    for run in runs:
        report = json.loads(run.report) if run.report else {}
        stats = (report or {}).get("stats") or {}
        expected = int(stats.get("expected") or 0)
        unexpected = int(stats.get("unexpected") or 0)
        skipped = int(stats.get("skipped") or 0)
        expected_total += expected
        unexpected_total += unexpected
        skipped_total += skipped
        if run.duration_ms:
            durations.append(run.duration_ms)
        day = (run.created_at or datetime.now(timezone.utc).replace(tzinfo=None)).date().isoformat()
        bucket = buckets.setdefault(day, {
            "date": day, "runs": 0, "expected": 0, "unexpected": 0,
            "skipped": 0, "duration_ms_total": 0, "passed_runs": 0,
        })
        bucket["runs"] += 1
        bucket["expected"] += expected
        bucket["unexpected"] += unexpected
        bucket["skipped"] += skipped
        bucket["duration_ms_total"] += run.duration_ms or 0
        if run.status == "passed":
            bucket["passed_runs"] += 1
        for test in (report or {}).get("tests") or []:
            if test.get("status") == "failed":
                title = str(test.get("fullTitle") or test.get("title") or "?")
                failures[title] = failures.get(title, 0) + 1

    trend = []
    for day in sorted(buckets):
        bucket = buckets[day]
        cases = bucket["expected"] + bucket["unexpected"]
        trend.append({
            **{k: bucket[k] for k in ("date", "runs", "expected", "unexpected", "skipped")},
            "pass_rate": round(bucket["expected"] / cases, 4) if cases else None,
            "avg_duration_ms": int(bucket["duration_ms_total"] / bucket["runs"]) if bucket["runs"] else 0,
        })

    cases_total = expected_total + unexpected_total
    return SuccessResponse(success=True, data={
        "window_days": days,
        "scripts": len(scripts_total),
        "runs": len(runs),
        "cases": cases_total,
        "expected": expected_total,
        "unexpected": unexpected_total,
        "skipped": skipped_total,
        "pass_rate": round(expected_total / cases_total, 4) if cases_total else None,
        "avg_duration_ms": int(sum(durations) / len(durations)) if durations else 0,
        "trend": trend,
        "top_failures": sorted(
            ({"title": title, "count": count} for title, count in failures.items()),
            key=lambda item: item["count"], reverse=True)[:10],
    })


# --- 产物与报告（签名 URL，供浏览器直接取用）------------------------------------

@router.get("/artifact/{run_id}/{path:path}", include_in_schema=False)
async def get_artifact(run_id: str, path: str, db: DbSessionDep, sig: str = Query("")):
    """按执行记录回取单个产物（截图 / 视频 / trace.zip / error-context）。

    鉴权靠 URL 签名而不是 token：`<img>`、`<video>`、新标签页下载都是浏览器
    自己发的请求，带不上前端设置的自定义头。签名由 share_link 覆盖 run_id，
    所以一个执行的签名换不到另一个执行的产物。
    """
    run = await _require_run(db, run_id)
    if not share_link.verify(sig, run_id):
        raise HTTPException(status_code=403, detail="链接无效或已过期")
    target = _artifact_path(run, path)
    if target is None:
        if _run_dir_gone(run):
            raise HTTPException(
                status_code=410,
                detail="该次执行的产物文件已被清理，无法回看；重新执行即可重新生成存证")
        raise HTTPException(status_code=404, detail="产物不存在")
    return FileResponse(target, media_type=_media_type(target))


@router.get("/report/{run_id}/{sig}/{path:path}", include_in_schema=False)
async def get_report(run_id: str, sig: str, path: str, db: DbSessionDep):
    """托管 Playwright 官方 HTML 报告（含内嵌的 trace 查看器）。

    签名放在**路径里**而不是查询串：报告是一整个目录，index.html 里的资源引用
    全是相对路径，浏览器请求 `data/x.png`、`trace/index.html` 时会原样保留前缀，
    签名也就跟过去了。放查询串只有入口那一次带得上，子资源全会 403。
    """
    run = await _require_run(db, run_id)
    if not share_link.verify(sig, run_id):
        raise HTTPException(status_code=403, detail="链接无效或已过期")
    target = _artifact_path(run, f"html-report/{path or 'index.html'}")
    if target is None:
        raise HTTPException(status_code=404, detail="报告不存在（该次执行未生成 HTML 报告）")
    return FileResponse(target, media_type=_media_type(target))


async def _require_run(db: DbSessionDep, run_id: str) -> WebUiScriptRun:
    try:
        uid = UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    row = (await db.execute(
        select(WebUiScriptRun).where(WebUiScriptRun.id == uid))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return row


#: 报告是给浏览器渲染的静态站点，MIME 错一个就会出现「模块脚本被拒绝执行」这类
#: 静默白屏；slim 镜像的 mimetypes 库也不保证认识 .webm / .mjs，所以关键类型写死。
_MEDIA_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webm": "video/webm",
    ".zip": "application/zip",
    ".md": "text/markdown; charset=utf-8",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}


def _media_type(path: Path) -> str:
    return _MEDIA_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] \
        or "application/octet-stream"
