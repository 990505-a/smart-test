"""TestCase Agent - fully wired with 3-layer middleware chain, tools, and system prompt.

Architecture (onion middleware model):
    |-- SkillsMiddleware (outer)           -> loads 7 SKILL.md files into system prompt (incl. wiki-query, test-data-generator)
    |   |-- DynamicModelSelection (middle) -> detects images -> switches to GPT-4o
    |   |   |-- FileContextMiddleware (inner) -> injects PDF/Image/Excel document context
    |   |   |-- LLM (deepseek or gpt-4o)

Design decisions:
    - D-04: 3-layer onion: Skills(outer) -> DynamicModel(middle) -> FileContext(inner)
    - D-05: Separate FilesystemBackend for skills, rooted at src/app/ (not workspace)
    - D-01/D-02: DynamicModelSelection detects image content and switches to GPT-4o
    - D-05/D-08: FileContextMiddleware (renamed from PDFContext) handles PDF/Image/Excel
    - D-06/MIDW-03: SYSTEM_PROMPT passed to FileContextMiddleware for immutable fallback pattern
    - D-01/D-03/D-14: System prompt enforces 5-stage mandatory workflow with quality red-lines
    - D-09/D-10/D-11/D-12: Unified export_test_cases tool supports Excel/CSV/JSON/Markdown
    - D-09: test-data-generator is the 7th Skill auto-discovered by SkillsMiddleware
    - D-16: No middleware changes for wiki-mcp. Tools registered via tools= parameter only.
    - D-05/D-10: wiki-mcp tools loaded via MCP client as LangChain BaseTool objects (no @tool wrapping)
"""

import asyncio
from pathlib import Path

from deepagents import create_deep_agent as create_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware import SkillsMiddleware
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv

from app.middleware.pdf_context import FileContextMiddleware
from app.middleware.dynamic_model import DynamicModelSelection
from app.agents.testcase.tools import export_test_cases
from app.core.config import settings
from app.core.workspace import get_workspace_dir
from app.mcp.mcp_client import get_mcp_client

load_dotenv()

# ============================================================================
# LLM configuration
# ============================================================================
llm = init_chat_model("deepseek:deepseek-chat")

# ============================================================================
# Backend configuration
# Default workspace for graph compilation.
# Tools that need per-request workspace resolve via get_space_id() at call time.
# ============================================================================
_default_workspace_dir = get_workspace_dir("default", "testcase")
_default_workspace_dir.mkdir(parents=True, exist_ok=True)
file_backend = FilesystemBackend(root_dir=_default_workspace_dir, virtual_mode=True)

# ============================================================================
# SkillsMiddleware configuration (D-05 outer layer, D-12/D-13)
# Per RESEARCH Open Question 2 and Pitfall 1: separate FilesystemBackend
# rooted at src/app/ with sources=["/skills/"]
# ============================================================================
app_dir = Path(__file__).parent.parent.parent  # src/app/
skills_backend = FilesystemBackend(root_dir=app_dir, virtual_mode=True)
skills_middleware = SkillsMiddleware(
    backend=skills_backend,
    sources=["/skills/"],
)

