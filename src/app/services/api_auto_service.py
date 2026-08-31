"""API automation service (接口自动化模块).

AI's role in this flow:
1. **初始化** — a Feishu API doc (fetched via lark-cli) is parsed by the LLM
   into a structured endpoint list, then the LLM generates the first version
   of a pytest automation script.
2. **自修复** — when a script run fails, the LLM re-reads the doc plus the
   failure output and rewrites the script (version bump), re-running until
   it passes or ``API_AUTO_MAX_REPAIR`` attempts are exhausted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from pathlib import Path

from sqlalchemy import select

from src.app.core.config import settings
from src.app.core.async_subprocess import run_subprocess
from src.app.core.llms import get_deepseek_model
from src.app.db.database import async_session_factory
from src.app.db.models.api_doc import ApiDocImport
from src.app.db.models.api_script import ApiScript, ApiScriptRun
from src.app.services import feishu_service

logger = logging.getLogger(__name__)

_RUN_TIMEOUT = 300.0


def _workspace() -> Path:
    root = Path(settings.api_script_workspace) if settings.api_script_workspace \
        else settings.workspace_dir / "default" / "api-auto"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# 1. Doc import
# ---------------------------------------------------------------------------

EXTRACT_PROMPT = """你是接口测试专家。下面是一份从飞书拉取的 API 接口文档。
请提取其中所有 HTTP 接口，输出**纯 JSON 数组**（不要输出其他内容），每个元素：
{{
  "name": "接口名",
  "method": "GET|POST|PUT|DELETE|PATCH",
  "path": "/api/xxx",
  "description": "功能描述",
  "headers": {{"Header-Name": "示例值"}},
  "query_params": [{{"name": "p", "type": "string", "required": true, "desc": "含义"}}],
  "body": {{"示例字段": "示例值"}},
  "response": {{"code": 0, "示例字段": "说明"}}
}}
无法确定字段时给合理示例。文档内容：

{doc}
"""


async def import_doc(doc_url: str) -> dict:
    """Fetch a Feishu doc and extract the endpoint list via LLM."""
    fetch = await feishu_service.fetch_doc(doc_url)
    if not fetch.get("success"):
        return {"success": False, "error": f"飞书文档拉取失败: {fetch.get('error')}"}
    content = fetch.get("content") or ""
    if len(content) < 50:
        return {"success": False, "error": "文档内容过短，可能未授权或为空"}

    model = get_deepseek_model()
    response = await model.ainvoke(EXTRACT_PROMPT.format(doc=content[:60000]))
    text = response.content if isinstance(response.content, str) else str(response.content)

    endpoints: list = []
    parse_error: str | None = None
    match = re.search(r"\[.*\]", text, flags=re.S)
    if match:
        try:
            endpoints = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
    else:
        parse_error = "LLM 输出中未找到 JSON 数组"

    async with async_session_factory() as db:
        row = ApiDocImport(
            doc_url=doc_url,
            title=fetch.get("title") or doc_url[-60:],
            content=content[:200_000],
            endpoints=json.dumps(endpoints, ensure_ascii=False) if endpoints else None,
            endpoint_count=str(len(endpoints)),
            status="parsed" if endpoints else "failed",
            error=parse_error,
        )
        db.add(row)
        await db.commit()
        return {
            "success": bool(endpoints),
            "import_id": str(row.id),
            "title": row.title,
            "endpoint_count": len(endpoints),
            "endpoints": endpoints,
            "error": parse_error,
        }


# ---------------------------------------------------------------------------
# 2. Initial script generation
# ---------------------------------------------------------------------------

SCRIPT_PROMPT = """你是接口自动化测试专家。基于下面的接口清单，生成一份**可直接运行的 pytest 接口自动化脚本**（python + requests），作为第一版脚本。

要求：
1. 顶部通过环境变量读取 base_url：`BASE_URL = os.environ.get("API_BASE_URL", "{base_url}")`。
2. 每个接口一个 test 函数：正向场景 + 关键断言（状态码、业务 code、关键字段存在性）。
3. 如有登录/鉴权接口，先登录并把 token 存入模块级变量供后续接口使用（fixtures 或模块级 setup）。
4. 请求超时 15s；所有断言信息用中文。
5. 不使用任何外部 mock；脚本自包含，只依赖 requests / pytest / os / json。
6. 只输出 python 代码，不要输出解释文字。

接口清单：
{endpoints}
"""

REPAIR_PROMPT = """你是接口自动化测试专家。下面这份 pytest 接口脚本执行失败了。
请**对照接口文档**分析原因并输出修复后的完整脚本（只输出 python 代码）。

【接口文档/清单】
{endpoints}

【当前脚本(v{version})】
{script}

【失败输出】
{error}

