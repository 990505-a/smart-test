"""MCP 冒烟测试：以 dsh 同款方式（stdio 子进程）验证 agent_tools_server。

用法（项目根目录）::

    .venv/Scripts/python.exe dsh/mcp_smoke.py

验证内容：
  1. stdio 握手（initialize）成功
  2. tools/list 返回预期工具集（2026-08-28 MD 重构后 + evolution/api-auto 扩展）
  3. 真实调用 get_beijing_timestamp / list_case_documents / search_memories /
     evolution_schedule（只读，不触发 LLM）
  4. 失败路径 fail-open（analyze_image 未配置视觉模型时返回 skipped 而非崩溃）
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED_TOOLS = {
    # 用例文档（MD 重构后）
    "get_beijing_timestamp", "save_case_document", "read_case_document",
    "list_case_documents", "save_requirement_package", "lint_case_document",
    "review_case_document", "get_case_workflow_status",
    # 飞书
    "export_project_mindmap", "check_feishu_status",
    # 记忆 / 代码图谱
    "save_memory", "search_memories", "search_codebase",
    # Unity
    "unity_status", "unity_exec_lua", "unity_eval_lua", "unity_screenshot",
    "unity_list_windows", "unity_run_skill_script",
    # 视觉
    "analyze_image",
    # 自进化（dsh-suite 扩展）
    "evolution_trigger", "evolution_runs", "evolution_schedule",
    # API 自动化（dsh-suite 扩展）
    "api_doc_import", "api_docs_list", "api_script_generate",
    "api_scripts_list", "api_script_run", "api_script_runs",
}


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.app.mcp_servers.agent_tools_server"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = {t.name for t in listed.tools}
            missing = EXPECTED_TOOLS - names
            print(f"[tools/list] {len(names)} tools")
            if missing:
                print(f"[FAIL] missing: {missing}")
                return 1
            print(f"[OK] 全部 {len(EXPECTED_TOOLS)} 个预期工具在列")

            # 真实调用（只读路径，不触发 LLM / 不写库）
            ts = await session.call_tool("get_beijing_timestamp", {})
            print(f"[call] get_beijing_timestamp -> {ts.content[0].text}")

            docs = await session.call_tool("list_case_documents", {})
            print(f"[call] list_case_documents -> {docs.content[0].text[:120]}")

            mem = await session.call_tool("search_memories", {"query": "偏好"})
            print(f"[call] search_memories -> {mem.content[0].text[:80]}...")

            sched = await session.call_tool("evolution_schedule", {})
            print(f"[call] evolution_schedule -> {sched.content[0].text[:120]}")

            runs = await session.call_tool("api_docs_list", {})
            print(f"[call] api_docs_list -> {runs.content[0].text[:80]}")

            # 失败路径：视觉未配置/文件不存在时应 fail-open
            img = await session.call_tool(
                "analyze_image", {"image_path": "nonexistent.png"})
            body = img.content[0].text
            assert "success" in body.lower(), body
            print(f"[call] analyze_image(fail-open) -> {body[:100]}")

    print("\n冒烟测试全部通过 ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
