"""Eval routes (测评模块).

Runs the same pipeline as ``python -m src.app.eval.cli`` — dataset load →
LangGraph runs → deterministic + judge scores → Langfuse upload → gate — but
launched from the platform UI and persisted, so batches are reviewable
side by side.

The heavy lifting is imported lazily: this module must stay importable when the
optional eval dependencies (or Langfuse) are absent, because it is registered
unconditionally in the API router.
"""

import asyncio
import contextlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from src.app.api.deps import DbSessionDep
from src.app.api.v2.auth import CurrentUserDep
from src.app.core.config import settings
from src.app.db.models.eval_run import EvalBatch, EvalCaseResult
from src.app.db.schemas.common import SuccessResponse
from src.app.eval import live as live_mod

logger = logging.getLogger(__name__)


def langfuse_client_for(values: dict[str, str]):
    """按生效配置构造 Langfuse 客户端（设置页优先，其次 .env）。"""
    from src.app.eval.langfuse_client import LangfuseClient

    enabled = str(values.get("langfuse_enabled", "")).strip().lower() not in ("", "0", "false", "no")
    # 地址翻译在 LangfuseClient 构造函数里做（唯一入口）
    return LangfuseClient(
        host=values.get("langfuse_base_url") or None,
        public_key=values.get("langfuse_public_key") or None,
        secret_key=values.get("langfuse_secret_key") or None,
        enabled=enabled,
    )

router = APIRouter(prefix="/eval")


class RunRequest(BaseModel):
    #: 单个数据集（旧字段，保留兼容）；多选时用 datasets
    dataset: str | None = None
    #: 一次启动多个数据集 → 每个数据集起一个批次（批次是一数据集一 agent 的）
    datasets: list[str] = []
    agent: str | None = None
    concurrency: int = 1
    release: str | None = None
    gate: str | None = None
    judge: bool = True
    langfuse: bool = True
    #: 只跑这些用例（数据集内自定义选择）；留空 = 全跑
    item_ids: list[str] = []


def _age_seconds(batch: EvalBatch) -> float:
    """批次创建至今多少秒（库里是 naive UTC，统一到 UTC 再比）。"""
    if batch.created_at is None:
        return 0.0
    created = batch.created_at
    if created.tzinfo is not None:
        created = created.astimezone(timezone.utc).replace(tzinfo=None)
    return (datetime.now(timezone.utc).replace(tzinfo=None) - created).total_seconds()


def _batch_dict(batch: EvalBatch, *, full: bool = False,
                done_cases: int | None = None, stale: bool | None = None) -> dict:
    if stale is None:
        stale = (batch.status == "running"
                 and live_mod.is_stale(str(batch.id), created_age_s=_age_seconds(batch)))
    data = {
        "id": str(batch.id), "dataset": batch.dataset, "run_name": batch.run_name,
        "agent": batch.agent, "release": batch.release, "status": batch.status,
        "gate_expression": batch.gate_expression, "gate_passed": batch.gate_passed,
        "gate_output": batch.gate_output,
        "total_cases": batch.total_cases, "scored_cases": batch.scored_cases,
        "failed_cases": batch.failed_cases,
        # 完成数 = 已落库的用例行数。scored_cases 只数"有分数的"，
        # 用例没写期望值（没有分数可算）时它永远追不上总数，进度条会卡住。
        "done_cases": done_cases if done_cases is not None
        else batch.scored_cases + batch.failed_cases,
        "stale": stale,
        "averages": json.loads(batch.averages) if batch.averages else {},
        "duration_ms": batch.duration_ms, "langfuse_host": batch.langfuse_host,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
    }
    if full:
        data["output"] = batch.output
    return data


def _case_dict(case: EvalCaseResult) -> dict:
    return {
        "id": str(case.id), "item_id": case.item_id, "instruction": case.instruction,
        "trace_id": case.trace_id, "thread_id": case.thread_id, "status": case.status,
        "error": case.error, "duration_ms": case.duration_ms,
        "scores": json.loads(case.scores) if case.scores else [],
        "tool_names": json.loads(case.tool_names) if case.tool_names else [],
        "evidence": json.loads(case.evidence) if case.evidence else [],
    }


