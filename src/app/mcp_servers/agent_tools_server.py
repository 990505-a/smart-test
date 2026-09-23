"""Smart Test Platform agent tools MCP server (smart-test) — dsh 桥接层.

把平台 agent 工具（用例入库 / 飞书导出 / 代码图谱 / 持久记忆 / Unity 自动化 /
视觉分析）暴露为 MCP 工具，供 dsh（DeepSeek Harness）等外部宿主经 stdio 挂载。
逻辑全部复用 agents/testcase/tools、agents/unity/tools 与 services 层，本文件
只做薄封装，不复制业务逻辑。

Run standalone::

    python -m src.app.mcp_servers.agent_tools_server

dsh 挂载示例（cordis.patch.yml）::

    - insert:
        - id: mcp-smart-test
          name: '@deepseek-ai/dsh-mcp-client'
          config:
            serverName: smart-test
            transport: stdio
            command: '<venv>/Scripts/python.exe'
            args: ['-m', 'src.app.mcp_servers.agent_tools_server']
            cwd: '<platform repo root>'
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("smart-test-tools")

# ---------------------------------------------------------------------------
# 用例交付（复用 agents/testcase/tools 的 @tool 实现，经 .ainvoke 调用
# 保持单一事实来源；MCP 参数校验由 FastMCP 完成，内部再由 StructuredTool 复验）
# ---------------------------------------------------------------------------

from src.app.agents.testcase.tools import case_doc_tools, feishu_tools, memory_tools
from src.app.agents.unity import tools as unity_tools


@mcp.tool
async def get_beijing_timestamp() -> str:
    """获取当前北京时间（YYYY.MM.DD.HH.MM）。项目命名时调用一次并全程复用。"""
    return await case_doc_tools.get_beijing_timestamp.ainvoke({})


@mcp.tool
async def save_case_document(project_name: str, content: str) -> dict:
    """把整份测试用例集保存为用例 MD 文档——用例交付的主工具（覆盖式写入）。

    一个需求一份文档；续传前必须先 read_case_document 读原文再完整回传。
    MD 格式：标题层级 = 节点层级（# 根 / ##+ 分组 / 用例标题 [P0-P3] +
    「前置：」行 + 「- 操作 ⇒ 预期」缩进步骤），禁止 TC-xxx 编号。
    """
    return await case_doc_tools.save_case_document.ainvoke(
        {"project_name": project_name, "content": content})


@mcp.tool
async def read_case_document(project_name: str) -> dict:
    """读取已保存的用例 MD 文档原文（含人工标注 ✅❌ 与批注）。"""
    return await case_doc_tools.read_case_document.ainvoke(
        {"project_name": project_name})


@mcp.tool
async def list_case_documents() -> dict:
    """列出平台全部用例文档（名称 / 用例数 / 标注情况）。"""
    return await case_doc_tools.list_case_documents.ainvoke({})


@mcp.tool
async def save_requirement_package(project_name: str, package: dict) -> dict:
    """保存需求包、验收例子、风险、未知项和覆盖计划。"""
    return await case_doc_tools.save_requirement_package.ainvoke({
        "project_name": project_name,
        "package": package,
    })


@mcp.tool
async def lint_case_document(project_name: str, strict: bool = True) -> dict:
    """对用例 Markdown 执行确定性质量检查。"""
    return await case_doc_tools.lint_case_document.ainvoke({
        "project_name": project_name,
        "strict": strict,
    })


@mcp.tool
async def review_case_document(project_name: str) -> dict:
    """使用隔离上下文的评审模型检查用例文档。"""
    return await case_doc_tools.review_case_document.ainvoke({
        "project_name": project_name,
    })


@mcp.tool
async def get_case_workflow_status(project_name: str) -> dict:
    """读取用例文档当前的 Lint、复核和发布状态。"""
    return await case_doc_tools.get_case_workflow_status.ainvoke({
        "project_name": project_name,
    })


# ---------------------------------------------------------------------------
# 飞书导出
# ---------------------------------------------------------------------------

@mcp.tool
async def export_project_mindmap(
    project_name: str,
    root_text: str | None = None,
    mindnote_id: str | None = None,
) -> dict:
    """把已保存的用例 MD 文档导出为飞书思维导图（lark-cli）。

    数据直接读平台用例文档（人工标注自动剥离），与会话上下文无关。成功时
    返回 url —— 必须把该链接展示给用户。未配置 lark-cli 时返回 skipped。
    """
    return await feishu_tools.export_project_mindmap.ainvoke({
        "project_name": project_name,
        "root_text": root_text,
        "mindnote_id": mindnote_id,
    })


@mcp.tool
async def check_feishu_status() -> dict:
    """检查飞书 lark-cli 是否可用及登录状态。"""
    return await feishu_tools.check_feishu_status.ainvoke({})


# ---------------------------------------------------------------------------
# 持久记忆（跨会话）
# ---------------------------------------------------------------------------

@mcp.tool
async def save_memory(content: str, module: str = "memory", category: str = "") -> dict:
    """把一条结论追加到工作区记忆（Markdown 文件，默认 MEMORY.md）。
    用户明确要求记住、或分享了跨会话有价值的上下文时调用。"""
    return await memory_tools.save_memory.ainvoke(
        {"content": content, "module": module, "category": category})


@mcp.tool
async def search_memories(query: str, limit: int = 10) -> dict:
    """按关键词检索工作区记忆（返回文件、行号与原文片段）。"""
    return await memory_tools.search_memories.ainvoke({"query": query, "limit": limit})


# ---------------------------------------------------------------------------
# 代码图谱（与 agents/codebase/tools 逻辑一致，但 repo_path 改为显式参数——
# MCP 进程内没有 langgraph configurable 上下文，拿不到本次会话选中的仓库）
# ---------------------------------------------------------------------------

_MAX_RESULT_CHARS = 12000


def _project_name(repo_path: str) -> str:
    """项目名规则唯一实现在 codebase_service.project_name（realpath + 去首斜杠，
    对着官方 v0.11.0 实测过）；这里只转发，不再复制第二份规则。"""
    from src.app.services.codebase_service import project_name

    return project_name(repo_path)


def _clip(payload: dict) -> str:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) > _MAX_RESULT_CHARS:
        text = text[:_MAX_RESULT_CHARS] + "\n...(结果过长已截断，请用更精确的 pattern 或 file_pattern 缩小范围)"
    return text


@mcp.tool
async def search_codebase(
    pattern: str,
    repo_path: str,
    file_pattern: str = "",
    semantic: bool = False,
) -> str:
    """查询挂载仓库的代码知识图谱（需先在平台「代码图谱」页建索引）。

    图谱增强检索：文本命中 + 定义/调用者/结构排序增强，适合「在哪定义 /
    谁在调用」类问题，优于纯 grep。未建索引时会报错——此时改用原生
    grep/glob/read 直接检索仓库即可。

    Args:
        pattern: 检索模式（函数/类/关键字名）。
        repo_path: 仓库绝对路径（即当前会话的 cwd）。
        file_pattern: 限定文件 glob（如 "*.lua"、"*.cs"）。
        semantic: True 时用向量相似度检索（不知道准确标识符名时用）。
    """
    from src.app.services import codebase_service

    repo = repo_path.strip()
    if not repo:
        return "Error: 未提供 repo_path（仓库绝对路径）。"
    project = _project_name(repo)

    if semantic:
        keywords = [k for k in pattern.replace(",", " ").split() if k]
        result = await codebase_service.cbm_call(
            "search_graph",
            {"project": project, "semantic_query": keywords or [pattern],
             "limit": 20, "format": "json"},
        )
    else:
        args: dict = {"project": project, "pattern": pattern, "limit": 20, "format": "json"}
        if file_pattern:
            args["file_pattern"] = file_pattern
        result = await codebase_service.cbm_call("search_code", args)

    if not result.get("success"):
        return (f"Error: 代码图谱查询失败（仓库 {repo}）：{result.get('error')}\n"
                "可能原因：该仓库尚未建立索引。请改用 grep/glob/read 直接检索仓库，"
                "并建议用户在平台「代码图谱」页为该仓库建库。")
    return _clip(result.get("data", {}))


# ---------------------------------------------------------------------------
# Unity 自动化（复用 agents/unity/tools）—— 通用 MCP 桥，不依赖任何游戏侧代码
# ---------------------------------------------------------------------------

@mcp.tool
async def unity_status() -> dict:
    """检查 Unity 自动化桥（MCP 服务器 + Unity 编辑器）状态与 Play Mode。"""
    return await unity_tools.unity_status.ainvoke({})


@mcp.tool
async def unity_find_objects(name: str = "", path: str = "", component: str = "",
                             tag: str = "", limit: int = 50) -> dict:
    """在 Unity 场景里按名字/层级路径/组件查对象（含未激活对象）。"""
    return await unity_tools.unity_find_objects.ainvoke(
        {"name": name, "path": path, "component": component, "tag": tag, "limit": limit})


@mcp.tool
async def unity_object(target: str, component: str = "") -> dict:
    """读一个 Unity 对象的组件与字段（text/value/interactable 等）。"""
    return await unity_tools.unity_object.ainvoke({"target": target, "component": component})


@mcp.tool
async def unity_console(action: str = "get", filter_text: str = "", limit: int = 50) -> dict:
    """读/清 Unity Console（操作后必看：Unity 侧异常不会让调用失败）。"""
    return await unity_tools.unity_console.ainvoke(
        {"action": action, "filter_text": filter_text, "limit": limit})


@mcp.tool
async def unity_editor(action: str) -> dict:
    """控制 Unity 编辑器：play / pause / stop / state / refresh。"""
    return await unity_tools.unity_editor.ainvoke({"action": action})


@mcp.tool
async def unity_click(target: str) -> dict:
    """点一个 UGUI 控件（Button 优先 onClick，其次 ExecuteEvents 指针点击）。"""
    return await unity_tools.unity_click.ainvoke({"target": target})


@mcp.tool
async def unity_set_text(target: str, text: str) -> dict:
    """给带文本的控件写值（反射找可写 text 属性，TMPro / 旧版 UI 都行）。"""
    return await unity_tools.unity_set_text.ainvoke({"target": target, "text": text})


@mcp.tool
async def unity_wait_for(target: str, timeout_s: float = 10.0, state: str = "present") -> dict:
    """等对象出现（present）或消失（absent），超时返回 success=False。"""
    return await unity_tools.unity_wait_for.ainvoke(
        {"target": target, "timeout_s": timeout_s, "state": state})


@mcp.tool
async def unity_screenshot(save_path: str | None = None) -> dict:
    """截取当前游戏画面（Game View），返回保存路径。"""
    return await unity_tools.unity_screenshot.ainvoke({"save_path": save_path})


@mcp.tool
async def unity_exec_csharp(code: str) -> dict:
    """在 Unity 编辑器里执行任意 C# 语句（通用逃逸口；结果用 Debug.Log("UNITY_BRIDGE:"+json) 回传）。"""
    return await unity_tools.unity_exec_csharp.ainvoke({"code": code})


