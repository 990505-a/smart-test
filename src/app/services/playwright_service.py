"""Web-UI automation service (Web-UI 自动化模块).

The browser side of UI automation, driven by the **Playwright CLI**. The
backend has no Node runtime, so execution is delegated to the
`playwright-runner` sidecar (``tools/playwright-runner/server.mjs``) over
HTTP; it owns ``@playwright/test`` + the browsers and shells out to
``playwright test`` / ``playwright screenshot``.

AI's role mirrors the api-auto module:
1. **生成** — the LLM turns a natural-language test intent into a runnable
   Playwright spec (定位 → 操作 → 断言 → 截图存证).
2. **自修复** — when the CLI reports failures, the LLM re-reads the spec plus
   the failure text and rewrites it (version bump), re-running until it passes
   or ``WEB_UI_MAX_REPAIR`` attempts are exhausted.
3. **落库** — every run records the json-reporter stats, the failing test
   messages and the artifact manifest so results are reviewable and feed the
   eval module (测评模块) as evidence.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from src.app.core.config import settings
from src.app.core.llms import get_deepseek_model
from src.app.db.models.web_ui_script import WebUiScript

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    "passed": "passed",
    "failed": "failed",
    "timedOut": "failed",
    "interrupted": "error",
    "skipped": "skipped",
}

#: 每条用例保留的字段——前端表格、证据缩略图、agent 自修复都要用，
#: 漏一个就要么让用户看不到失败原因，要么让 agent 猜。
_TEST_FIELDS = (
    "id", "title", "fullTitle", "file", "line", "tags", "projectName",
    "status", "rawStatus", "duration", "retry", "error", "errorLocation",
    "stdout", "stderr", "annotations", "attachments",
)


def _runner_url(path: str) -> str:
    return f"{settings.playwright_runner_url.rstrip('/')}{path}"


def workspace() -> Path:
    root = Path(settings.playwright_workspace) if settings.playwright_workspace \
        else settings.workspace_dir / "default" / "web-ui-auto"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# Runner connectivity
# ---------------------------------------------------------------------------

async def status() -> dict:
    """Probe the runner and report the CLI/browser inventory."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(_runner_url("/health"))
            response.raise_for_status()
            data = response.json()
        return {
            "available": bool(data.get("available")),
            "runner_url": settings.playwright_runner_url,
            "version": data.get("version"),
            "browsers": data.get("browsers", []),
            "node": data.get("node"),
            "hint": None if data.get("available") else "runner 在线但 playwright CLI 不可用，检查镜像是否装好浏览器",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "runner_url": settings.playwright_runner_url,
            "error": f"无法连接 playwright runner: {exc}",
            "hint": "容器内应由 compose 的 playwright 服务提供；本机开发用 "
                    "`node tools/playwright-runner/server.mjs`（需先 npm i 并 playwright install chromium）",
        }