# --- status & datasets --------------------------------------------------------

@router.get("/status", response_model=SuccessResponse, summary="测评环境状态")
async def eval_status(user: CurrentUserDep, db: DbSessionDep):
    from src.app.eval.dataset import DEFAULT_DATASET_DIR
    from src.app.eval.langfuse_client import LangfuseClient
    from src.app.eval.scorers import judge_endpoint_from_values
    from src.app.services.settings_service import SettingsService

    svc = SettingsService(db)
    client = langfuse_client_for(await svc.langfuse_values())
    langfuse: dict = {"enabled": client.enabled, "host": client.host}
    if client.enabled:
        reachable = client._get("/api/public/projects")  # noqa: SLF001 — probe only
        langfuse["reachable"] = reachable is not None
        langfuse["organizations"] = len((reachable or {}).get("data") or [])
        # 界面路由需要项目 id（/project/<id>/traces/<traceId>），拼链接要用
        langfuse["project_id"] = client.project_id()
    client.close()

    # 裁判配置走"设置页优先"的同一条解析路径，保证卡片显示的就是批次实际会用的；
    # source 告诉界面这个模型名是独立配的，还是继承主 LLM 来的。
    judge_values = await svc.judge_values()
    endpoint = judge_endpoint_from_values(judge_values, await svc.model_values())
    return SuccessResponse(success=True, data={
        "langfuse": langfuse,
        "judge": {"model": endpoint.model, "base_url": endpoint.base_url,
                  "configured": bool(endpoint.api_key), "source": endpoint.source,
                  "explicit_model": judge_values.get("judge_model") or ""},
        "datasets_dir": str(DEFAULT_DATASET_DIR),
        "max_repair": settings.eval_max_repair,
    })


@router.get("/datasets", response_model=SuccessResponse, summary="评测集列表")
async def list_datasets(user: CurrentUserDep):
    from src.app.eval.dataset import DEFAULT_DATASET_DIR, load_dataset

    out = []
    for path in sorted(DEFAULT_DATASET_DIR.glob("*.yaml")):
        try:
            dataset = load_dataset(path)
            out.append({"file": path.name, "name": dataset.name,
                        "description": dataset.description, "agent": dataset.agent,
                        "items": len(dataset.items),
                        "has_judge": any(item.judge is not None for item in dataset.items),
                        "gate_hint": _gate_hint(dataset)})
        except Exception as exc:  # noqa: BLE001 — a broken YAML must not hide the rest
            out.append({"file": path.name, "error": str(exc)[:300]})
    return SuccessResponse(success=True, data=out)


def _gate_hint(dataset) -> str | None:
    """A gate worth trying for this dataset, derived from the scorers it feeds."""
    names = set()
    for item in dataset.items:
        expected = item.expected
        if expected is None:
            continue
        if expected.contains:
            names.add("task_output_match")
        if expected.tools is not None:
            names.add("tool_sequence")
        if expected.max_tool_errors is not None:
            names.add("tool_errors")
    if any(item.judge is not None for item in dataset.items):
        names.add("llm_judge")
    if not names:
        return None
    clauses = [f"{'max' if n == 'tool_errors' else 'avg'}({n})"
               + ("<=2" if n == "tool_errors" else ">=0.8")
               for n in sorted(names) if n != "tool_sequence"]
    if "tool_sequence" in names:
        clauses.append("all(tool_sequence)")
    return " && ".join(clauses)


# --- 评测集的增删改查（页面上的编辑器用）-------------------------------------

#: 只允许 datasets/ 下的普通 yaml 文件名：不含路径分隔符，天然挡住了目录穿越
_DATASET_FILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,118}\.ya?ml")


class ToolSpecPayload(BaseModel):
    sequence: list[str] = []
    mode: str = "subsequence"


class ExpectedPayload(BaseModel):
    contains: list[str] = []
    not_contains: list[str] = []
    tools: ToolSpecPayload | None = None
    evidence: str | None = None
    max_tool_errors: int | None = None


class JudgePayload(BaseModel):
    criteria: str = ""
    # `pass` 是 python 关键字，字段名换成 pass_threshold，序列化回 YAML 时再改回 pass
    pass_threshold: float = Field(default=0.7, alias="pass")

    model_config = {"populate_by_name": True}


