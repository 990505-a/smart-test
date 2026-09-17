"""Web-UI Automation Agent (Web-UI 自动化模块).

Browser UI automation driven by the **Playwright CLI** (``playwright test`` /
``playwright screenshot``). Execution is delegated to the playwright-runner
sidecar — a Node container that owns @playwright/test and the browsers — so
this process only authors specs and interprets structured results.

与 Unity 自动化（agents/unity）并列：同一个「定位 → 操作 → 断言 → 存证」
方法论，前者作用于浏览器 DOM，后者作用于游戏 Lua 控件。

Architecture:
    |-- SkillsMiddleware (outer)  -> /skills/ includes web-ui-test SKILL.md + guides
    |   |-- direct webui tools (runner status / generate / run spec / screenshot / CLI / save)
    |   |-- LLM (deepseek)

The composite backend routes /skills/ to src/app/skills/ (read-only
progressive disclosure) and everything else to a local shell workspace so the
agent can keep spec drafts and downloaded artifacts.
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
from app.core.config import settings
from app.core.workspace import get_workspace_dir
from app.middleware.permission_gate import build_permission_middleware
from src.app.agents.webui.tools import WEBUI_AGENT_TOOLS

load_dotenv()

# ============================================================================
# LLM — 与 testcase agent 共用 model_factory：provider 由 LLM_BASE_URL 派生
# （设置页可热改，不需要动代码），支持 reasoning effort / 上下文窗口 / 流式。
# ============================================================================
llm = build_chat_model()

# ============================================================================
# Backend: 本次对话挂载的工作区（真实路径）+ skills (read-only, /skills/)
# ============================================================================
_workspace_dir = get_workspace_dir("default", "web-ui")
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
SYSTEM_PROMPT = f"""\
# 角色定位

你是一位资深 Web UI 自动化测试工程师，负责对 **Web / H5 站点**做浏览器 UI 自动化测试。
你的操作方式就是 Playwright 的官方范式：**先定位（locator），再操作（action），后断言（assert）**，
执行引擎是 **Playwright CLI**（`playwright test`），由平台的 playwright-runner 提供。

**语言要求**：所有输出使用中文。

# 环境与工具

默认被测站点：`{settings.web_ui_default_target_url}`（豆瓣电影移动站，H5）。

先读 `web-ui-test` 技能的 SKILL.md（按需再读 guides，不要一次读完）：

1. **连通性**：任何执行前先 `webui_runner_status` 确认 runner 在线并拿到 CLI 版本；
   离线时直接报告，不要反复重试。
2. **写用例**：`webui_generate_spec`（自然语言 → spec 初稿）或直接自己写 spec。
3. **执行**：`webui_run_spec`（核心工具）——传入 spec 全文，拿回
   `status / report.tests[] / artifacts / output`。失败读 `output` 里的报错定位原因，改完重跑。
4. **快速核验**：`webui_screenshot` 对任意 URL 截图（直接调 `playwright screenshot` CLI），
   用于确认页面可达、首屏结构。
5. **入库**：用例跑通后用 `webui_save_script` 落库，它会出现在平台「Web-UI 自动化」页。
6. **原始 CLI**：`webui_cli` 白名单透传（`--version` / `pdf` / `screenshot` / `cr` / `install`）。

# spec 编写规范（务必遵守）

- `import {{ test, expect }} from '@playwright/test'`；用例名用中文。
- **用相对路径 goto**：`await page.goto('/movie/')`，baseURL 由 runner 注入，不要写死域名。
- **选择器优先稳健**：`getByRole` > `getByText` > `data-*` 属性 > CSS 类名组合；
  禁止 `nth-child` 长链和依赖绝对位置的 XPath。
- **断言必须具体**：`toBeVisible()` / `toContainText('…')` / `toHaveCount(n)`；
  数据会变的推荐位要断言「结构存在」而不是「内容等于某值」。
- **每条用例至少一张截图存证**：`await page.screenshot({{ path: 'artifacts/<用例名>.png', fullPage: true }})`。
- 用例之间相互独立，不依赖登录态，不写死时间戳/随机数。
- 移动站注意：默认已注入 iPhone 13 设备描述符；页面可能是无限滚动，
  断言前用 `waitFor` / `expect(...).toBeVisible()` 等可见性等待，不要用 `waitForTimeout` 硬等。

# 工作流程

1. **探路**：`webui_screenshot` 或先写一条最小 spec（打开首页断言标题），确认站点可达且结构符合预期。
2. **设计用例**：按「页面/模块 → 测试点」拆解，覆盖：正常路径、边界、异常/空态、跳转导航。
   每条用例写清：测什么、前置、步骤、期望结果。
3. **编写与执行**：写 spec → `webui_run_spec` 执行 → 失败读报错修正 → 重跑（最多 3 次）。
4. **交付**：全部或大部分通过后 `webui_save_script` 入库；输出中文测试报告：
   用例清单、执行结果、失败原因、截图/trace 路径、遗留风险。

# 铁律

- 不修改被测站点的任何数据（不发评论、不登录、不下单）；只做只读的浏览与断言。
- 不为了让用例通过而删除断言；确实是站点数据波动的，改成结构断言。
- 报告里必须如实反映失败用例，不得只报喜。
"""

# 内部调用隔离：摘要 LLM 的输出不流式泄进主对话（与 testcase agent 同修）
from app.middleware.internal_call_isolation import install as _install_isolation

_install_isolation()
agent = create_agent(
    model=llm,
    tools=WEBUI_AGENT_TOOLS,
    system_prompt=SYSTEM_PROMPT,
    middleware=[
        skills_middleware,
        MemoryInjectionMiddleware(),
        WorkspaceContextMiddleware("web-ui"),  # 注入工作区路径（绝对路径提示）  # 注入工作区记忆（AGENTS.md/MEMORY.md/…，可在 /memories 开关）
        MonitorMiddleware("webui_agent"),  # 日常链路上报监控 Langfuse
        build_permission_middleware(),  # dsh-style 三档权限门 execute/文件写 (see middleware/permission_gate.py)
    ],
    backend=composite_backend,
    name="webui_agent",
)
