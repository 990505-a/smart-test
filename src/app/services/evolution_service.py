"""Self-evolution service (自进化模块).

Nightly (or manual) self-improvement loop over annotated case documents:

1. **聚合 (aggregate)** — scan ``workspace/default/cases/*.md`` for documents
   carrying human annotations (heading ✅/❌/⚠️ marks and ``>`` note lines).
   Content-hash tracking (``.evolution_state.json``) feeds only documents
   that are new or changed since the last successful run.
2. **反思 (reflect)** — the LLM reads the RAW annotated markdown per
   document and distills good patterns / anti-patterns / missed-case
   lessons (用户补充的漏测用例与批注是核心信号).
3. **记录 (record)** — lessons are stored on the EvolutionRun (viewable in
   the /evolution page). The skill library is user-curated (manual upload);
   the run never writes SKILL.md files automatically.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from src.app.core.config import settings
from src.app.core.llms import get_deepseek_model
from src.app.db.database import async_session_factory
from src.app.db.models.evolution import EvolutionRun
from src.app.services import case_docs_service

logger = logging.getLogger(__name__)

# 每份文档喂给 LLM 的原文上限（字符）：防单文档过大撑爆上下文
_MAX_DOC_CHARS = 60_000

# A single process must not consume the same annotated documents concurrently.
# The scheduler and manual API both enter through run_evolution().
_evolution_lock = asyncio.Lock()

REFLECT_PROMPT = """你是一位游戏测试质量专家，负责测试平台的自进化（self-evolution）。
下面是「{module}」用例集的 Markdown 原文，其中包含测试人员的人工标注：

- 标题尾部的 ✅ 表示该用例设计得好，❌ 表示不好，⚠️ 表示漏测/存疑
- `>` 引用块是该测试人员写的批注（好/不好的原因、补充说明）
- 文档中直接补写的用例（常带「漏测补充」批注）是 AI 生成时遗漏的盲区

请阅读全文，输出一份 Markdown 经验总结，供今后 AI 为该模块生成用例时遵循，包含三节：

## 好的模式（应继续保持）
（从 ✅ 用例中归纳 3-7 条具体模式）

## 坏的反模式（必须避免）
（从 ❌ 用例及批注中归纳 3-7 条，说明为什么不好）

## 漏测教训与生成指令补充
（对比漏测补充的用例与原用例集，归纳 AI 的盲区 3-5 条，直接指导下一次用例生成）

要求：具体、可操作，结合模块业务细节，不要泛泛而谈。

用例文档原文：
{document}
"""


def _uid(value):
    from uuid import UUID

    return value if isinstance(value, UUID) else UUID(str(value))


def _state_path() -> Path:
    return case_docs_service.cases_dir() / ".evolution_state.json"


def _load_state() -> dict[str, str]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict[str, str]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


async def run_evolution(trigger: str = "manual") -> dict:
    """Run one self-evolution cycle, with process-local single-flight control."""
    if _evolution_lock.locked():
        return {"success": True, "status": "already_running", "trigger": trigger}

    async with _evolution_lock:
        started = datetime.now(UTC)
        async with async_session_factory() as db:
            run = EvolutionRun(trigger=trigger, status="running")
            db.add(run)
            await db.commit()
            run_id = str(run.id)

        try:
            return await _evolve(run_id)
        except Exception as exc:  # noqa: BLE001 — record and return as dict
            logger.exception("Evolution run %s failed", run_id)
            async with async_session_factory() as db:
                run = (await db.execute(
                    select(EvolutionRun).where(EvolutionRun.id == _uid(run_id)))).scalars().first()
                if run is not None:
                    run.status = "failed"
                    run.error = str(exc)[:2000]
                    run.finished_at = datetime.now(UTC).isoformat()
                    await db.commit()
            return {"success": False, "run_id": run_id, "status": "failed", "error": str(exc)}
        finally:
            logger.info("Evolution run %s finished in %.1fs",
                        run_id, (datetime.now(UTC) - started).total_seconds())


async def _evolve(run_id: str) -> dict:
    # --- 1. aggregate: 标注过且上次未消费的文档 ---------------------------
    state = _load_state()
    pending: list[dict] = []  # {name, content, good, bad, warn}
    for info in case_docs_service.list_docs():
        if not info["annotated"]:
            continue
        doc = case_docs_service.read_doc(info["name"])
        if doc is None:
            continue
        digest = hashlib.sha256(doc["content"].encode("utf-8")).hexdigest()
        if state.get(info["name"]) == digest:
            continue  # 上次进化后没变，不重复消费
        pending.append({**info, "content": doc["content"], "hash": digest})

    total = sum(d["good"] + d["bad"] + d["warn"] for d in pending)
    good = sum(d["good"] for d in pending)
    bad = sum(d["bad"] + d["warn"] for d in pending)

    if total < settings.evolution_min_annotations:
        async with async_session_factory() as db:
            run = (await db.execute(
                select(EvolutionRun).where(EvolutionRun.id == _uid(run_id)))).scalars().first()
            run.status = "skipped"
            run.annotations_total = total
            run.finished_at = datetime.now(UTC).isoformat()
            await db.commit()
        return {"success": True, "run_id": run_id, "status": "skipped",
                "reason": f"新增标注 {total} 条，低于阈值 {settings.evolution_min_annotations}"}

    # --- 2. reflect per document (lessons recorded; no skill write-back) --
    model = get_deepseek_model()
    all_lessons: list[str] = []
    touched: list[str] = []

    for doc in pending:
        document = doc["content"][:_MAX_DOC_CHARS]
        if len(doc["content"]) > _MAX_DOC_CHARS:
            document += "\n…（原文过长已截断）"
        prompt = REFLECT_PROMPT.format(module=doc["title"], document=document)
        response = await model.ainvoke(prompt)
        lessons = response.content if isinstance(response.content, str) else str(response.content)
        all_lessons.append(f"# 文档「{doc['name']}」\n\n{lessons}")
        touched.append(doc["name"])

    # --- 3. record run + mark consumed ------------------------------------
    async with async_session_factory() as db:
        run = (await db.execute(
            select(EvolutionRun).where(EvolutionRun.id == _uid(run_id)))).scalars().first()
        run.status = "success"
        run.annotations_total = total
        run.good_count = good
        run.bad_count = bad
        run.modules_touched = json.dumps(touched, ensure_ascii=False)
        run.lessons = "\n\n".join(all_lessons)
        run.regression_summary = (
            f"聚合 {len(pending)} 份标注文档（✅ {good} / ❌⚠️ {bad}），"
            f"经验已记录于本次运行（技能库由用户手动维护，不自动回写）。"
        )
        run.finished_at = datetime.now(UTC).isoformat()
        await db.commit()

    for doc in pending:
        state[doc["name"]] = doc["hash"]
    _save_state(state)

    return {
        "success": True, "run_id": run_id, "status": "success",
        "annotations_total": total, "good": good, "bad": bad,
        "documents": touched,
    }