class DatasetItemPayload(BaseModel):
    id: str = ""
    input: str
    expected: ExpectedPayload | None = None
    judge: JudgePayload | None = None
    metadata: dict = {}


class DatasetPayload(BaseModel):
    #: 新建时必填（写入 datasets/<file>）；更新时以 URL 里的文件名为准
    file: str | None = None
    name: str
    description: str | None = None
    agent: str = "webui_agent"
    max_repair: int | None = None
    items: list[DatasetItemPayload]


def _dataset_dir() -> Path:
    from src.app.eval.dataset import DEFAULT_DATASET_DIR

    DEFAULT_DATASET_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DATASET_DIR


def _dataset_path(file: str) -> Path:
    """文件名 → 绝对路径，越界（子目录、绝对路径、非 yaml）一律拒绝。"""
    if not _DATASET_FILE_RE.fullmatch(file or ""):
        raise HTTPException(status_code=400, detail="文件名只能是字母数字._- 组成的 *.yaml")
    root = _dataset_dir().resolve()
    path = (root / file).resolve()
    if path.parent != root:
        raise HTTPException(status_code=400, detail="文件名不合法")
    return path


def _payload_to_dict(data: DatasetPayload) -> dict:
    """去掉空壳字段：编辑器里没填的期望不该在 YAML 里留一堆空 key。"""
    items: list[dict] = []
    for index, item in enumerate(data.items):
        entry: dict = {"id": item.id.strip() or f"item-{index + 1}", "input": item.input}
        expected = item.expected
        if expected is not None:
            block: dict = {}
            if expected.contains:
                block["contains"] = [v for v in expected.contains if v.strip()]
            if expected.not_contains:
                block["not_contains"] = [v for v in expected.not_contains if v.strip()]
            if expected.tools is not None and expected.tools.sequence:
                block["tools"] = {"sequence": [v for v in expected.tools.sequence if v.strip()],
                                  "mode": expected.tools.mode}
            if expected.max_tool_errors is not None:
                block["max_tool_errors"] = expected.max_tool_errors
            if expected.evidence:
                block["evidence"] = expected.evidence
            if block:
                entry["expected"] = block
        if item.judge is not None and item.judge.criteria.strip():
            entry["judge"] = {"criteria": item.judge.criteria,
                              "pass": item.judge.pass_threshold}
        if item.metadata:
            entry["metadata"] = item.metadata
        items.append(entry)
    return {"name": data.name.strip(), "description": data.description, "agent": data.agent,
            "max_repair": data.max_repair, "items": items}


def _validate_payload(data: DatasetPayload) -> None:
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="name 不能为空（批次名会用它）")
    if not data.items:
        raise HTTPException(status_code=400, detail="至少要有一条用例")
    for index, item in enumerate(data.items, start=1):
        if not item.input.strip():
            raise HTTPException(status_code=400, detail=f"第 {index} 条用例的 input 不能为空")
    ids = [(item.id.strip() or f"item-{i}") for i, item in enumerate(data.items, start=1)]
    duplicate = next((v for v in ids if ids.count(v) > 1), None)
    if duplicate:
        raise HTTPException(status_code=400, detail=f"用例 id 重复：{duplicate}")


@router.get("/datasets/{file}", response_model=SuccessResponse, summary="评测集详情（含原始 YAML）")
async def get_dataset(file: str, user: CurrentUserDep):
    from src.app.eval.dataset import dataset_payload, load_dataset

    path = _dataset_path(file)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="评测集不存在")
    raw = path.read_text(encoding="utf-8")
    try:
        dataset = load_dataset(path)
    except Exception as exc:  # noqa: BLE001
        # 解析不了也要能打开：否则一个手改坏的 YAML 在页面上就是死文件，只能去
        # 命令行删。界面会显示原始内容 + 错误原因，允许直接覆盖修好。
        return SuccessResponse(success=True, data={
            "file": path.name, "name": "", "agent": "", "items": [], "raw": raw,
            "error": str(exc), "gate_hint": None,
        })
    return SuccessResponse(success=True, data={
        **dataset_payload(dataset, file=path.name),
        "raw": raw,
        "gate_hint": _gate_hint(dataset),
    })


