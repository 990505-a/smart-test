"""Unity Agent tools (UI 自动化模块).

Direct tools wrapping the vendored unity-auto-test skill
(LuaRemoteServer HTTP bridge). The heavy lifting (window ops, GM
commands, text asserts) is documented in the `unity-ui-test` skill
which the agent reads via SkillsMiddleware.
"""

from __future__ import annotations

from langchain_core.tools import tool

from src.app.services import unity_service


@tool
async def unity_status() -> dict:
    """检查 Unity Editor / LuaRemoteServer 连接状态与 Play Mode 状态。

    在执行任何 UI 操作前必须先调用本工具确认连接正常且游戏处于 Play Mode。
    """
    return await unity_service.status()


@tool
async def unity_exec_lua(code: str, sync: bool = False) -> dict:
    """在游戏运行时执行 Lua 代码（需要 Play Mode）。

    - sync=False: 异步协程方式（支持 yield / 网络等待），适合 UI.open 等操作
    - sync=True: 同步方式，适合纯查询
    print() 的内容会作为 output 返回。
    """
    return await unity_service.exec_lua(code, sync=sync)


@tool
async def unity_eval_lua(expression: str) -> dict:
    """求值一个 Lua 表达式并返回结果（适合读取游戏数据）。"""
    return await unity_service.exec_lua(f"print(tostring({expression}))", sync=True)


@tool
async def unity_screenshot(save_path: str | None = None) -> dict:
    """截取当前游戏画面（Game View），返回保存路径。"""
    return await unity_service.screenshot(save_path)


@tool
async def unity_list_windows() -> dict:
    """列出当前显示/隐藏的 UI 窗口。"""
    return await unity_service.shown_windows()


@tool
async def unity_run_skill_script(script_relpath: str, args: str = "") -> dict:
    """运行 unity-ui-test skill 自带的脚本（如 enter_game.py / explore_ui.py）。

    script_relpath 如 "scripts/enter_game.py"；args 为命令行参数。
    """
    import asyncio
    import sys

    from src.app.services.unity_service import skill_dir

    script_path = skill_dir() / script_relpath
    if not script_path.exists():
        return {"success": False, "error": f"脚本不存在: {script_relpath}"}
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd += args.split()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=180.0)
        return {"success": (proc.returncode or 0) == 0,
                "exit_code": proc.returncode,
                "output": out.decode("utf-8", errors="replace")[-8000:]}
    except TimeoutError:
        return {"success": False, "error": "脚本执行超时(180s)"}


UNITY_AGENT_TOOLS = [
    unity_status,
    unity_exec_lua,
    unity_eval_lua,
    unity_screenshot,
    unity_list_windows,
    unity_run_skill_script,
]
