"""Web-UI Agent tools (Web-UI 自动化模块).

Thin wrappers over ``playwright_service``: the agent authors Playwright specs
and executes them through the Playwright CLI sidecar. The methodology
(selector strategy, assertion rules, artifact conventions) lives in the
``web-ui-test`` skill, which the agent reads via SkillsMiddleware.
"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from src.app.core.config import settings
from src.app.services import playwright_service


@tool
async def webui_runner_status() -> dict:
    """检查 Playwright 执行器（playwright CLI sidecar）是否可用。

    返回 CLI 版本与已安装的浏览器列表。执行任何 spec 之前先调用一次，
    确认 runner 在线；不在线时不要尝试执行，直接报告问题。
    """
    return await playwright_service.status()


@tool
async def webui_generate_spec(intent: str, target_url: str = "",
                              extra_requirements: str = "") -> dict:
    """把一段自然语言测试意图写成一份可运行的 Playwright spec（TypeScript）。

    生成结果只返回源码，不执行、不入库。适合先拿到初稿再自己修改。
    target_url 留空则用配置的默认站点。
    """
    return await playwright_service.generate_spec(
        intent=intent, target_url=target_url or None,
        extra_requirements=extra_requirements)


@tool
async def webui_run_spec(content: str, spec_file: str = "tests/spec.spec.ts",
                         target_url: str = "", device: str = "",
                         desktop: bool = False, browsers: list[str] | None = None,
                         locale: str = "", grep: str = "", timeout_s: int = 0) -> dict:
    """执行一份 Playwright spec 源码（经 playwright test CLI），返回结构化结果。

    - content: spec 源码全文（`import { test, expect } from '@playwright/test'`）。
      用相对路径 goto（如 `page.goto('/movie/')`），baseURL 由执行器注入。
    - spec_file: spec 在运行目录里的相对路径，决定 testMatch 能否命中。
    - target_url: 被测站点入口；留空用默认站点。
    - device: Playwright 设备描述符（如 `iPhone 13`、`Pixel 5`）；留空用平台默认。
    - desktop: 要看**桌面版**页面就传 true（不注入任何设备模拟）。
      注意不能用 device="" 表达桌面——那是「未指定」的意思。
    - browsers: 浏览器矩阵，如 ["chromium", "webkit"]；留空只跑 chromium。
    - locale: 站点语言（如 "zh-CN"），影响按 Accept-Language 出内容的站点。
    - grep: 只跑标题匹配的用例（由 CLI 的 --grep 执行）。
    - timeout_s: 整体超时秒数；0 表示用配置默认值。

    返回 status/exit_code/report(tests+stats)/artifacts/output：
    - 每条用例的 status、duration、error、errorLocation（失败在 spec 的第几行）、
      stdout（spec 里 console.log 的内容）、附件路径都在 report.tests 里；
    - report.tests[].attachments 给出失败截图/trace 的运行目录相对路径；
    - artifacts 是完整产物清单，html_report 有值时说明官方 HTML 报告已生成；
    - output 是人读版汇总，失败原因在里面。
    失败时不要放弃：读 output 与 errorLocation 定位原因，修正 spec 后重跑
    （重跑预算见系统提示里的说明；不要无声地反复重试同一份 spec）。
    """
    options: dict = {}
    if locale:
        options["locale"] = locale
    if browsers:
        options["browsers"] = [str(b) for b in browsers]
    run_device: str | None = None if not desktop else ""
    if device and not desktop:
        run_device = device
    return await playwright_service.run_adhoc(
        content=content, spec_file=spec_file, target_url=target_url or None,
        device=run_device, options=options or None, grep=grep or None,
        timeout_s=timeout_s or None)


@tool
async def webui_screenshot(url: str, device: str | None = None,
                           desktop: bool = False, full_page: bool = True) -> dict:
    """对任意 URL 截一张图（直接调用 `playwright screenshot` CLI）。

    用于快速核验页面是否可达、首屏渲染是否正常。返回里的 `dataUri` 是可直接
    内联显示的图片（**不是** `data_uri`——执行器返回的是驼峰），`path` 是相对
    运行目录的落盘路径。

    设备三态（与 webui_run_spec 一致）：不传 = 用平台默认设备（移动站）；
    desktop=True = 显式桌面；device="Pixel 5" = 指定设备。
    """
    resolved = "" if desktop else (device or settings.web_ui_default_device)
    return await playwright_service.screenshot(
        url, device=resolved or None, full_page=full_page)


@tool
async def webui_cli(args: list[str]) -> dict:
    """执行 playwright CLI 的**专用**子命令（白名单：install / pdf / cr）。

    这是给"没有专用工具的能力"留的口子：
    - `["pdf", "<url>", "out.pdf"]` 存 PDF；
    - `["cr", "<url>", "out.ts"]` 生成 codegen 脚本骨架。
    版本查询用 `webui_runner_status`，截图用 `webui_screenshot`，跑用例用
    `webui_run_spec`——它们返回结构化结果，比读 CLI stdout 可靠。
    """
    return await playwright_service.run_cli([str(a) for a in args])


@tool
async def webui_save_script(name: str, content: str, target_url: str = "",
                            module: str = "", description: str = "",
                            spec_file: str = "", device: str | None = None,
                            desktop: bool = False,
                            browsers: list[str] | None = None,
                            script_id: str = "") -> dict:
    """把一份 Playwright spec 入库，出现在「Web-UI 自动化」页并可一键执行。

    用例通过后再入库；入库前请确认 webui_run_spec 返回 passed。入库的脚本会以
    `status=active` 保存（表示"已验证跑通"），设备默认取平台配置。

    **改库里的用例**：传 `script_id` 就是**更新**那条（内容变了自动 version+1），
    而不是又存一份新的。流程通常是：
    `webui_list_scripts` 找 id → `webui_get_script` 读回源码 → 改 →
    `webui_run_spec` 验证 → 带 `script_id` 调本工具覆盖。

    - device / desktop：设备三态，同 webui_run_spec（不传=平台默认设备，desktop=true=桌面）。
    - browsers：浏览器矩阵（如 ["chromium", "webkit"]），留空只跑 chromium。
    - spec_file：留空用平台默认路径。
    """
    from src.app.db.database import async_session_factory

    async with async_session_factory() as db:
        try:
            script = await playwright_service.save_script(
                db, script_id=script_id or None, name=name, content=content,
                module=module or None, description=description or None,
                spec_file=spec_file or None, target_url=target_url or None,
                device=device, browsers=browsers, desktop=desktop,
                # 本工具的契约就是"已验证通过才入库"，所以显式标 active；
                # 默认 draft 是给页面表单那种"先存下来再说"的路径用的。
                status="active",
            )
        except LookupError as exc:
            return {"success": False, "error": str(exc)}
    return {"success": True, "script_id": str(script.id), "name": script.name,
            "updated": bool(script_id), "version": script.version,
            "target_url": script.target_url,
            "options": json.loads(script.options) if script.options else {}}


@tool
async def webui_get_script(script_id: str) -> dict:
    """读取已入库脚本的**完整源码**（含 options / 版本 / 修复历史摘要）。

    改库里的用例之前必须先读它——`webui_list_scripts` 只给元数据，拿不到源码。
    读完改好、用 `webui_run_spec` 验证通过，再带 `script_id` 调
    `webui_save_script` 覆盖，版本号会自动 +1。
    """
    from src.app.db.database import async_session_factory

    async with async_session_factory() as db:
        script = await playwright_service.get_script(db, script_id)
        if script is None:
            return {"success": False, "error": f"脚本不存在: {script_id}"}
        return {
            "success": True,
            "id": str(script.id), "name": script.name, "module": script.module,
            "description": script.description, "status": script.status,
            "version": script.version, "spec_file": script.spec_file,
            "target_url": script.target_url,
            "options": json.loads(script.options) if script.options else {},
            "content": script.content,
            "repair_count": len(playwright_service._load_repairs(script)),
        }


@tool
async def webui_list_scripts() -> dict:
    """列出已入库的 Web-UI 自动化脚本（id / 名称 / 状态 / 版本 / 目标站点）。

    只有元数据。要改某条用例得先 `webui_get_script <id>` 把源码读回来。
    """
    from sqlalchemy import select

    from src.app.db.database import async_session_factory
    from src.app.db.models.web_ui_script import WebUiScript

    async with async_session_factory() as db:
        rows = list((await db.execute(
            select(WebUiScript).order_by(WebUiScript.updated_at.desc()).limit(50)
        )).scalars().all())
        return {"success": True, "scripts": [
            {"id": str(r.id), "name": r.name, "module": r.module,
             "status": r.status, "version": r.version,
             "target_url": r.target_url, "spec_file": r.spec_file}
            for r in rows
        ]}


WEBUI_AGENT_TOOLS = [
    webui_runner_status,
    webui_generate_spec,
    webui_run_spec,
    webui_screenshot,
    webui_cli,
    webui_save_script,
    webui_get_script,
    webui_list_scripts,
]
