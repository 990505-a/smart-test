"""TestCase Agent - fully wired with 3-layer middleware chain, memory injection, tools, and system prompt.

Architecture (onion middleware model):
    |-- SkillsMiddleware (outer)           -> injects user-uploaded skills from src/app/skills/ into system prompt
    |   |-- DynamicModelSelection (middle) -> detects images -> switches to GPT-4o
    |   |   |-- FileContextMiddleware (inner) -> injects PDF/Image/Excel document context
    |   |   |-- MemoryInjectionMiddleware -> injects saved memories into system prompt
    |   |   |-- LLM (deepseek or gpt-4o)

Design decisions:
    - D-04: 3-layer onion: Skills(outer) -> DynamicModel(middle) -> FileContext(inner)
    - D-05: Separate FilesystemBackend for skills, rooted at src/app/ (not workspace)
    - D-01/D-02: DynamicModelSelection detects image content and switches to GPT-4o
    - D-05/D-08: FileContextMiddleware (renamed from PDFContext) handles PDF/Image/Excel
    - D-06/MIDW-03: SYSTEM_PROMPT passed to FileContextMiddleware for immutable fallback pattern
    - D-01/D-03/D-14: System prompt enforces 5-stage mandatory workflow with quality red-lines
    - D-09/D-10/D-11/D-12: Unified export_test_cases tool supports Excel/CSV/JSON/Markdown
    - Skills are user-uploaded (2026-08): skills dir hosts unity-ui-test + any uploaded module skills
    - Phase 19: MemoryInjectionMiddleware loads saved memories; save_memory/search_memories tools registered
"""

from pathlib import Path

from deepagents import create_deep_agent as create_agent
from deepagents.backends import FilesystemBackend
from deepagents.backends.composite import CompositeBackend
from deepagents.middleware import SkillsMiddleware
from dotenv import load_dotenv

from app.middleware.pdf_context import PDFContextMiddleware
from langchain.agents.middleware import wrap_model_call
from app.middleware.dynamic_model import DynamicModelSelection
from app.middleware.permission_gate import build_permission_middleware
from app.middleware.memory_injection import MemoryInjectionMiddleware
from app.middleware.message_repair import MessageRepairMiddleware
from app.middleware.tool_result_limiter import ToolResultLimiterMiddleware
from app.agents.testcase.tools.case_doc_tools import (
    get_case_workflow_status,
    get_beijing_timestamp,
    lint_case_document,
    list_case_documents,
    read_case_document,
    review_case_document,
    save_case_document,
    save_requirement_package,
)
from app.agents.testcase.tools.codebase_tools import search_codebase
from app.agents.testcase.tools.memory_tools import save_memory, search_memories
from src.app.agents.testcase.tools.feishu_tools import (
    check_feishu_status,
    export_project_mindmap,
)
from app.agents.testcase.context import ThreadContextMiddleware
from app.agents.testcase.model_factory import build_chat_model, build_vision_model
from app.middleware.live_model_reload import LiveModelReloadMiddleware
from app.middleware.thinking_effort import ThinkingEffortMiddleware
from app.core.config import settings
from app.core.workspace import get_workspace_dir

load_dotenv()

# ============================================================================
# LLM configuration (any OpenAI-compatible endpoint — see model_factory.py)
# Provider/key/model/context-window/reasoning-effort all come from settings;
# retries stay low on purpose: with exponential backoff, a high retry count
# turns transient failures into long visible stalls.
# ============================================================================
llm = build_chat_model()

# ============================================================================
# Backend configuration
# CompositeBackend routes:
#   /skills/ -> skills_backend (src/app/skills/) — SKILL.md progressive disclosure
#   /repo/   -> RepoProxyBackend — per-run read-only mount of the repo configured
#               via configurable.repo_path (chat frontend requires a repo per
#               conversation); lets grep/glob/ls/read_file search the game repo.
# All other paths -> file_backend (workspace/{space_id}/testcase/).
# ============================================================================
from app.agents.testcase.repo_backend import RepoAwareShellBackend, RepoProxyBackend