async def run_cli(args: list[str], *, timeout: float = 120.0) -> dict:
    """Raw allow-listed ``playwright <subcommand>`` passthrough."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(_runner_url("/cli"), json={"args": args, "timeoutMs": int(timeout * 1000)})
        return response.json()


async def screenshot(url: str, *, filename: str | None = None, device: str | None = None,
                     full_page: bool = False, timeout: float = 120.0) -> dict:
    """One-shot ``playwright screenshot`` — visual evidence without a spec."""
    payload: dict[str, Any] = {"url": url, "fullPage": full_page, "timeoutMs": int(timeout * 1000)}
    if filename:
        payload["filename"] = filename
    if device:
        payload["device"] = device
    async with httpx.AsyncClient(timeout=timeout + 30) as client:
        response = await client.post(_runner_url("/screenshot"), json=payload)
        return response.json()


# ---------------------------------------------------------------------------
# Spec execution
# ---------------------------------------------------------------------------

def _spec_files(script: WebUiScript) -> dict[str, str]:
    """The file map handed to the runner (one spec, path from the model)."""
    path = (script.spec_file or "tests/spec.spec.ts").strip()
    if not path.endswith((".ts", ".js", ".mjs")):
        path = f"{path}.spec.ts"
    return {path: script.content}


async def run_spec(script: WebUiScript, *, timeout_s: int | None = None,
                   grep: str | None = None, run_id: str | None = None) -> dict:
    """Drive ``playwright test`` for a script; returns the normalized result."""
    options = _script_options(script)
    browsers = options.get("browsers")
    # grep 可以由调用方传，也可以挂在 spec 对象上（AdHocSpec.grep）——
    # 只在调用方传时读，会把「按标题只跑几条」静默丢掉。
    effective_grep = grep or getattr(script, "grep", None)
    payload: dict[str, Any] = {
        "files": _spec_files(script),
        "spec": script.spec_file or "tests/spec.spec.ts",
        "options": options,
        "timeoutMs": int((timeout_s or settings.web_ui_run_timeout_s) * 1000),
        "testTimeoutMs": int(settings.web_ui_case_timeout_s * 1000),
        # 浏览器矩阵下让每个 project 有 worker 可跑，否则第二个浏览器要等第一个跑完
        "workers": max(1, len(browsers)) if isinstance(browsers, list) and browsers else 1,
        "retries": 0,
    }
    if effective_grep:
        payload["grep"] = effective_grep
    # 让后端指定运行目录名：执行记录要先把 status=running 落库，前端才能在
    # 跑的当下按 runner_run_id 找到 progress.ndjson。
    if run_id:
        payload["runId"] = run_id
    if script.target_url:
        payload["options"] = {**options, "baseURL": options.get("baseURL") or script.target_url}

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=(timeout_s or settings.web_ui_run_timeout_s) + 60) as client:
            response = await client.post(_runner_url("/run"), json=payload)
            data = response.json()
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "exit_code": -2,
            "output": f"playwright runner 调用失败: {exc}",
            "report": None,
            "artifacts": [],
            "runner_run_id": None,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }

    tests = data.get("tests") or []
    stats = data.get("stats") or {}
    if data.get("exitCode") == 0 and not data.get("tests"):
        status = "error"  # CLI成功但没有用例——通常是 testMatch 没匹配到文件
    elif data.get("exitCode") == 0 and not stats.get("expected"):
        status = "error"  # 一条都没真跑（全被 skip / only 排除）
    else:
        status = "passed" if data.get("ok") else "failed"

    output_parts = []
    if data.get("timedOut"):
        output_parts.append("!! playwright CLI 超时被杀")
    if data.get("errors"):
        output_parts.extend(str(e) for e in data["errors"])
    for test in tests:
        marker = {"passed": "✓", "skipped": "-"}.get(test.get("status"), "✗")
        location = test.get("errorLocation") or {}
        where = f" ({location.get('file')}:{location.get('line')})" if location.get("file") else ""
        output_parts.append(
            f"{marker} {test.get('fullTitle')}  [{test.get('status')}, {test.get('duration')}ms]{where}")
        if test.get("error"):
            output_parts.append(_indent(test["error"]))
    # spec 里的 console.log 是「侦察页面结构」的抓手，必须回传，否则
    # 技能文档教的探路流程拿不到任何东西。
    if data.get("stdout"):
        output_parts.append(f"--- spec stdout ---\n{data['stdout']}")
    if data.get("stderr"):
        output_parts.append(f"--- stderr ---\n{data['stderr']}")

    return {
        "status": status,
        "exit_code": data.get("exitCode"),
        "output": "\n".join(output_parts)[-30_000:],
        "report": {"stats": stats, "tests": [
            {k: t.get(k) for k in _TEST_FIELDS}
            for t in tests
        ]},
        "artifacts": data.get("artifacts") or [],
        "html_report": data.get("htmlReport"),
        "runner_run_id": data.get("runId"),
        "duration_ms": int(data.get("durationMs") or (time.monotonic() - started) * 1000),
    }


def _script_options(script: WebUiScript) -> dict:
    options = script.options
    if not options:
        return {}
    if isinstance(options, dict):
        return options
    try:
        parsed = json.loads(options)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        logger.warning("script %s has unparsable options JSON", script.id)
        return {}


@dataclass
class AdHocSpec:
    """A spec that was never persisted — what the agent runs while iterating.

    Duck-typed against {@link run_spec}'s expectations so the agent path and
    the saved-script path share one execution routine.
    """

    content: str
    spec_file: str = "tests/spec.spec.ts"
    target_url: str | None = None
    options: dict | None = None
    grep: str | None = None


async def run_adhoc(*, content: str, spec_file: str = "tests/spec.spec.ts",
                    target_url: str | None = None, device: str | None = None,
                    options: dict | None = None, grep: str | None = None,
                    timeout_s: int | None = None) -> dict:
    """Run a spec straight from source, without a DB row.

    ``device`` 三态：``None`` = 用平台默认（移动站），``""`` = **显式桌面**
    （不注入设备），其它 = 该设备描述符。空串曾经被当成"没传"而回落到
    iPhone 13，于是「想看桌面版传空串」这条被文档写明的用法实际跑的是移动端。
    """
    merged: dict[str, Any] = dict(options or {})
    if device is None:
        merged.setdefault("device", settings.web_ui_default_device)
    elif device == "":
        merged.pop("device", None)
    else:
        merged["device"] = device
    return await run_spec(
        AdHocSpec(content=content, spec_file=spec_file,
                  target_url=target_url or settings.web_ui_default_target_url,
                  options=merged, grep=grep or None),
        timeout_s=timeout_s,
    )


def _indent(text: str) -> str:
    return "\n".join(f"    {line}" for line in str(text).splitlines()[:40])


# ---------------------------------------------------------------------------
# Generation + self-repair
# ---------------------------------------------------------------------------

SPEC_PROMPT = """你是资深 Web UI 自动化测试工程师。请把下面的测试意图写成**一份可直接运行的 Playwright 测试 spec**（TypeScript，`@playwright/test`）。