@router.post("/datasets", response_model=SuccessResponse, status_code=201, summary="新建评测集")
async def create_dataset(data: DatasetPayload, user: CurrentUserDep):
    from src.app.eval.dataset import dataset_payload, load_dataset, save_dataset

    _validate_payload(data)
    path = _dataset_path(data.file or "")
    if path.exists():
        raise HTTPException(status_code=409, detail=f"{path.name} 已存在，请换一个文件名")
    try:
        saved = save_dataset(path, _payload_to_dict(data))
    except Exception as exc:  # noqa: BLE001 — 校验失败要把原因原样给用户
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("评测集已创建: %s（%d 条用例）", path.name, len(saved.items))
    return SuccessResponse(success=True, data={
        **dataset_payload(saved, file=path.name), "gate_hint": _gate_hint(load_dataset(path)),
    })


@router.put("/datasets/{file}", response_model=SuccessResponse, summary="保存评测集")
async def update_dataset(file: str, data: DatasetPayload, user: CurrentUserDep):
    from src.app.eval.dataset import dataset_payload, load_dataset, save_dataset

    _validate_payload(data)
    path = _dataset_path(file)
    existed = path.exists()
    try:
        saved = save_dataset(path, _payload_to_dict(data))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("评测集已%s: %s（%d 条用例）", "更新" if existed else "创建", path.name, len(saved.items))
    return SuccessResponse(success=True, data={
        **dataset_payload(saved, file=path.name), "gate_hint": _gate_hint(load_dataset(path)),
    })


@router.delete("/datasets/{file}", response_model=SuccessResponse, summary="删除评测集")
async def delete_dataset(file: str, user: CurrentUserDep, db: DbSessionDep):
    from src.app.eval.dataset import load_dataset

    path = _dataset_path(file)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="评测集不存在")
    name = load_dataset(path).name
    running = (await db.execute(
        select(func.count()).select_from(EvalBatch)
        .where(EvalBatch.status == "running", EvalBatch.dataset == name))).scalar() or 0
    if running:
        raise HTTPException(status_code=409, detail=f"有 {running} 个批次正在跑这个评测集，先等它跑完")
    path.unlink()
    logger.info("评测集已删除: %s", path.name)
    return SuccessResponse(success=True, data={"file": path.name, "deleted": True})


# --- AI 生成测评集（从历史对话的完整记录提炼）---------------------------------

class GenerateRequest(BaseModel):
    #: 数据来源：一段或多段历史对话（thread_id）
    thread_ids: list[str]
    #: 目标被测 agent（评测集里的 agent 字段 + prompt 里的约束）
    agent: str = "testcase_agent"
    #: 期望生成几条
    count: int = 5
    #: 额外要求（用户补充的侧重点）
    focus: str = ""
    #: 数据集名/文件名建议
    name: str = ""


@router.get("/sources", response_model=SuccessResponse, summary="可作为生成来源的历史对话")
async def list_generation_sources(user: CurrentUserDep, db: DbSessionDep,
                                  agent: str | None = None, limit: int = 50):
    """列出可用于 AI 生成测评集的对话（带各自的 agent 与消息数）。

    只列**有消息的**会话：零消息的空壳线程拿来生成不了任何东西。
    """
    from src.app.db.models.thread_info import ThreadInfo
    from src.app.db.models.thread_message import ThreadMessage

    counts = dict((await db.execute(
        select(ThreadMessage.thread_id, func.count())
        .group_by(ThreadMessage.thread_id))).all())
    stmt = select(ThreadInfo).where(ThreadInfo.deleted.is_(False))
    if agent:
        stmt = stmt.where(ThreadInfo.agent == agent)
    rows = list((await db.execute(
        stmt.order_by(ThreadInfo.updated_at.desc()).limit(max(1, min(limit, 200))))).scalars().all())
    data = []
    for row in rows:
        count = counts.get(row.thread_id, 0)
        if not count:
            continue
        data.append({
            "thread_id": row.thread_id,
            "title": row.title,
            "agent": getattr(row, "agent", "") or "",
            "messages": count,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        })
    return SuccessResponse(success=True, data=data)


