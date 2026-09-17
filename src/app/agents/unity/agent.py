"""Unity UI Automation Agent (Unity 自动化模块).

Playwright-style UI automation for the Unity + Lua game client
(E:\\m72-publish\\m72). The agent drives the game's Lua UI controls
through the vendored `unity-ui-test` skill (HTTP LuaRemoteServer on
:16666): open/close windows, logical button clicks, TMP text asserts,
screenshots, and GM commands for test-data setup — mirroring
Playwright's locator/assert philosophy on Unity UI controls.

浏览器方向的 UI 自动化见 agents/webui（Playwright CLI），两者并列。

Architecture:
    |-- SkillsMiddleware (outer)  -> /skills/ includes unity-ui-test SKILL.md + guides
    |   |-- direct unity tools (status / exec lua / screenshot / windows / skill scripts)
    |   |-- LLM (deepseek)

The composite backend routes /skills/ to src/app/skills/ (read-only
progressive disclosure) and everything else to a local shell workspace
so the agent can write and run python test scripts.
"""

from pathlib import Path

from deepagents import create_deep_agent as create_agent
from deepagents.backends import CompositeBackend, FilesystemBackend
from deepagents.middleware import SkillsMiddleware
from dotenv import load_dotenv

from app.agents.testcase.model_factory import build_chat_model
from app.agents.workspace_backend import WorkspaceShellBackend
from app.middleware.memory_injection import MemoryInjectionMiddleware
from app.monitoring import MonitorMiddleware
from app.middleware.workspace_context import WorkspaceContextMiddleware
from app.core.workspace import get_workspace_dir
from app.middleware.permission_gate import build_permission_middleware
from src.app.agents.unity.tools import UNITY_AGENT_TOOLS

load_dotenv()

# ============================================================================
# LLM — 与 testcase agent 共用 model_factory：provider 由 LLM_BASE_URL 派生
# （设置页可热改，不需要动代码）。原先是写死 `deepseek:` provider，只认
# DEEPSEEK_API_KEY + 官方端点，换任何第三方 OpenAI 兼容端点都会 401。
# ============================================================================
llm = build_chat_model()

# ============================================================================
# Backend: 本次对话挂载的工作区（真实路径）+ skills (read-only, /skills/)
# ============================================================================
_workspace_dir = get_workspace_dir("default", "unity")
_workspace_dir.mkdir(parents=True, exist_ok=True)
# WorkspaceShellBackend：cwd = configurable.workspace_path（未挂载时用上面的默认
# 目录），真实路径语义——与 testcase/code_analyst 用同一套工作区模型。
shell_backend = WorkspaceShellBackend(_workspace_dir)

skills_dir = Path(__file__).parent.parent.parent / "skills"  # src/app/skills/
skills_backend = FilesystemBackend(root_dir=skills_dir, virtual_mode=True)

composite_backend = CompositeBackend(
    default=shell_backend,
    routes={"/skills/": skills_backend},
)

skills_middleware = SkillsMiddleware(
    backend=composite_backend,
    sources=["/skills/"],
)

# ============================================================================
# System prompt
# ============================================================================
SYSTEM_PROMPT = """\
# 角色定位

你是一位资深游戏 UI 自动化测试工程师，负责对 Unity + Lua 游戏客户端（m72 项目）进行 UI 自动化测试。
你的操作方式借鉴 Playwright 思想：**先定位（find/locator），再操作（action），后断言（assert）**，
只不过定位与操作的对象是游戏内的 Lua UI 控件（窗口 / 按钮 / TMP 文本），而不是浏览器 DOM。

**语言要求**：所有输出使用中文。

# 环境与工具

你通过 `unity-ui-test` 技能操作游戏（务必先阅读该技能的 SKILL.md，再按需阅读对应 guide，不要一次读完所有 guide）：

1. **连接检查**：任何操作前调用 `unity_status` 确认 LuaRemoteServer 可用且游戏处于 Play Mode；
   未进入 Play Mode 时提示用户在 Unity Editor 启动 Tools > LuaTestTool 并进入游戏。
2. **技能脚本**：`unity_run_skill_script` 可运行 skill 自带脚本（enter_game.py / explore_ui.py 等）。
3. **直接工具**：`unity_exec_lua`（执行 Lua）、`unity_eval_lua`（读数据）、`unity_screenshot`（截图存证）、
   `unity_list_windows`（窗口快照）。
4. **完整 API**：在工作区用 python 编写测试脚本时，按技能模板引入 ui / text / inspector / gm 四个层面：
   - UI 层（优先）：find_and_click / open_window / wait_for_window / click_close 等
   - 文本层：get_text / assert_text / assert_number / wait_for_text 等
   - 检查层：dump_tree / inspect_window / get_shown_windows
   - GM 层：构造测试数据（加道具、调等级、跨天、清任务等）

# 工作流程（Playwright 式）

1. **探索**：先用 inspector/窗口快照了解目标界面结构，确定控件名称与文本（相当于编写 locator）。
2. **编写脚本**：在工作区编写 python 测试脚本，结构为 setup（GM 构造数据）→ 操作步骤 → 断言 → 截图存证。
   - 每个关键步骤后截图，命名带步骤序号。
   - 断言优先使用 text.assert_text / assert_number（strip_tags=True）。
   - 点击优先 lua_click / find_and_click_by_text；instanceID 是临时的，必须动态查找。
3. **执行验证**：运行脚本；失败时阅读输出与截图，修复后重跑（最多 3 次）。
4. **报告**：输出中文测试报告：测试点、步骤、断言结果、截图路径、遗留问题。

# 铁律

- 操作间隔 0.5-1s，窗口操作后必须等待（wait_for_window）。
- 禁止使用 GM 命令绕过被测功能本身（GM 只用于构造前置数据）。
- clear_self() 等不可逆 GM 命令禁止使用。
- 时间平移类 GM（shift_add_time）会影响同服所有玩家，使用前必须向用户确认。
"""

# 内部调用隔离：摘要 LLM 的输出不流式泄进主对话（与 testcase agent 同修）
from app.middleware.internal_call_isolation import install as _install_isolation

_install_isolation()
agent = create_agent(
    model=llm,
    tools=UNITY_AGENT_TOOLS,
    system_prompt=SYSTEM_PROMPT,
    middleware=[
        skills_middleware,
        MemoryInjectionMiddleware(),
        WorkspaceContextMiddleware("unity"),  # 注入工作区路径（绝对路径提示）  # 注入工作区记忆（AGENTS.md/MEMORY.md/…，可在 /memories 开关）
        MonitorMiddleware("unity_agent"),  # 日常链路上报监控 Langfuse
        build_permission_middleware(),  # dsh-style 三档权限门 execute/文件写 (see middleware/permission_gate.py)
    ],
    backend=composite_backend,
    name="unity_agent",
)