硬性要求：
1. 只输出代码，用 ```typescript 围栏包裹，不要任何解释文字。
2. 第一行 import：`import { test, expect } from '@playwright/test'`。
3. **不要**自己写 `playwright.config`、不要 `page.goto` 绝对域名——用相对路径（baseURL 由运行器注入，值为 {target_url}）。
   即：`await page.goto('/movie/')` 而不是 `page.goto('https://...')`。
4. 用例名用中文，描述「测什么」；每个 `test()` 内按 定位 → 操作 → 断言 的顺序写。
5. **选择器必须稳健**：优先 `getByRole` / `getByText` / `data-*` 属性；避免 nth-child 之类的脆弱路径。
   移动站点注意用 `page.getByText(...)` 或 CSS 类名组合。
6. 断言用 `expect(...)`，必须给出**具体的期望值**（`toBeVisible()` / `toContainText('...')` / `toHaveCount(n)`），
   禁止 `expect(true).toBe(true)` 这类空断言。
7. 每个用例至少 1 处截图存证：`await page.screenshot({{ path: 'artifacts/<用例名>.png', fullPage: true }})`。
8. 超时留足：移动站首屏可能较慢，可在 test 内用 `test.setTimeout(60000)`。
9. 不依赖登录态、不写死时间戳/随机数；用例之间相互独立。

被测站点：{target_url}
{extra}

测试意图：
{intent}
"""

REPAIR_PROMPT = """你是资深 Web UI 自动化测试工程师。下面这份 Playwright spec 执行失败了，请修好它。

【原始测试意图】
{intent}

【当前 spec (v{version})】
{spec}

【playwright CLI 的失败输出】
{error}

修复原则：
1. 先判断是**选择器写错**还是**断言写错**。优先放宽/更正选择器，不要为了过而删断言。
2. 如果某条断言依赖的数据本身会变（如首页推荐位），改成断言「结构存在」而不是「内容等于某值」。
3. 保持用例条数与意图不变；确实无法自动化的用例，用 `test.fixme('原因')` 标注而不是删除。
4. 只输出修复后的完整 spec 代码（```typescript 围栏），不要解释。