@router.post("/datasets/generate", response_model=SuccessResponse, summary="AI 生成测评集（草稿）")
async def generate_dataset(data: GenerateRequest, user: CurrentUserDep, db: DbSessionDep):
    """把历史对话的完整记录交给主 LLM，提炼成一份**待微调**的评测集草稿。

    只返回草稿（结构与数据集详情一致），不落盘：生成结果一定要经过人工微调
    才成为正式评测集，保存动作留给页面上的编辑器。
    """
    from src.app.db.models.thread_info import ThreadInfo
    from src.app.db.models.thread_message import ThreadMessage
    from src.app.eval.generator import generate_items, render_transcript, suggested_file
    from src.app.services.settings_service import SettingsService

    thread_ids = [t for t in (data.thread_ids or []) if t]
    if not thread_ids:
        raise HTTPException(status_code=400, detail="请选择至少一段历史对话作为来源")
    count = max(1, min(int(data.count or 5), 20))

    chunks: list[str] = []
    sources: list[dict] = []
    for thread_id in thread_ids[:5]:
        info = (await db.execute(
            select(ThreadInfo).where(ThreadInfo.thread_id == thread_id))).scalars().first()
        rows = list((await db.execute(
            select(ThreadMessage).where(ThreadMessage.thread_id == thread_id)
            .order_by(ThreadMessage.seq_index.asc()))).scalars().all())
        if not rows:
            raise HTTPException(status_code=400, detail=f"会话 {thread_id} 没有已保存的消息")
        title = (info.title if info else "") or thread_id
        chunks.append(render_transcript(rows, title=title))
        sources.append({"thread_id": thread_id, "title": title,
                        "agent": (getattr(info, "agent", "") if info else "") or "",
                        "messages": len(rows)})

    svc = SettingsService(db)
    model_values = await svc.model_values()
    base_url = (model_values.get("llm_base_url") or "").strip() or settings.llm_base_url
    api_key = (model_values.get("llm_api_key") or "").strip() or model_values.get("deepseek_api_key") or settings.deepseek_api_key
    model = ((model_values.get("llm_model") or "").strip() or model_values.get("deepseek_model")
             or settings.llm_model or settings.deepseek_model)
    try:
        payload = await generate_items(
            transcript="\n\n---\n\n".join(chunks), agent=data.agent or "testcase_agent",
            count=count, base_url=base_url, api_key=api_key, model=model,
            focus=data.focus, name_hint=data.name)
    except Exception as exc:  # noqa: BLE001 — 生成失败的原因要原样给用户看
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload["file"] = suggested_file(payload["name"], _dataset_dir())
    logger.info("AI 生成评测集草稿：%s（%d 条，来源 %d 段对话，模型 %s）",
                payload["file"], len(payload["items"]), len(sources), model)
    return SuccessResponse(success=True, data={
        "dataset": payload, "sources": sources, "model": model,
        "note": "草稿尚未保存。请核对/微调后再点保存，它才会写进 datasets/ 成为评测集。",
    })


# --- batches ------------------------------------------------------------------

@router.get("/batches", response_model=SuccessResponse, summary="测评批次列表")
async def list_batches(user: CurrentUserDep, db: DbSessionDep):
    rows = list((await db.execute(
        select(EvalBatch).order_by(EvalBatch.created_at.desc()).limit(50)
    )).scalars().all())
    # 一次分组查询拿到各批次的完成数：列表要显示"跑到第几条"，一条一条 count
    # 就是 50 次往返（实时进度面板在轮询这条路）。
    counts = dict((await db.execute(
        select(EvalCaseResult.batch_id, func.count())
        .where(EvalCaseResult.batch_id.in_([b.id for b in rows]))
        .group_by(EvalCaseResult.batch_id)
    )).all()) if rows else {}
    return SuccessResponse(success=True, data=[
        _batch_dict(b, done_cases=counts.get(b.id, 0)) for b in rows
    ])


