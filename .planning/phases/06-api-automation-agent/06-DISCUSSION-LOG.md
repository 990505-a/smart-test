# Phase 6: API Automation Agent - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.

**Date:** 2026-05-14
**Phase:** 06-api-automation-agent
**Areas discussed:** OpenAPI 解析器设计, MASTEST 方法论与工作流, 工具与 MCP 集成, 报告展示与前端交互

---

## OpenAPI 解析器设计

| Option | Description | Selected |
|--------|-------------|----------|
| LLM 解析 | OpenAPI 规范作为文本注入 prompt，LLM 解析 $ref | ✓ |
| Python 解析器工具 | 用库递归解析 OpenAPI，结构化提取 | |
| 渐进式 | 先 LLM 后升级为 Python 解析器 | |

**User's choice:** LLM 解析（课堂模式）

---

## MASTEST 方法论与工作流

### 工作流结构

| Option | Description | Selected |
|--------|-------------|----------|
| 强制多阶段流程 | 规格解析→场景设计→脚本生成→语法校验→覆盖率报告 | ✓ |
| 自由流程 | Agent 自行决定流程 | |

**User's choice:** 强制多阶段流程

### Skill 组织

| Option | Description | Selected |
|--------|-------------|----------|
| 3 个 Skill | test-scenario-design, playwright-api-testing, api-test-quality | ✓ |
| 更多 Skill | 增加 openapi-parser, syntax-checker 等 | |
| Claude 决定 | 覆盖 API-01 到 API-09 | |

**User's choice:** 3 个 Skill（课堂模式）

---

## 工具与 MCP 集成

### 核心工具

| Option | Description | Selected |
|--------|-------------|----------|
| 课堂工具集 | api_parser + metrics + Playwright MCP | ✓ |
| 增加语法校验 | check_script_syntax 独立工具 | |

**User's choice:** 课堂工具集

### Human-in-the-Loop

| Option | Description | Selected |
|--------|-------------|----------|
| 延迟 HITL | 课堂未实现，后续再做 | ✓ |
| 实现 HITL | LangGraph interrupts + UI-13 | |

**User's choice:** 延迟 HITL

### Graphify/GitNexus MCP

User pointed out they have a complete code knowledge graph implementation at `D:/prpm/72codegraph/gitnexus/` — GitNexus, not Graphify. It provides an MCP Server with 18 tools including api_impact, tool_map, cross_ref, protocol_trace. Decision: integrate GitNexus MCP for API-07.

---

## 报告展示与前端交互

### 报告方式

| Option | Description | Selected |
|--------|-------------|----------|
| Markdown 报告 | 简单可靠，与 TestCase Agent 一致 | ✓ |
| 图形化报告 | antvis/G2 可视化 | |
| Markdown + 前端美化 | 简单美化不用 antvis | |

**User's choice:** Markdown 报告

### 前端工作

| Option | Description | Selected |
|--------|-------------|----------|
| 无额外前端 | AgentTabs 和 graph.json 已就绪 | ✓ |
| 增加前端组件 | 覆盖率可视化等 | |

**User's choice:** 无额外前端工作

---

## Claude's Discretion

- SKILL.md 内容从课堂参考复制
- api_parser 和 metrics 工具实现细节
- GitNexus MCP 连接配置
- SYSTEM_PROMPT 具体措辞

## Deferred Ideas

- Human-in-the-Loop (API-08) — 后续阶段
- 图形化报告 (antvis) — 用 Markdown 代替