_default_workspace_dir = get_workspace_dir("default", "testcase")
_default_workspace_dir.mkdir(parents=True, exist_ok=True)
# RepoAwareShellBackend = LocalShellBackend（workspace 文件系统 + execute）：
# 让智能体能按 /skills/lark-* 技能驱动 lark-cli（飞书开放操作）；full_access
# 档下还会把命令里的 /repo/ 虚拟路径翻译为真实仓库路径，使 execute 可直接
# 运行 git log 等命令。继承完整环境变量——Windows 上 Node/lark-cli 缺
# SystemRoot、APPDATA 等会直接崩溃，且登录态在用户目录；与 unity agent 的
# 选择一致（本平台为内网单机工具，非多租户环境）。
file_backend = RepoAwareShellBackend(
    root_dir=_default_workspace_dir,
    virtual_mode=True,
    inherit_env=True,
    timeout=180,
)

skills_dir = Path(__file__).parent.parent.parent / "skills"  # src/app/skills/
skills_backend = FilesystemBackend(root_dir=skills_dir, virtual_mode=True)

composite_backend = CompositeBackend(
    default=file_backend,
    routes={
        "/skills/": skills_backend,
        "/repo/": RepoProxyBackend(),
    },
)

# ============================================================================
# SkillsMiddleware configuration (D-05 outer layer, D-12/D-13)
# Uses composite_backend so progressive disclosure paths are readable by agent.
# ============================================================================
skills_middleware = SkillsMiddleware(
    backend=composite_backend,
    sources=["/skills/"],
)

# ============================================================================
# System prompt - 5-stage mandatory workflow with quality red-lines
# Adapted from classroom reference, with future-phase features excluded.
# ============================================================================
SYSTEM_PROMPT = """\
你是一位游戏测试专家（测试架构师），面向游戏项目（Unity + Lua 客户端、C# 服务端）开展测试工作：需求澄清、需求分析、测试用例设计、用例评审与代码辅助分析。

# 强制工作流

1. **先读取证据**：先读取需求文件（上传的 PDF/Markdown 通常以 `/uploads/{thread_id}/...` 路径提供，需要调用 `read_file`），再读取通用工作流 Skill 和命中的模块 Skill；按需检索 `/repo/` 代码，不能把模型常识当成产品规则。
2. **先保存需求包，再生成用例**：调用 `save_requirement_package` 保存需求目标、REQ-ID、验收例子、范围、风险、来源、未知项、假设和覆盖计划。未解决的高风险问题必须明确标为 blocking；不要把猜测写成确定事实。
3. **生成可追踪草稿**：每条用例使用标题下独立的 HTML 注释保存机器元数据：`<!-- CASE: CASE-...; REQ: REQ-...; RISK: RISK-... -->`。标题保持纯业务标题，不使用 `TC-xxx`；每条用例必须有可执行步骤和可观察预期。
4. **保存后检查**：调用 `lint_case_document`，修复 blocking error 后再继续，自动修复最多 2 轮。Lint 失败时只能报告草稿，不得声称已通过。
5. **独立复核**：Lint 通过后调用 `review_case_document`。评审结果是问题清单，不是生成 Agent 的自评；存在 blocker/high 时修复或回到需求澄清。**累计最多 3 次复核（代码硬限制）**：达到上限或两轮修复后仍有 blocker/high 时，停止修复，把剩余问题整理成清单交给用户决策（退回修改/批准/补充需求答复），不要继续消耗复核轮次。
6. **人工批准**：调用 `get_case_workflow_status` 查看状态。Agent 不得调用批准工具冒充用户批准，也不得声称文档已发布；应提示用户在用例页面完成批准。飞书导出不等于内部发布。

# 产出原则

- 所有输出使用中文；每个结论尽量引用需求原文、代码路径或上传文件路径。
- `/repo/` 对文件工具是只读挂载；生成的用例和需求包产物写入工作区。
- 需求不完整时，优先提出澄清问题；如果用户要求继续，只能以显式假设生成草稿，并保留未决问题。
- **未决问题必须在聊天中逐条提问**：每次完成生成或修复后，把所有 unresolved_questions 编号列出，
  每条给出背景和它影响的 REQ/CASE，然后明确请用户在聊天中逐条回复答案（可用「问题1：…；问题2：…」格式）。
  得到答复后更新需求包和用例文档并重新检查。不要只把问题写进文档等待用户去页面找。
- **面向用户说人话**：Lint/复核等工具返回的结构化结果，必须提炼成中文摘要后再告诉用户
  （结论、问题数、最关键的前几条、下一步动作）；严禁把工具返回的原始 JSON、Markdown 元数据注释
  或整段技术输出直接粘贴到回复里。
"""