@mcp.tool
async def unity_run_tests(mode: str = "PlayMode", filter_text: str = "",
                          timeout_s: float = 300.0) -> dict:
    """跑工程里已有的 Unity Test Framework 测试（PlayMode / EditMode）。"""
    return await unity_tools.unity_run_tests.ainvoke(
        {"mode": mode, "filter_text": filter_text, "timeout_s": timeout_s})


@mcp.tool
async def unity_mcp_tools(refresh: bool = False) -> dict:
    """列出 Unity MCP 服务器提供的全部工具与入参 schema（换服务器/版本时的第一现场）。"""
    return await unity_tools.unity_mcp_tools.ainvoke({"refresh": refresh})


@mcp.tool
async def unity_mcp_call(tool: str, arguments: str = "{}") -> dict:
    """原样调用 Unity MCP 服务器上的任意工具（arguments 为 JSON 字符串）。

    参数名不叫 args：会撞 pydantic 的可变参数保留名 v__args，schema 与签名
    对不上、调用必炸（见 unity/tools.py 同名工具处的说明）。
    """
    return await unity_tools.unity_mcp_call.ainvoke({"tool": tool, "arguments": arguments})


@mcp.tool
async def unity_generate_script(intent: str, extra_requirements: str = "") -> dict:
    """把测试意图写成第一版 Unity 用例脚本（草稿，需实跑验证后入库）。"""
    return await unity_tools.unity_generate_script.ainvoke(
        {"intent": intent, "extra_requirements": extra_requirements})