被测站点：{target_url}
"""


def _extract_code(text: str) -> str:
    match = re.search(r"```(?:typescript|ts|javascript|js)?\s*\n(.*?)```", text, flags=re.S)
    return match.group(1).rstrip() + "\n" if match else text.rstrip() + "\n"


async def generate_spec(*, intent: str, target_url: str | None = None,
                        extra_requirements: str = "") -> dict:
    """Turn a test intent into the first version of a Playwright spec."""
    target = target_url or settings.web_ui_default_target_url
    prompt = SPEC_PROMPT.format(
        target_url=target, intent=intent,
        extra=extra_requirements or "- 无额外要求。",
    )
    model = get_deepseek_model()
    response = await model.ainvoke(prompt)
    text = response.content if isinstance(response.content, str) else str(response.content)
    return {"success": True, "content": _extract_code(text), "target_url": target}


async def repair_spec(script: WebUiScript, run_output: str, *, intent: str = "") -> dict:
    """Ask the LLM to fix a failing spec using the CLI's failure output."""
    model = get_deepseek_model()
    prompt = REPAIR_PROMPT.format(
        intent=intent or script.description or script.name,
        version=script.version,
        spec=script.content[:40_000],
        error=(run_output or "")[-8_000:],
        target_url=script.target_url or settings.web_ui_default_target_url,
    )
    try:
        response = await model.ainvoke(prompt)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"LLM 调用失败: {exc}"}
    text = response.content if isinstance(response.content, str) else str(response.content)
    return {"success": True, "content": _extract_code(text)}


# ---------------------------------------------------------------------------
# Scripts that already exist: run (+ optional self-repair)
# ---------------------------------------------------------------------------

async def run_script(script: WebUiScript, *, auto_repair: bool | None = None,
                     first_run_id: str | None = None) -> list[dict]:
    """Execute a script, optionally self-repairing on failure.

    Returns the list of attempts (first run + repairs) so the caller can
    persist one WebUiScriptRun row per attempt. ``first_run_id`` 让调用方
    指定第一轮的运行目录名（它需要先落一条 running 记录）。
    """
    attempts: list[dict] = []
    result = await run_spec(script, run_id=first_run_id)
    result["repair_attempt"] = 0
    attempts.append(result)
    if result["status"] == "passed":
        return attempts

    if auto_repair is False:
        allowed = 0
    else:
        allowed = settings.web_ui_max_repair
    repairs: list[dict] = _load_repairs(script)

    for attempt in range(1, allowed + 1):
        before = script.content
        fix = await repair_spec(script, result["output"])
        if not fix.get("success"):
            break
        script.content = fix["content"]
        script.version += 1
        # 记下「改前 / 改后」：自修复是静默改写用户代码的，不留下 diff
        # 用户就只能看到版本号变了而不知道变了什么。
        repairs.append({
            "version": script.version,
            "error": (result["output"] or "")[-800:],
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "before": before[:20_000],
            "after": script.content[:20_000],
        })
        result = await run_spec(script)
        result["repair_attempt"] = attempt
        attempts.append(result)
        if result["status"] == "passed":
            break

    # 历史会跟着每次失败一直长，只保留最近 10 轮
    script.repair_history = json.dumps(repairs[-10:], ensure_ascii=False)
    return attempts


def _load_repairs(script: WebUiScript) -> list[dict]:
    if not script.repair_history:
        return []
    try:
        parsed = json.loads(script.repair_history)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []
