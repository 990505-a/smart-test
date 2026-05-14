# Phase 6: API Automation Agent - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning

<domain>
## Phase Boundary

构建 API 自动化测试 Agent，支持：
- 用户导入 OpenAPI/Swagger 规范，Agent 解析后生成测试场景和 Playwright TypeScript API 测试脚本
- MASTEST 学术方法论（arXiv:2511.18038）指导测试设计
- 覆盖率计算（数据类型 + 状态码覆盖率）和语法校验
- GitNexus 代码知识图谱 MCP 集成，获取源码级接口信息
- Markdown 格式测试报告

技术基础：DeepAgents + Skills + CompositeBackend（复用 Phase 5 模式）

本阶段不实现 Human-in-the-Loop（API-08 延迟到后续）、不实现多工作空间（Phase 7）、不实现图形化报告。

**关键参考：** 课堂代码（2026-05-07）已实现完整的 API Agent，本阶段基于课堂代码适配。
</domain>

<decisions>
## Implementation Decisions

### OpenAPI 解析器设计 (API-01)
- **D-01:** LLM 解析模式（课堂模式）— OpenAPI JSON/YAML 规范作为文本注入 system prompt，让 LLM 自行解析 $ref 引用、提取参数/响应/Schema。不单独实现 Python 解析器工具
- **D-02:** api_parser 工具仍然存在（课堂参考有），但主要做格式化/结构化辅助，不做 $ref 递归解析

### MASTEST 方法论与工作流 (API-02, API-03)
- **D-03:** 强制多阶段流程 — 规格解析 → 场景设计 → 脚本生成 → 语法校验 → 覆盖率报告。每阶段有对应 Skill 指导
- **D-04:** 3 个 Skill（课堂模式），与课堂参考一致：
  1. `test-scenario-design` — 测试场景设计（正向/反向/边界/跨操作序列）
  2. `playwright-api-testing` — Playwright TypeScript 脚本生成（test.step、soft assertions）
  3. `api-test-quality` — 质量校验 + 覆盖率分析 + 语法校验
- **D-05:** Skills 目录在 workspace/api/skills/ 下，与课堂参考结构一致

### 工具与 MCP 集成 (API-04, API-05, API-06, API-07)
- **D-06:** 课堂工具集 — api_parser（OpenAPI 解析辅助）和 metrics（覆盖率计算）两个核心工具，加 Playwright MCP Server
- **D-07:** 复用 Phase 5 的 CompositeBackend 配置 — LocalShellBackend（执行命令）+ FilesystemBackend（文件操作）
- **D-08:** GitNexus MCP 集成（API-07）— 使用用户已实现的 GitNexus 代码知识图谱（D:/prpm/72codegraph/gitnexus/），它提供 MCP Server 接口，含 api_impact、tool_map、cross_ref、protocol_trace 等 18 个工具，可获取源码级接口信息
- **D-09:** GitNexus MCP 配置通过 config.py 管理（类似 wiki-mcp 的 stdio/SSE 模式）

### 报告展示与前端交互 (API-09)
- **D-10:** Markdown 报告格式 — 覆盖率数据、状态码分布、测试摘要均以 Markdown 文本输出，与 TestCase Agent 输出风格一致
- **D-11:** 无额外前端工作 — graph.json 已配置 api_agent 路由，AgentTabs 已有"API自动化" tab。无需新增前端组件

### Human-in-the-Loop (API-08)
- **D-12:** HITL 延迟到后续阶段 — 课堂参考未实现此功能，当前阶段先不做 LangGraph interrupts 机制

### Claude's Discretion
- 具体的 3 个 SKILL.md 内容从课堂参考代码复制适配
- api_parser 和 metrics 工具的具体实现细节
- GitNexus MCP 的连接配置（stdio vs SSE）
- SYSTEM_PROMPT 的具体措辞和 MASTEST 方法论指令

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 课堂参考代码（主要参考）
- `D:/test_agent/2026-05-07-ai-test-agent-system/2026-05-07-ai-test-agent-system/ai-test-agent-system/src/app/agents/api/agent.py` — API Agent 主文件，MASTEST system prompt，SkillsMiddleware 配置
- `D:/test_agent/2026-05-07-ai-test-agent-system/2026-05-07-ai-test-agent-system/ai-test-agent-system/src/app/agents/api/tools/` — api_parser.py, metrics.py, playwright_mcp_server.py 工具
- `D:/test_agent/2026-05-07-ai-test-agent-system/2026-05-07-ai-test-agent-system/ai-test-agent-system/src/workspace/api/skills/` — 3 个 API Skills 目录（含 SKILL.md）

### GitNexus 代码知识图谱
- `D:/prpm/72codegraph/gitnexus/src/mcp/tools.ts` — MCP Server 工具定义（18 个工具含 api_impact, tool_map, cross_ref, protocol_trace）
- `D:/prpm/72codegraph/gitnexus/src/mcp/server.ts` — MCP Server 启动和配置

### 现有项目代码（集成点）
- `src/app/agents/api/agent.py` — 当前 API Agent stub（需替换）
- `src/app/core/config.py` — 项目配置（需添加 GitNexus MCP 相关配置）
- `src/app/mcp/mcp_client.py` — MCP 客户端（已有 wiki-mcp、graphify 配置模式可参考）
- `src/app/agents/web/tools.py` — Phase 5 的 CompositeBackend + tools 模式（可复用）

### 技术文档
- CLAUDE.md — 技术栈决策
- `D:/test_agent/2026-05-07-ai-test-agent-system/2026-05-07-ai-test-agent-system/multi-agent system for restful api tests.pdf` — MASTEST 学术论文

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **API Agent stub** (`src/app/agents/api/agent.py`): 已有基本骨架，可直接扩展
- **CompositeBackend 模式**: Phase 5 已建立 LocalShell + Filesystem 组合模式，API Agent 可复用
- **MCP 客户端配置**: wiki-mcp 的 stdio 模式和 graphify 的 SSE 模式均已实现，GitNexus 可参考
- **SkillsMiddleware + FilesystemBackend**: Skill 加载模式已验证
- **AgentTabs + graph.json**: 前端路由和切换已就绪

### Established Patterns
- **workspace/skills/ 目录结构**: Phase 5 用 workspace/web/skills/，API 用 workspace/api/skills/
- **tools.py 分离模式**: tools.py 独立于 agent.py，方便测试
- **config.py Settings**: 所有 MCP 配置统一管理

### Integration Points
- **graph.json**: `api_agent` 路由 → `src/app/agents/api/agent.py:agent`
- **workspace/api/**: API 产物输出和 Skills 存放目录
- **GitNexus MCP**: 通过 mcp_client.py 注册，Agent 通过 tools 参数获取 GitNexus 工具

</code_context>

<specifics>
## Specific Ideas

- 课堂参考代码是主要实现来源，直接适配到现有项目
- 3 个 Skills 的 SKILL.md 从课堂参考复制
- GitNexus MCP 集成参考 wiki-mcp 的配置模式
- api_parser 和 metrics 工具从课堂参考适配

</specifics>

<deferred>
## Deferred Ideas

- **Human-in-the-Loop (API-08)**: LangGraph interrupts 机制延迟到后续阶段
- **图形化报告 (antvis)**: 使用简单 Markdown 报告代替 antvis 可视化

</deferred>

---

*Phase: 06-api-automation-agent*
*Context gathered: 2026-05-14*