@mcp.tool
async def unity_run_script(script_id: str = "", content: str = "", name: str = "") -> dict:
    """跑一份 Unity 用例脚本（同步；0=通过 1=断言失败 其余=环境问题）。"""
    return await unity_tools.unity_run_script.ainvoke(
        {"script_id": script_id, "content": content, "name": name})


@mcp.tool
async def unity_save_script(name: str, content: str, module: str = "",
                            description: str = "", script_id: str = "") -> dict:
    """把跑通过的 Unity 用例入库（带 script_id 即更新那条，版本号自动 +1）。"""
    return await unity_tools.unity_save_script.ainvoke(
        {"name": name, "content": content, "module": module,
         "description": description, "script_id": script_id})


@mcp.tool
async def unity_get_script(script_id: str) -> dict:
    """读取已入库 Unity 用例的完整源码。"""
    return await unity_tools.unity_get_script.ainvoke({"script_id": script_id})


@mcp.tool
async def unity_list_scripts() -> dict:
    """列出已入库的 Unity 用例（id / 名称 / 状态 / 版本）。"""
    return await unity_tools.unity_list_scripts.ainvoke({})


# ---------------------------------------------------------------------------
# 视觉分析（modlens 式视觉桥）：dsh 宿主模型无视觉能力时，由本工具直连平台主模型
# （.env 的 LLM_*，回退 DEEPSEEK_*）去读图。平台只保留一套模型配置，所以这里不再
# 有独立的视觉端点——主模型本身支持读图就用得上，不支持则会由服务端报错。
# 典型场景：unity_screenshot 后的界面核验、UI 走查、截图取证。
# ---------------------------------------------------------------------------
def _image_model_config() -> tuple[str, str, str]:
    """返回 (model, base_url, api_key)：平台主模型的配置。"""
    model = (os.environ.get("LLM_MODEL") or "").strip() or \
        (os.environ.get("DEEPSEEK_MODEL") or "").strip()
    base_url = (os.environ.get("LLM_BASE_URL") or "").strip()
    api_key = (
        (os.environ.get("LLM_API_KEY") or "").strip()
        or (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    )
    return model, base_url, api_key


# OpenCode Go 网关要求 x-opencode-session 头（见 model_factory._go_session_headers）。
_GO_SESSION_ID = uuid.uuid4().hex


@mcp.tool
async def analyze_image(image_path: str, prompt: str = "") -> dict:
    """调用平台主模型分析一张本地图片（截图核验 / UI 走查 / 界面取证）。

    典型用法：unity_screenshot 截图后，把返回的保存路径传给本工具，
    prompt 写明要核验的内容（如"检查活动入口按钮是否可见、有无报错弹窗"），
    再根据描述判断断言是否通过。

    需要 .env 的主模型配置（LLM_MODEL / LLM_BASE_URL / LLM_API_KEY，回退
    DEEPSEEK_*），且该模型要支持读图；否则由服务端返回错误。
    """
    model, base_url, api_key = _image_model_config()
    if not model:
        return {
            "success": False,
            "skipped": True,
            "error": "未配置主模型（.env 的 LLM_MODEL），无法分析图片。",
        }
    if not api_key:
        return {"success": False, "skipped": True,
                "error": "主模型缺少 API Key（LLM_API_KEY / DEEPSEEK_API_KEY）。"}

    path = Path(image_path)
    if not path.is_file():
        return {"success": False, "error": f"图片不存在: {image_path}"}
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode()

    if base_url:
        url = base_url.rstrip("/") + "/chat/completions"
    else:
        url = "https://api.deepseek.com/chat/completions"

    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text",
                 "text": prompt or "以游戏测试工程师视角详细描述这张截图：可见的界面元素、"
                                   "文案、状态、异常（报错/遮挡/错位），以及任何值得注意的细节。"},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }],
        "max_tokens": 2000,
    }
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        if "opencode.ai" in base_url.lower():
            headers["x-opencode-session"] = _GO_SESSION_ID
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        description = data["choices"][0]["message"]["content"]
        return {"success": True, "model": model, "description": description}
    except httpx.HTTPStatusError as e:
        return {"success": False,
                "error": f"视觉端点返回 {e.response.status_code}: {e.response.text[:500]}"}
    except Exception as e:
        return {"success": False, "error": f"视觉分析失败: {e}"}


