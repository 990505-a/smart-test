"""TestCase Agent - fully wired with middleware chain, tools, and system prompt.

Architecture (onion middleware model):
    |-- SkillsMiddleware (outer)     -> loads 5 SKILL.md files into system prompt
    |   |-- PDFContextMiddleware (inner) -> injects PDF document context into system prompt
    |   |-- LLM

Design decisions:
    - D-05: SkillsMiddleware is outer layer (executes first), PDFContextMiddleware is inner layer
    - D-05: Separate FilesystemBackend for skills, rooted at src/app/ (not workspace)
    - D-06/MIDW-03: SYSTEM_PROMPT passed to PDFContextMiddleware for immutable fallback pattern
    - D-01/D-03/D-14: System prompt enforces 5-stage mandatory workflow with quality red-lines
    - D-09/D-10/D-11: Excel export tool registered as sole agent tool

Out of scope (future phases):
    - RAG knowledge retrieval integration (Phase 3)
    - Dynamic model selection for multimodal (Phase 4)
    - test-data-generator Skill (Phase 4)
"""

from pathlib import Path

from deepagents import create_deep_agent as create_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware import SkillsMiddleware
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv

from app.middleware.pdf_context import PDFContextMiddleware
from app.agents.testcase.tools import export_test_cases_to_excel

load_dotenv()

# ============================================================================
# LLM configuration
# ============================================================================
llm = init_chat_model("deepseek:deepseek-chat")

# ============================================================================
# Backend configuration
# ============================================================================
workspace_dir = Path(__file__).parent.parent.parent.parent.parent / "workspace"
file_backend = FilesystemBackend(root_dir=workspace_dir, virtual_mode=True)

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
| Phase 3 | `test-case-design` | 逐模块测试用例 | 每模块含轻量自检 |
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
   - 用户说"导出" / "生成Excel" -> 调用 `export_test_cases_to_excel` 工具生成 .xlsx 文件
4. **用例密度控制**：P0 >= 3条/模块，P1 >= 3条/核心功能，P2/P3按需补充
5. **语言一致性**：用户用中文提问，所有输出（包括用例标题、步骤、预期结果）必须使用中文

---

请始终以企业级测试工程师的专业标准执行每一个任务。
"""

# ============================================================================
# PDFContextMiddleware configuration (D-05 inner layer)
# D-06/MIDW-03: SYSTEM_PROMPT passed for immutable system prompt pattern
# ============================================================================
pdf_middleware = PDFContextMiddleware(
    original_system_prompt=SYSTEM_PROMPT,
    enable_cache=True,
)

# ============================================================================
# Agent creation (D-05 middleware order: Skills outer, PDF inner)
# ============================================================================
agent = create_agent(
    model=llm,
    tools=[export_test_cases_to_excel],
    backend=file_backend,
    middleware=[
        skills_middleware,      # D-05 outer layer: loads SKILL.md into system prompt
        pdf_middleware,         # D-05 inner layer: injects PDF context into system prompt
    ],
    system_prompt=SYSTEM_PROMPT,
)