修复方向参考：接口路径/字段名变更、鉴权方式变更、响应结构变更、断言过严、依赖接口未先调用。
"""


def _extract_code(text: str) -> str:
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, flags=re.S)
    return match.group(1) if match else text


async def generate_script(
    import_id: str,
    name: str,
    *,
    base_url: str = "http://localhost:8080",
    module: str | None = None,
    project_id: str | None = None,
) -> dict:
    """Generate the first version of an automation script from an imported doc."""
    async with async_session_factory() as db:
        doc = (await db.execute(
            select(ApiDocImport).where(ApiDocImport.id == _uid(import_id)))).scalars().first()
        if doc is None or not doc.endpoints:
            return {"success": False, "error": "文档导入记录不存在或未解析出接口"}
        endpoints = json.loads(doc.endpoints)

    model = get_deepseek_model()
    prompt = SCRIPT_PROMPT.format(
        base_url=base_url,
        endpoints=json.dumps(endpoints, ensure_ascii=False, indent=1)[:40000],
    )
    response = await model.ainvoke(prompt)
    code = _extract_code(response.content if isinstance(response.content, str)
                         else str(response.content))

    async with async_session_factory() as db:
        script = ApiScript(
            name=name,
            project_id=project_id or None,
            module=module,
            doc_url=doc.doc_url,
            language="python",
            content=code,
            status="draft",
            endpoints=json.dumps(
                [f"{e.get('method', '?')} {e.get('path', '?')}" for e in endpoints[:100]],
                ensure_ascii=False),
        )
        db.add(script)
        await db.commit()
        return {"success": True, "script_id": str(script.id), "name": name,
                "endpoint_count": len(endpoints), "content": code}


# ---------------------------------------------------------------------------
# 3. Execution + self-repair
# ---------------------------------------------------------------------------

async def _write_and_run(script: ApiScript, run: ApiScriptRun, *, base_url: str | None) -> ApiScriptRun:
    workdir = _workspace() / str(script.id)
    workdir.mkdir(parents=True, exist_ok=True)
    test_file = workdir / f"test_api_v{script.version}.py"
    test_file.write_text(script.content, encoding="utf-8")

    env = None
    if base_url:
        import os
        env = {**os.environ, "API_BASE_URL": base_url}

    started = time.monotonic()
    try:
        out_bytes, _err_bytes, exit_code = await run_subprocess(
            settings.api_script_python, "-m", "pytest", str(test_file),
            "-x", "--tb=short", "-q",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(workdir), env=env,
            timeout=_RUN_TIMEOUT,
        )
        output = out_bytes.decode("utf-8", errors="replace")
    except TimeoutError:
        output = f"执行超时({_RUN_TIMEOUT}s)"
        exit_code = -1
    except OSError as exc:
        output = str(exc)
        exit_code = -2

    run.exit_code = exit_code
    run.output = output[-30_000:]
    run.duration_ms = int((time.monotonic() - started) * 1000)
    run.status = "passed" if exit_code == 0 else ("failed" if exit_code == 1 else "error")
    return run


async def run_script(script_id: str, *, base_url: str | None = None,
                     auto_repair: bool = True, triggered_by: str = "manual") -> dict:
    """Run a script; on failure, AI self-repairs against the doc (bounded)."""
    async with async_session_factory() as db:
        script = (await db.execute(
            select(ApiScript).where(ApiScript.id == _uid(script_id)))).scalars().first()
        if script is None:
            return {"success": False, "error": "脚本不存在"}
        endpoints = script.endpoints
        doc_url = script.doc_url
        run = ApiScriptRun(script_id=script.id, triggered_by=triggered_by)
        db.add(run)
        await db.flush()
        run_id = str(run.id)

        run = await _write_and_run(script, run, base_url=base_url)
        repairs: list[dict] = json.loads(script.repair_history or "[]")

        attempt = 0
        while run.status != "passed" and auto_repair and attempt < settings.api_auto_max_repair:
            attempt += 1
            repair = await _self_repair(script, run, endpoints, doc_url)
            if not repair.get("success"):
                break
            script.content = repair["content"]
            script.version += 1
            repairs.append({
                "version": script.version,
                "error": (run.output or "")[-800:],
                "fix_summary": repair.get("summary", ""),
                "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            repair_run = ApiScriptRun(
                script_id=script.id, triggered_by="self_repair", repair_attempt=attempt)
            db.add(repair_run)
            await db.flush()
            run = await _write_and_run(script, repair_run, base_url=base_url)
            run_id = str(repair_run.id)

        script.repair_history = json.dumps(repairs, ensure_ascii=False)
        script.status = "active" if run.status == "passed" else "broken"
        await db.commit()

        return {
            "success": run.status == "passed",
            "run_id": run_id,
            "status": run.status,
            "exit_code": run.exit_code,
            "repair_attempts": attempt,
            "script_version": script.version,
            "output_tail": (run.output or "")[-3000:],
        }


async def _self_repair(script: ApiScript, run: ApiScriptRun,
                       endpoints: str | None, doc_url: str | None) -> dict:
    """Ask the LLM to fix the script using the doc + failure output."""
    doc_text = endpoints or ""
    if doc_url:
        fetched = await feishu_service.fetch_doc(doc_url)
        if fetched.get("success") and fetched.get("content"):
            doc_text = f"{doc_text}\n\n【最新文档】\n{fetched['content'][:20000]}"
    if not doc_text:
        return {"success": False, "error": "无接口文档可用于自修复"}

    model = get_deepseek_model()
    prompt = REPAIR_PROMPT.format(
        endpoints=doc_text[:40000],
        version=script.version,
        script=script.content[:40000],
        error=(run.output or "")[-8000:],
    )
    try:
        response = await model.ainvoke(prompt)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"LLM 调用失败: {exc}"}
    text = response.content if isinstance(response.content, str) else str(response.content)
    return {"success": True, "content": _extract_code(text),
            "summary": f"AI 自修复 v{script.version}→v{script.version + 1}"}


def _uid(value):
    from uuid import UUID
    return value if isinstance(value, UUID) else UUID(str(value))