# ---------------------------------------------------------------------------
# 记忆（Markdown 记忆模块；平台原生工具同名能力的 MCP 面）
# ---------------------------------------------------------------------------

@mcp.tool
async def memory_save(content: str, module: str = "memory", category: str = "") -> dict:
    """把一条信息写进工作区记忆（Markdown 文件，跨会话生效）。
    用户明确要求"记住"或分享了应长期保留的上下文时调用。
    """
    return await memory_tools.save_memory.ainvoke(
        {"content": content, "module": module, "category": category})


@mcp.tool
async def memory_search(query: str, limit: int = 8) -> dict:
    """检索工作区记忆（AGENTS.md/MEMORY.md/USER.md/failures.md…），返回命中片段。"""
    return await memory_tools.search_memories.ainvoke({"query": query, "limit": limit})


@mcp.tool
async def memory_status() -> dict:
    """查记忆模块状态（模块数/启用数/字符数/目录）。"""
    from src.app.services import memory_service

    return {"success": True, "data": memory_service.status()}


# ---------------------------------------------------------------------------
# API 自动化（复用 services/api_auto_service：飞书文档→pytest 生成→执行→AI 自修复）
# ---------------------------------------------------------------------------

@mcp.tool
async def api_doc_import(doc_url: str) -> dict:
    """从飞书接口文档导入并解析接口清单（LLM 提取 name/method/path/参数/响应）。

    需 lark-cli 已登录。返回 import_id 供生成脚本。长耗时（LLM 解析）。
    """
    from src.app.services import api_auto_service

    return await api_auto_service.import_doc(doc_url)