@router.get("/batches/{batch_id}", response_model=SuccessResponse, summary="批次详情")
async def get_batch(batch_id: str, user: CurrentUserDep, db: DbSessionDep):
    batch = await _load_batch(db, batch_id)
    cases = list((await db.execute(
        select(EvalCaseResult).where(EvalCaseResult.batch_id == batch.id)
        .order_by(EvalCaseResult.created_at.asc())
    )).scalars().all())
    return SuccessResponse(success=True, data={
        **_batch_dict(batch, full=True, done_cases=len(cases)),
        "cases": [_case_dict(c) for c in cases],
    })


@router.get("/batches/{batch_id}/progress", response_model=SuccessResponse,
            summary="执行中的实时进度（供轮询）")
async def batch_progress(batch_id: str, user: CurrentUserDep, db: DbSessionDep):
    """批次执行现场的实时快照。

    数据来自执行进程边跑边写的两份文件（见 ``eval/live.py``）：
    ``live.ndjson`` 是结构化事件（逐条用例、工具调用、心跳），``live.log`` 是
    给人读的日志尾。心跳决定 ``stale``——记录写着"运行中"而执行进程已经没了
    （容器重启、被 kill）时，界面必须说出来，而不是永远转圈。
    """
    batch = await _load_batch(db, batch_id)
    state = live_mod.read_live(str(batch.id))
    running = batch.status == "running" and state["terminal"] is None
    return SuccessResponse(success=True, data={
        **state,
        "status": batch.status,
        "running": running,
        "stale": running and live_mod.is_stale(str(batch.id),
                                               created_age_s=_age_seconds(batch)),
        "total": state["total"] if state["total"] is not None else batch.total_cases,
        # 文件里没有开始事件时（进程还没写第一行）退回按批次创建时间算
        "elapsed_ms": (int(_age_seconds(batch) * 1000) if state["started_at"] is None
                       else state["elapsed_ms"]),
    })


@router.post("/run", response_model=SuccessResponse, status_code=202, summary="启动测评批次")
async def start_run(data: RunRequest, user: CurrentUserDep, db: DbSessionDep,
                    background: BackgroundTasks):
    """启动一个或多个批次。

    数据集可以多选（``datasets``）：批次是一数据集一 agent 的，所以多选 = 起多个
    批次，而不是把它们混成一个——混起来就没有"这个集子过了没有"的答案了。
    ``item_ids`` 用于在数据集内只跑选中的用例（先冒烟几条再全量跑）。
    """
    from src.app.eval.dataset import load_dataset

    files = [f for f in ([*data.datasets] or [data.dataset or ""]) if f]
    if not files:
        raise HTTPException(status_code=400, detail="请选择至少一个评测集")

    selected = {str(item).strip() for item in (data.item_ids or []) if str(item).strip()}
    batches: list[dict] = []
    for file in files:
        try:
            dataset = load_dataset(file)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"数据集 {file} 加载失败: {exc}") from exc
        if selected:
            missing = selected - {item.id for item in dataset.items}
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"数据集 {file} 里没有这些用例：{'、'.join(sorted(missing))}")
        options = data.model_dump()
        options["dataset"] = file
        if data.agent:
            dataset.agent = data.agent
        total = len(selected) if selected else len(dataset.items)
        batch = EvalBatch(
            dataset=dataset.name,
            run_name=f"{dataset.name}@{data.release or time.strftime('%Y%m%d-%H%M%S')}",
            agent=dataset.agent,
            release=data.release,
            status="running",
            gate_expression=data.gate,
            total_cases=total,
            langfuse_host=settings.langfuse_base_url if settings.langfuse_enabled else None,
        )
        db.add(batch)
        await db.commit()
        background.add_task(_execute_batch, str(batch.id), options)
        batches.append(_batch_dict(batch))
    return SuccessResponse(success=True, data=batches)


