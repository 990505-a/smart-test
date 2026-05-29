"""TestCase Agent — refactored with make_agent() factory, context injection, and tool registry.

Architecture (onion middleware model):
    |-- SkillsMiddleware (outer)           -> loads 7 SKILL.md files into system prompt
    |   |-- ContextInjectionMiddleware     -> injects project_identifier, folder_id from context
    |   |   |-- DynamicModelSelection      -> detects images -> switches to GPT-4o
    |   |   |   |-- FileContextMiddleware   -> injects PDF/Image/Excel document context
    |   |   |   |-- LLM (deepseek or gpt-4o)

Design decisions:
    - make_agent() asynccontextmanager for MCP session lifecycle management
    - context_schema=TestCaseAgentContext for runtime context injection
    - ContextInjectionMiddleware auto-injects project/folder into system prompt
    - tool_registry.py for centralized tool management
    - CompositeBackend routes /skills/ to skills_backend, other paths to file_backend
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from deepagents import create_deep_agent as create_agent
from deepagents.backends import FilesystemBackend
from deepagents.backends.composite import CompositeBackend
from deepagents.middleware import SkillsMiddleware
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.pregel import Pregel
from dotenv import load_dotenv

from app.middleware.pdf_context import FileContextMiddleware
from app.middleware.dynamic_model import DynamicModelSelection
from app.agents.testcase.context import (
    ContextInjectionMiddleware,
    TestCaseAgentContext,
)
from app.agents.testcase.tool_registry import get_local_tools
from app.core.config import settings
from app.core.workspace import get_workspace_dir

load_dotenv()

# ============================================================================
# LLM configuration
# ============================================================================
llm = init_chat_model("deepseek:deepseek-chat")

# ============================================================================
# Backend configuration
# CompositeBackend routes /skills/ to skills_backend (src/app/skills/), all other
# paths to the default file_backend (workspace/default/testcase/).
# ============================================================================
_default_workspace_dir = get_workspace_dir("default", "testcase")
_default_workspace_dir.mkdir(parents=True, exist_ok=True)
file_backend = FilesystemBackend(root_dir=_default_workspace_dir, virtual_mode=True)

skills_dir = Path(__file__).parent.parent.parent / "skills"  # src/app/skills/
skills_backend = FilesystemBackend(root_dir=skills_dir, virtual_mode=True)

composite_backend = CompositeBackend(
    default=file_backend,
    routes={"/skills/": skills_backend},
)

# ============================================================================
# SkillsMiddleware configuration
# ============================================================================
skills_middleware = SkillsMiddleware(
    backend=composite_backend,
    sources=["/skills/"],
)

# ============================================================================
# System prompt — 5-stage mandatory workflow with quality red-lines
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

# 自动保存规范（Phase 10）

## 保存流程（强制原子操作）

**核心规则：`ensure_project` 和 `save_test_cases_batch` 必须成对调用。禁止只调用 `ensure_project` 不调用 `save_test_cases_batch`。**

在 Phase 5（output-formatter）完成输出后，**必须**自动调用以下流程保存到数据库：

### 步骤 1：逐模块保存（子模块项目）

对 Phase 1 识别出的每个子模块，**按以下固定顺序执行**（不可跳过任何一步）：

```
对每个模块：
  1. result = ensure_project("{项目名}-{模块名}-{时间}")
  2. 立即将该模块的测试用例传入 save_test_cases_batch(project_id=result.project_id, test_cases=[...全部用例])
  3. 确认 save_test_cases_batch 返回 success=true，记录 saved_count
  4. 如果返回 success=false，必须重试，不可跳过
```

**禁止行为：**
- 禁止连续调用多个 ensure_project 后再统一 save（会导致遗漏）
- 禁止只调用 ensure_project 就进入下一个模块
- 禁止因为用例数量多就跳过某个模块的保存

### 步骤 2：汇总保存（总项目）

所有子模块保存完成后，创建总项目并合并所有用例：
```
  1. total_result = ensure_project("{项目名}-总-{时间}")
  2. 对每个子模块，用 read_file 读取该模块的 test_cases_{模块名}.md 文件
  3. 解析文件中的每条用例，提取标题、步骤、预期结果等结构化数据
  4. 将所有子模块的完整用例合并为一个列表
  5. 调用 save_test_cases_batch(project_id=total_result.project_id, test_cases=[...全部合并用例])
```

**步骤 2 的关键要求：**
- 必须用 `read_file` 逐个读取子模块文件获取实际内容
- 步骤（steps）必须使用文件中的真实操作步骤和预期结果
- **绝对禁止**在 steps 中使用以下占位文本：
  - "参见子项目中的详细步骤"
  - "详见子模块用例"
  - "同子项目用例"
  - 任何暗示"去看别的文件"的文本
- 如果子模块文件不存在或为空，跳过该模块并在最终回复中说明

### 步骤 3：输出保存结果

对每个项目（包括总项目），输出保存结果格式（见下方 [SAVE_RESULT] 格式）。

## 保存结果格式
保存完成后，在回复中输出以下格式的汇总信息（供前端卡片渲染）：

[SAVE_RESULT]
status: success
project_id: {project_id}
project_name: {project_name}
case_count: {count}
identifiers: {id1}, {id2}, ...
[/SAVE_RESULT]

如果保存失败：
[SAVE_RESULT]
status: error
error: {error_message}
[/SAVE_RESULT]

## 数据库保存格式
将 Markdown 格式的测试用例转换为以下结构传给 `save_test_cases_batch`：
```json
{
  "project_id": "从 ensure_project 获取",
  "test_cases": [
    {
      "name": "用例标题",
      "description": "用例描述",
      "preconditions": "前置条件文本",
      "priority": "medium|high|low|critical",
      "test_case_type": "functional",
      "template": "test_case",
      "steps": [
        {"action": "具体操作", "expected_result": "预期结果"},
        ...
      ]
    }
  ],
  "folder_id": "可选，不指定则保存到项目根目录"
}
```

## 保存完成自检（强制）

保存流程结束后，必须执行以下自检：

1. **项目数验证**：子模块数 + 1个总项目 = 创建的项目总数。如果项目数不匹配，说明有遗漏。
2. **用例数验证**：总项目的用例数应等于所有子模块用例数之和。如果不等，说明合并不完整。
3. **步骤内容验证**：抽查总项目中的前3条用例，确认 steps 不包含任何占位文本（"参见"、"详见"、"同上"等）。如发现占位文本，必须重新执行步骤2的汇总保存。

自检结果随保存结果一起输出。

## Human-in-the-Loop 交互规范

以下破坏性操作**必须**先暂停并询问用户确认：
- 删除测试用例："即将删除 N 条测试用例，是否继续？"
- 覆盖已有数据："该操作将覆盖已有的 N 条用例，是否继续？"
- 执行测试脚本："即将执行测试脚本，可能影响目标系统，是否继续？"

非破坏性操作（生成、保存、查询）**自动执行**，无需确认。
"""