@mcp.tool
async def api_docs_list() -> dict:
    """查已导入的接口文档列表（含接口数与状态）。"""
    from sqlalchemy import select

    from src.app.db.database import async_session_factory
    from src.app.db.models.api_doc import ApiDocImport

    async with async_session_factory() as db:
        rows = list((await db.execute(
            select(ApiDocImport).order_by(ApiDocImport.created_at.desc()).limit(50)
        )).scalars().all())
    return {"success": True, "data": [{
        "id": str(r.id), "doc_url": r.doc_url, "title": r.title,
        "endpoint_count": r.endpoint_count, "status": r.status, "error": r.error,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}


@mcp.tool
async def api_script_generate(
    import_id: str,
    name: str,
    base_url: str = "http://localhost:8080",
    module: str | None = None,
) -> dict:
    """AI 生成第一版接口自动化脚本（pytest + requests：每接口一个 test 函数、
    中文断言、BASE_URL 走环境变量）。基于已导入文档的 import_id。
    长耗时（LLM 生成）。
    """
    from src.app.services import api_auto_service

    return await api_auto_service.generate_script(
        import_id, name, base_url=base_url, module=module)


@mcp.tool
async def api_scripts_list() -> dict:
    """查接口自动化脚本列表（状态/版本/接口数/修复历史）。"""
    import json as _json

    from sqlalchemy import select

    from src.app.db.database import async_session_factory
    from src.app.db.models.api_script import ApiScript

    async with async_session_factory() as db:
        rows = list((await db.execute(
            select(ApiScript).order_by(ApiScript.updated_at.desc()).limit(100)
        )).scalars().all())
    return {"success": True, "data": [{
        "id": str(s.id), "name": s.name, "module": s.module, "doc_url": s.doc_url,
        "version": s.version, "status": s.status,
        "endpoints": _json.loads(s.endpoints) if s.endpoints else [],
        "repair_history": _json.loads(s.repair_history) if s.repair_history else [],
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    } for s in rows]}


@mcp.tool
async def api_script_run(
    script_id: str,
    base_url: str | None = None,
    auto_repair: bool = True,
) -> dict:
    """执行接口自动化脚本（pytest；失败时 AI 自修复重跑，最多 3 轮）。

    超长耗时操作（pytest 300s × 若干轮 + LLM 修复），宿主超时需 ≥10 分钟。
    返回 run_id/status/exit_code/repair_attempts/output_tail。
    """
    from src.app.services import api_auto_service

    return await api_auto_service.run_script(
        script_id, base_url=base_url, auto_repair=auto_repair,
        triggered_by="dsh-mcp")


@mcp.tool
async def api_script_runs(script_id: str, limit: int = 30) -> dict:
    """查脚本执行历史（状态/exit_code/输出/修复次数）。"""
    from uuid import UUID as _UUID

    from sqlalchemy import select

    from src.app.db.database import async_session_factory
    from src.app.db.models.api_script import ApiScriptRun

    sid = _UUID(str(script_id))
    async with async_session_factory() as db:
        rows = list((await db.execute(
            select(ApiScriptRun).where(ApiScriptRun.script_id == sid)
            .order_by(ApiScriptRun.created_at.desc()).limit(limit)
        )).scalars().all())
    return {"success": True, "data": [{
        "id": str(r.id), "status": r.status, "exit_code": r.exit_code,
        "output": r.output, "duration_ms": r.duration_ms,
        "repair_attempt": r.repair_attempt,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}


if __name__ == "__main__":
    mcp.run()
