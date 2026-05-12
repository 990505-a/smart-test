# Phase 3: RAG Knowledge System - Context

**Gathered:** 2026-05-12
**Status:** Ready for planning

<domain>
## Phase Boundary

将 wiki-mcp 知识库查询能力集成到 TestCase Agent：
- wiki-mcp 作为 stdio MCP 服务器注册到 Agent，提供 6 个查询工具
- 创建独立 wiki-query Skill 指导 Agent 如何使用 wiki 知识
- 环境变量配置 wiki-mcp 路径和知识库目录
- Agent 在 5 阶段工作流中自动判断是否需要查询 wiki

本阶段不实现 wiki 内容创建/维护（在 llm-wiki 开源项目中完成）、不实现前端 UI 变更、不实现 LightRAG。

**重大变更：** 本阶段从 LightRAG + RAG 系统完全替换为 llm-wiki + wiki-mcp 方案。原始需求 MIDW-05（RAGMiddleware）、RAGS-01~05（LightRAG 相关）、UI-06（RAG 开关）均不再适用，由 wiki-mcp MCP 集成替代。
</domain>

<decisions>
## Implementation Decisions

### 知识库方案替换
- **D-01:** 完全替换 LightRAG 为 llm-wiki + wiki-mcp。不使用 LightRAG Server、Ollama 嵌入、向量数据库。知识库是磁盘上的 Markdown 文件，由 llm-wiki 开源项目（https://github.com/nashsu/llm_wiki）管理
- **D-02:** wiki-mcp 仅负责查询（search、get_page、list_pages、list_wikis、graph_query、reload），不负责内容创建/编辑/维护。内容维护在 llm-wiki 项目中完成
- **D-03:** 知识库内容为预建 Markdown 文件，无需文档上传功能

### MCP 集成方式
- **D-04:** wiki-mcp 通过 stdio MCP 协议注册到 TestCase Agent，使用 MultiServerMCPClient 管理（复用 Phase 1 的 MCP 基础设施模式）
- **D-05:** wiki-mcp 的 6 个工具（list_wikis、list_pages、get_page、search、graph_query、reload）通过 MCP 协议自动暴露给 Agent，无需手动包装为 @tool

### Skill 设计
- **D-06:** 创建独立的 wiki-query SKILL.md（放在 src/app/skills/wiki-query/），指导 Agent 在哪些场景下查询 wiki、如何使用 6 个工具、查询结果如何融入测试设计
- **D-07:** wiki-query Skill 不改变现有 5 阶段工作流结构，而是作为可选增强，Agent 在 requirement-analysis 和 test-strategy 阶段主动判断是否需要查询 wiki

### 配置管理
- **D-08:** wiki-mcp 路径和知识库目录通过环境变量配置（.env + config.py Settings 类扩展）
- **D-09:** wiki-mcp-config.json 配置文件指定 wiki 项目名称和路径

### 不再需要的原始需求
- **D-10:** MIDW-05（RAGMiddleware 动态注入/移除工具）→ 不需要，wiki-mcp 工具通过 MCP 协议自动可用
- **D-11:** RAGS-01（LightRAG 7 个 MCP 工具）→ 替换为 wiki-mcp 6 个工具
- **D-12:** RAGS-03（RAG-first 强制策略）→ 不需要强制策略，Agent 按需查询
- **D-13:** RAGS-04（6 种查询模式）→ wiki-mcp 有不同的查询能力（search + graph_query + get_page 等），Agent 根据场景自动选择
- **D-14:** RAGS-05（文档状态监控）→ 不需要，wiki-mcp 读取预建文件
- **D-15:** UI-06（RAG 开关）→ 不需要前端开关，wiki 工具始终可用
- **D-16:** 不需要 3 层洋葱中间件，保持 Phase 2 的 2 层（SkillsMiddleware + PDFContextMiddleware）不变

### Claude's Discretion
- wiki-query SKILL.md 的具体 Prompt 内容和查询指导
- wiki-mcp 在 Agent 创建时的具体注册代码
- config.py 中新增字段的命名

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 项目规划
- `.planning/PROJECT.md` — 项目愿景、约束、技术栈
- `.planning/REQUIREMENTS.md` — 原始需求（注意 Phase 3 需求已大幅变更，以本 CONTEXT.md 为准）
- `.planning/ROADMAP.md` — Phase 3 描述（注意原始描述基于 LightRAG，需适配 wiki-mcp）
- `.planning/phases/02-testcase-agent-mvp/02-CONTEXT.md` — Phase 2 交付物和决策
- `.planning/phases/02-testcase-agent-mvp/02-VERIFICATION.md` — Phase 2 验证结果

### wiki-mcp 参考代码
- `D:\llm-wiki\wiki-mcp\src\server.ts` — wiki-mcp MCP 服务器注册和工具列表
- `D:\llm-wiki\wiki-mcp\src\tools\search.ts` — search 工具实现（多阶段检索管道）
- `D:\llm-wiki\wiki-mcp\src\tools\graph-query.ts` — graph_query 工具实现（neighbors/stats/trace_source）
- `D:\llm-wiki\wiki-mcp\src\tools\get-page.ts` — get_page 工具实现
- `D:\llm-wiki\wiki-mcp\src\types.ts` — WikiProject/WikiPage 类型定义
- `D:\llm-wiki\wiki-mcp\package.json` — 依赖和启动命令

### llm-wiki 方法论
- `D:\llm-wiki\karpathy-llm-wiki-original.md` — LLM Wiki 核心思想（持久化知识累积 vs RAG 即时检索）

### 课堂参考代码
- `../2026-05-07-ai-test-agent-system/` — DeepAgents Agent 创建 + MCP 集成参考
- `../2026-03-25-testing-agent-system/` — DeepAgents Skills 体系参考

### 已有代码
- `src/app/mcp/mcp_client.py` — Phase 1 MCP 客户端配置（Docling SSE），需扩展添加 wiki-mcp stdio 配置
- `src/app/agents/testcase/agent.py` — Phase 2 Agent 创建代码，需添加 wiki-mcp MCP 工具
- `src/app/core/config.py` — Settings 类，需添加 wiki-mcp 配置字段
- `src/app/skills/` — 现有 5 个 Skill 目录，需添加 wiki-query/

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/app/mcp/mcp_client.py` 的 MultiServerMCPClient 配置模式 — 可直接扩展添加 wiki-mcp stdio 条目
- `src/app/agents/testcase/agent.py` 的 Agent 创建模式 — 可添加 MCP 工具注册
- `src/app/core/config.py` 的 Settings BaseSettings 模式 — 可添加 wiki-mcp 字段
- `src/app/skills/` 的 SKILL.md 模式 — 可创建 wiki-query SKILL.md

### Established Patterns
- MCP 服务器配置：SSE（Docling）和 stdio 两种传输方式，Phase 1 已配置 SSE，Phase 3 添加 stdio
- Agent 创建：create_deep_agent(model, tools, backend, middleware, system_prompt) — MCP 工具通过 get_mcp_client() 获取
- Skills 加载：SKILL.md 在 src/app/skills/目录名/SKILL.md，YAML frontmatter 的 name 必须匹配目录名

### Integration Points
- mcp_client.py → 需要添加 "wiki-mcp" stdio 配置条目
- agent.py → 需要在创建时加载 wiki-mcp 工具（通过 MCP 客户端）
- config.py → 需要添加 wiki_mcp_command、wiki_mcp_config_path 等字段
- src/app/skills/ → 需要新建 wiki-query/ 目录

</code_context>

<specifics>
## Specific Ideas

- wiki-mcp 的 search 工具支持中英文查询，对测试用例生成的中文场景友好
- graph_query 的 neighbors 模式可以帮助 Agent 发现测试相关的知识关联
- wiki-mcp 的 purpose.md 自动注入功能可以为 Agent 提供知识库的上下文背景
- Agent 在 requirement-analysis 阶段可以查询 wiki 获取项目领域知识
- Agent 在 test-strategy 阶段可以查询 wiki 获取测试标准和最佳实践

</specifics>

<deferred>
## Deferred Ideas

- 前端 Wiki 知识库状态显示 — 可在后续 Phase 实现
- 多知识库动态切换 — 当前只支持配置文件中定义的 wiki 项目
- Wiki 内容创建/维护集成 — 在 llm-wiki 项目中完成，不集成到测试平台
- LightRAG 完整移除 — 可在 Phase 7 基础设施硬化时清理 LightRAG 相关配置

</deferred>

---
*Phase: 03-rag-knowledge-system*
*Context gathered: 2026-05-12*