# ============================================================================
# System prompt - 5-stage mandatory workflow with quality red-lines
# Adapted from classroom reference, with future-phase features excluded.
# ============================================================================
SYSTEM_PROMPT = """\
# 角色定位

你是一位企业级资深测试架构师，服务于软件测试团队。你的核心职责是将模糊需求转化为高质量、可执行、可量化的测试资产。

你的工作严格遵循五大 Skills 体系执行。收到任何需求后，**必须按顺序激活对应 Skill**，禁止跳过。

---

# 核心工作铁律

1. 收到需求后，按以下 **强制顺序** 执行：

| 阶段 | 激活 Skill | 产出要求 | 进入下一阶段条件 |
|------|-----------|---------|----------------|
| Phase 1 | `requirement-analysis` | 需求解析报告（功能矩阵 + 风险清单 + 用例预估） | 用户确认或默认继续 |
| Phase 2 | `test-strategy` | 测试策略报告（类型选择 + 优先级 + 深度分配） | 用户确认或默认继续 |
| Phase 3 | `test-case-design` + `test-data-generator` | 逐模块测试用例（含具体测试数据） | 每模块含轻量自检 |
| Phase 4 | `quality-review` | 质量评审报告 | 综合评分 >= 75分，否则回退修改 |
| Phase 5 | `output-formatter` | 最终交付物（用户指定格式） | - |

> **红线**：未完成 Phase 1（需求分析）和 Phase 2（测试策略）前，**禁止生成具体测试用例**。

---

# 技能调用规则

## 单 Skill 激活指令

用户明确指定任务时，仅激活对应 Skill：

- "分析需求" / 收到文档 / "帮我看看这个PRD" -> 仅激活 `requirement-analysis`
- "制定策略" / "怎么测" / "测试方案" -> 仅激活 `test-strategy`
- "设计用例" / "写用例" -> 仅激活 `test-case-design`
- "生成测试数据" / "构造数据" / "准备数据" -> 仅激活 `test-data-generator`
- "评审用例" / "质量检查" -> 仅激活 `quality-review`
- "导出" / "生成Excel" -> 仅激活 `output-formatter`

## 多 Skill 组合激活指令

用户要求端到端交付时，按 Phase 顺序依次激活：

- "全流程生成" / "生成测试方案" / "从需求到用例" -> Phase 1 -> 2 -> 3 -> 4 -> 5
- "生成用例并导出Excel" -> `test-case-design` -> `quality-review` -> `output-formatter`

---

# 用例质量红线（任何情况下不可违背）

以下规则在任何 Skill 的输出中都必须强制执行：

1. **可追溯性**：用例编号格式 `TC-[项目]-[模块]-[序号]`（参考 `output-formatter` Skill），备注标注关联需求 `REQ-XXX`
2. **可验证性**：预期结果禁止"正确""成功""正常"等模糊词，必须可客观判定 Pass/Fail
3. **数据完整性**：每条用例必须提供**具体测试数据值**，禁止"有效数据""合理值"等描述性占位
4. **原子性**：一个用例只验证**一个检查点**，不堆砌验证项
5. **独立性**：前置条件必须可**独立准备**，禁止依赖其他用例的执行结果
6. **安全性**：任何涉及用户输入的功能点，必须包含至少 **1条安全测试用例**（SQL注入/XSS/越权等）
7. **边界性**：任何有取值范围的字段，必须覆盖边界值（min-1, min, min+1, max-1, max, max+1）

---

# 需求不明确时的处理规则

发现以下情况时，在分析报告中标注「需澄清问题」并列出具体问题：
- 需求描述存在歧义（A还是B？）
- 缺少关键约束条件（范围/格式/规则未定义）
- 功能点相互矛盾

**处理方式**：提出具体澄清问题，并基于**最保守假设**先行设计用例，标注"[基于假设: XXX]"。

---

# 输出行为规范

1. **每模块完成后**：自动调用 `quality-review` 轻量自检（10项快速检查），输出自检结果
2. **所有模块完成后**：输出完整汇总表 + 质量评审报告（四维度评分）
3. **格式选择**：
   - 未指定时 -> 默认 `output-formatter` 的 Markdown 详细格式
   - 用户说"导出" / "生成Excel" -> 调用 `export_test_cases` 工具生成 .xlsx 文件
   - 用户说"导出CSV" -> 调用 `export_test_cases` 工具(format="csv")
   - 用户说"导出JSON" / "Jira格式" -> 调用 `export_test_cases` 工具(format="json")
   - 用户说"导出Markdown" -> 调用 `export_test_cases` 工具(format="markdown")
4. **用例密度控制**：P0 >= 3条/模块，P1 >= 3条/核心功能，P2/P3按需补充
5. **语言一致性**：用户用中文提问，所有输出（包括用例标题、步骤、预期结果）必须使用中文

---

请始终以企业级测试工程师的专业标准执行每一个任务。
"""

# ============================================================================
# DynamicModelSelection middleware (D-01/D-04 middle layer)
# Detects image content and switches to GPT-4o multimodal model.
# Onion order: Skills(outer) -> DynamicModel(middle) -> FileContext(inner)
# ============================================================================
dynamic_model_middleware = DynamicModelSelection(api_key=settings.openai_api_key)

# ============================================================================
# FileContextMiddleware configuration (D-05 inner layer, D-08 unified file injection)
# Supports PDF, Image, and Excel file processing with session isolation.
# ============================================================================
file_middleware = FileContextMiddleware(
    original_system_prompt=SYSTEM_PROMPT,
    enable_cache=True,
    api_key=settings.openai_api_key,
)

# ============================================================================
# wiki-mcp tool loading (D-04/D-05/D-16)
# Uses asyncio.new_event_loop() to safely fetch tools at module import time.
# Per RESEARCH Pitfall 3: avoids asyncio.run() which crashes inside running
# event loops (e.g., LangGraph server). Graceful fallback if wiki-mcp unavailable.
# ============================================================================


def _load_wiki_tools() -> list:
    """Try to load wiki-mcp tools at module import time.

    Uses a new event loop to avoid conflicts with any running loop.
    Returns empty list if wiki-mcp is unavailable (not installed, config missing, etc.)
    so the agent degrades gracefully with just the Excel export tool.
    """
    try:
        loop = asyncio.new_event_loop()
        client = loop.run_until_complete(get_mcp_client())
        tools = loop.run_until_complete(client.get_tools(server_name="wiki-mcp"))
        loop.close()
        return tools
    except Exception:
        return []


wiki_tools = _load_wiki_tools()

# ============================================================================
# Agent creation (D-04 3-layer onion: Skills outer -> DynamicModel middle -> FileContext inner)
# D-16: wiki-mcp tools added via tools= parameter, no middleware change.
# Tools: export_test_cases (unified multi-format) + wiki-mcp 6 tools
# (list_wikis, list_pages, get_page, search, graph_query, reload)
# ============================================================================
agent = create_agent(
    model=llm,
    tools=[export_test_cases] + wiki_tools,
    backend=file_backend,
    middleware=[
        skills_middleware,          # D-05 outer layer: loads SKILL.md into system prompt
        dynamic_model_middleware,   # D-01/D-04 middle layer: switches model for images
        file_middleware,            # D-05 inner layer: injects file context into system prompt
    ],
    system_prompt=SYSTEM_PROMPT,
)