async def _execute_batch(batch_id: str, options: dict) -> None:
    """Background task: run the CLI pipeline and persist the outcome.

    结果**边跑边落库**：每条用例跑完立刻写 ``EvalCaseResult`` 并更新批次计数，
    同时把执行现场写进 ``eval-runs/<batchId>/``（见 ``eval/live.py``）。此前是整轮
    跑完才一次性入库，界面上一个 6 条用例的批次会有好几分钟只显示"用例 0/6"，
    用户既看不出在跑也看不出卡住。
    """
    from src.app.db.database import async_session_factory

    log: live_mod.LiveLog | None = None
    heartbeat: asyncio.Task | None = None

    async with async_session_factory() as db:
        batch = (await db.execute(
            select(EvalBatch).where(EvalBatch.id == UUID(batch_id)))).scalars().first()
        if batch is None:
            return
        try:
            log = live_mod.LiveLog(
                batch_id, total=batch.total_cases, dataset=batch.dataset,
                agent=batch.agent, concurrency=max(1, int(options.get("concurrency") or 1)))
            live_mod.LIVE.add(batch_id)
            heartbeat = asyncio.create_task(log.heartbeat_loop())
            await _run_batch(db, batch, options, log)
            log.finish(batch.status, summary=(batch.output or "")[:4_000])
        except Exception as exc:  # noqa: BLE001
            logger.exception("eval batch %s failed", batch_id)
            batch.status = "error"
            batch.output = f"批次执行失败: {exc}"
            if log is not None:
                log.finish("error", summary=batch.output)
        finally:
            await db.commit()
            if heartbeat is not None:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
            if log is not None:
                live_mod.LIVE.discard(batch_id)
                log.close()


async def _run_batch(db, batch: EvalBatch, options: dict, log: live_mod.LiveLog) -> None:
    """跑完整个评测集并把结果写进批次行；每条用例落地即入库。"""
    from src.app.eval.dataset import load_dataset
    from src.app.eval.gate import evaluate_gate
    from src.app.eval.runner import LangGraphDriver, LangfuseReporter, run_dataset
    from src.app.eval.scorers import LlmJudge, deterministic_scorers, judge_endpoint_from_values
    from src.app.services.settings_service import SettingsService

    dataset = load_dataset(options["dataset"])
    if options.get("agent"):
        dataset.agent = options["agent"]
    selected = {str(i).strip() for i in (options.get("item_ids") or []) if str(i).strip()}
    if selected:
        # 自定义选择：只跑选中的用例（先冒烟两条再全量的常用做法）
        dataset.items = [item for item in dataset.items if item.id in selected]
    log.set_total(len(dataset.items))

    svc = SettingsService(db)
    scorers = deterministic_scorers()
    if options.get("judge", True) and any(i.judge for i in dataset.items):
        # 裁判端点按"设置页优先"解析：网页保存后下一个批次立刻用新配置，
        # 不必重启容器（进程环境变量在重启前不会变）。
        scorers.append(LlmJudge(judge_endpoint_from_values(
            await svc.judge_values(), await svc.model_values())))

    def on_start(item) -> None:
        log.item_start(item.id)

    async def on_item(item, row) -> None:
        """一条用例落地：先进度文件（界面立刻可见），再入库并提交。"""
        log.item_done(
            item.id, status="error" if row.error else "ok",
            duration_ms=row.duration_ms,
            scores=[{"name": s.name, "value": s.value, "comment": s.comment}
                    for s in row.scores],
            tools=row.tool_names, error=row.error)
        db.add(EvalCaseResult(
            batch_id=batch.id, item_id=item.id, instruction=item.input,
            trace_id=row.trace_id or None, thread_id=row.thread_id,
            status="error" if row.error else "ok", error=row.error,
            duration_ms=row.duration_ms,
            scores=json.dumps([{
                "name": s.name, "value": s.value,
                "data_type": s.data_type, "comment": s.comment,
            } for s in row.scores], ensure_ascii=False),
            tool_names=json.dumps(row.tool_names, ensure_ascii=False),
            evidence=json.dumps(row.evidence, ensure_ascii=False),
        ))
        if row.scores:
            batch.scored_cases += 1
        if row.error:
            batch.failed_cases += 1
        await db.commit()

    client = langfuse_client_for(await svc.langfuse_values())
    reporter = None
    if options.get("langfuse", True) and client.enabled:
        reporter = LangfuseReporter(client, dataset.name)
        try:
            await reporter.mirror_dataset(dataset)
        except Exception as exc:  # noqa: BLE001
            logger.warning("mirror dataset failed: %s", exc)

    outcome = await run_dataset(
        dataset=dataset, scorers=scorers,
        driver=LangGraphDriver(release=options.get("release"),
                               note=lambda item, text: log.note(item.id, text)),
        reporter=reporter, concurrency=max(1, int(options.get("concurrency") or 1)),
        run_name=batch.run_name, on_start=on_start, on_item=on_item)

    if reporter is not None:
        for row in outcome.rows:
            if row.error or not row.trace_id or row.item.langfuse_item_id is None:
                continue
            await reporter.link(row.trace_id, row.item.langfuse_item_id, outcome.run_name)

    averages = _averages(outcome.rows)
    batch.averages = json.dumps(averages, ensure_ascii=False)
    batch.scored_cases = sum(1 for row in outcome.rows if row.scores)
    batch.failed_cases = sum(1 for row in outcome.rows if row.error)
    batch.duration_ms = sum(row.duration_ms for row in outcome.rows)
    gate_ok = True
    if options.get("gate"):
        gate = evaluate_gate(options["gate"], [row.scores for row in outcome.rows])
        batch.gate_output = "\n".join(gate.lines)
        batch.gate_passed = gate.ok
        gate_ok = gate.ok
    batch.status = ("passed" if gate_ok and not batch.failed_cases
                    else ("error" if batch.failed_cases == len(outcome.rows) else "failed"))
    batch.output = _summary_text(outcome)
    if reporter is not None:
        batch.output += "\n" + _reporting_line(reporter, len(outcome.rows))
    client.close()