# ============================================================================
# Middleware instances (reusable across agent invocations)
# ============================================================================
dynamic_model_middleware = DynamicModelSelection(api_key=settings.openai_api_key)

file_middleware = FileContextMiddleware(
    original_system_prompt=SYSTEM_PROMPT,
    enable_cache=True,
    api_key=settings.openai_api_key,
)

context_middleware = ContextInjectionMiddleware()


# ============================================================================
# Agent factory — asynccontextmanager for MCP session lifecycle
# Matches classroom's make_agent() pattern:
#   - Creates MCP client inside context manager
#   - MCP tools loaded lazily per-session
#   - Resources cleaned up on exit
# ============================================================================
@asynccontextmanager
async def make_agent() -> AsyncIterator[Pregel]:
    """Create a TestCase Agent with managed MCP session lifecycle.

    Uses asynccontextmanager to ensure MCP client sessions are properly
    initialized before agent creation and cleaned up on exit.
    """
    # Initialize MCP client and load tools within the context
    mcp_tools: list = []
    try:
        client = MultiServerMCPClient(
            {
                "wiki-mcp": {
                    "transport": "stdio",
                    "command": settings.wiki_mcp_command,
                    "args": settings.wiki_mcp_args.split(),
                },
            }
        )
        mcp_tools = await load_mcp_tools(client, server_name="wiki-mcp")
    except Exception:
        pass  # Graceful degradation — agent works with just local tools

    all_tools = get_local_tools() + mcp_tools

    agent = create_agent(
        model=llm,
        tools=all_tools,
        backend=composite_backend,
        middleware=[
            skills_middleware,
            context_middleware,
            dynamic_model_middleware,
            file_middleware,
        ],
        system_prompt=SYSTEM_PROMPT,
        context_schema=TestCaseAgentContext,
    )

    yield agent


# Export for LangGraph API — the factory function itself, not an agent instance
agent = make_agent