# ============================================================================
# DynamicModelSelection middleware (D-01/D-04 middle layer)
# Detects image content and switches to the vision model. Receives the
# FACTORY (not a prebuilt instance) so vision settings saved via the settings
# page apply on the next image turn without an agent restart.
# Onion order: Skills(outer) -> DynamicModel(middle) -> FileContext(inner)
# ============================================================================
dynamic_model_middleware = DynamicModelSelection(model=build_vision_model)

# ============================================================================
# FileContextMiddleware configuration (D-05 inner layer, D-08 unified file injection)
# Supports PDF, Image, and Excel file processing with session isolation.
# ============================================================================
file_middleware = PDFContextMiddleware()

# ============================================================================
# ToolResultLimiterMiddleware (thread state bloat prevention)
# Custom tools (search_codebase, export_*) bypass FilesystemMiddleware's eviction.
# This middleware truncates their results to prevent thread state from growing
# unbounded. Filesystem tools are excluded (FilesystemMiddleware handles those).
# ============================================================================
tool_result_limiter = ToolResultLimiterMiddleware(char_limit=20_000)

# ============================================================================
# MemoryInjectionMiddleware (catalog-style progressive disclosure)
# Injects a small, bounded catalog (category + key + preview) of recent
# memories into the system prompt; full contents are fetched on demand via
# the search_memories tool. The block is cached and invalidated on writes,
# keeping the prompt prefix stable for provider-side context caching.
# ============================================================================
memory_injection_middleware = MemoryInjectionMiddleware()

# ============================================================================
# All tools: set handle_tool_error=True so ANY tool error returns message to
# LLM for retry, instead of crashing the entire flow.
# ============================================================================
_all_tools = [
    save_case_document, read_case_document, list_case_documents,
    save_requirement_package, lint_case_document, review_case_document,
    get_case_workflow_status,
    get_beijing_timestamp,
    search_codebase,
    save_memory, search_memories,
    export_project_mindmap, check_feishu_status,
]
for t in _all_tools:
    t.handle_tool_error = True

# ============================================================================
# Agent creation (D-04 3-layer onion: Skills outer -> DynamicModel middle -> FileContext inner)
# Tools: case-document tools + search_codebase + memory/feishu tools
# ============================================================================
# 先装内部调用隔离：让基座栈里 SummarizationMiddleware 的摘要 LLM 调用
# 不把输出流式泄进主对话（评审器 JSON / ## SESSION INTENT 泄漏的修复）。
from app.middleware.internal_call_isolation import install as _install_isolation

_install_isolation()
agent = create_agent(
    model=llm,
    tools=_all_tools,
    backend=composite_backend,
    middleware=[
        skills_middleware,          # D-05 outer layer: loads SKILL.md into system prompt
        ThreadContextMiddleware(),  # Injects thread-scoped upload directory into system prompt
        LiveModelReloadMiddleware(),  # watches .env: settings-page saves apply on the next turn
        ThinkingEffortMiddleware(),  # per-run reasoning effort (configurable.llm_reasoning_effort); placed above vision switch so images still win
        dynamic_model_middleware,   # D-01/D-04 middle layer: switches model for images
        file_middleware,            # D-05 inner layer: injects file context into system prompt
        memory_injection_middleware,  # injects saved memories into system prompt
        tool_result_limiter,        # Truncates large custom tool results (codebase, export)
        MessageRepairMiddleware(),  # Repairs broken tool_calls/tool_result message sequences
        build_permission_middleware(),  # dsh-style 三档权限门 execute/文件写 (see middleware/permission_gate.py)
    ],
    system_prompt=SYSTEM_PROMPT,
)