def _reporting_line(reporter, row_count: int) -> str:
    """把「上报到 Langfuse 的结果」写进批次输出。

    为什么必须写进批次记录：CLI 会打印上报条数与失败数，但网页触发的批次**不经过
    CLI**——key 配错、磁盘满、自建实例挂了的时候，页面会照旧显示"通过、N 条用例有
    分数"（那些分数是进程内算出来的），而 Langfuse 里一条都没有。追踪链路断了却
    看起来一切正常，是最难查的一种故障。
    """
    client = getattr(reporter, "client", None)
    if client is None or not getattr(client, "enabled", False):
        return "langfuse 上报：未启用（缺 LANGFUSE_ENABLED / PUBLIC_KEY / SECRET_KEY），测评结果只在本地"
    parts = [f"langfuse 上报：trace {reporter.traces_uploaded} 条"]
    if reporter.trace_failures:
        parts.append(f"失败 {reporter.trace_failures} 条")
    if reporter.link_failures:
        parts.append(f"DatasetRun 挂载失败 {reporter.link_failures} 次")
    line = "，".join(parts)
    if row_count and reporter.traces_uploaded == 0:
        line += ("\n⚠️ 一条都没上报成功——检查 LANGFUSE_BASE_URL 是否可达、"
                 "PUBLIC_KEY/SECRET_KEY 是否为该项目下有效密钥")
    return line


def _averages(rows) -> dict:
    totals: dict[str, list[float]] = {}
    for row in rows:
        for score in row.scores:
            if isinstance(score.value, bool):
                totals.setdefault(score.name, []).append(1.0 if score.value else 0.0)
            elif isinstance(score.value, (int, float)):
                totals.setdefault(score.name, []).append(float(score.value))
    return {name: round(sum(values) / len(values), 4) for name, values in totals.items() if values}


def _summary_text(outcome) -> str:
    lines = []
    for row in outcome.rows:
        if row.error:
            lines.append(f"✗ {row.item.id}: ERROR {row.error[:200]}")
            continue
        rendered = "  ".join(
            f"{s.name}={'✓' if s.value else '✗'}" if isinstance(s.value, bool)
            else f"{s.name}={round(float(s.value), 3)}" if isinstance(s.value, (int, float))
            else f"{s.name}={s.value}" for s in row.scores)
        lines.append(f"✓ {row.item.id}: {row.duration_ms / 1000:.1f}s  {rendered or '(无分数)'}")
    return "\n".join(lines)


async def _load_batch(db, batch_id: str) -> EvalBatch:
    try:
        uid = UUID(batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="批次 ID 非法") from exc
    batch = (await db.execute(
        select(EvalBatch).where(EvalBatch.id == uid))).scalars().first()
    if batch is None:
        raise HTTPException(status_code=404, detail="批次不存在")
    return batch
