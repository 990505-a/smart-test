# Phase 3: RAG Knowledge System - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-12
**Phase:** 03-RAG Knowledge System
**Areas discussed:** RAG Middleware 设计, LightRAG 替换为 wiki-mcp, 前端 UI, wiki-query Skill, wiki-mcp 接入方案

---

## RAG Middleware 设计（初始讨论，后被 wiki-mcp 替换覆盖）

### 中间件位置

| Option | Description | Selected |
|--------|-------------|----------|
| 3 层洋葱 | Skills(外层) → RAG(中间) → PDF(内层) → LLM | ✓ (后被 D-16 覆盖) |
| 合并到 PDF 中间件 | RAG 开关逻辑内置在 PDFContextMiddleware | |
| RAG 在 PDF 内层 | Skills → PDF → RAG → LLM | |

**User's choice:** 3 层洋葱（后被 wiki-mcp 替换，不再需要）

### RAG-first 强制策略

| Option | Description | Selected |
|--------|-------------|----------|
| 系统提示词强制 | RAGMiddleware 添加强制拒绝指令 | ✓ (后被 D-12 覆盖) |
| 响应拦截模式 | 包装 LLM 调用，检测引用 | |
| Skill 级别强制 | requirement-analysis Skill 检查 | |

**User's choice:** 系统提示词强制（后被 wiki-mcp 替换，不再需要）

### RAG 开关传递方式

| Option | Description | Selected |
|--------|-------------|----------|
| additional_kwargs 传递 | 前端通过 additional_kwargs.rag_enabled 传递 | ✓ (后被 D-15 覆盖) |
| configurable 参数 | LangGraph configurable 参数 | |
| Agent 级别配置 | 创建 Agent 时决定 | |

**User's choice:** additional_kwargs（后被 wiki-mcp 替换，不再需要开关）

---

## LightRAG 替换为 wiki-mcp

### LightRAG 工具暴露方式

| Option | Description | Selected |
|--------|-------------|----------|
| 直接 REST API 调用 | httpx 调用 LightRAG Server | |
| MCP 协议封装 | 复用 Phase 1 MCP 基础设施 | ✓ (初始选择，后被替换) |
| Python SDK 嵌入 | 进程内调用 LightRAG | |

**User's choice:** MCP 协议封装（LightRAG → 被 wiki-mcp 完全替换）

### 知识库来源

| Option | Description | Selected |
|--------|-------------|----------|
| 对话内上传 | 复用 PDF 上传管道 | |
| 独立文档管理页面 | 新增文档管理 UI | |
| 双通道 | 对话 + 管理页面 | |
| 预建文件 | 用户在 llm-wiki 项目中管理 Markdown | ✓ |

**User's choice:** 用户指出 "我不想用rag这一套了，把rag整体换成llm-wiki" → 最终选择 wiki-mcp 预建文件模式

### 查询模式策略

| Option | Description | Selected |
|--------|-------------|----------|
| Agent 自动选择模式 | rag-query Skill 指导 Agent 根据场景选择 | ✓ |
| 默认 hybrid + 用户可覆盖 | 默认 hybrid，用户可指定其他模式 | |

**User's choice:** Agent 自动选择模式

---

## LightRAG → wiki-mcp 完全替换确认

### 替换范围

| Option | Description | Selected |
|--------|-------------|----------|
| 完全替换 | 用 wiki-mcp 替换 LightRAG，不需要 Server/Ollama/向量DB | ✓ |
| 双后端可选 | 保留 LightRAG 作为备选 | |
| 移除 Phase 3 | 不用知识库功能 | |

**User's choice:** 完全替换

### 知识库内容来源

| Option | Description | Selected |
|--------|-------------|----------|
| 预建文件（wiki-mcp 原生） | 用户手动管理 Markdown 文件 | ✓ |
| 保留上传功能 | 改用 wiki-mcp 存储 | |

**User's choice:** 预建文件

---

## 前端 UI（简化后）

### RAG 开关交互

| Option | Description | Selected |
|--------|-------------|----------|
| 顶栏 RAG 开关按钮 | AgentTabs 旁边添加开关 | ✓ (后被 D-15 覆盖) |
| 设置对话框中配置 | ConfigDialog 中添加 | |
| 输入框旁指示器 | 聊天输入框旁状态指示器 | |

**User's choice:** 顶栏开关（后被 wiki-mcp 替换，不再需要前端开关）

---

## wiki-mcp 接入方案

### 接入方式

| Option | Description | Selected |
|--------|-------------|----------|
| MCP stdio 协议 | 通过 MultiServerMCPClient 管理 | ✓ |
| 直接 @tool 包装 | 包装成 LangChain @tool 函数 | |

**User's choice:** MCP stdio 协议

### Skill 融入方式

| Option | Description | Selected |
|--------|-------------|----------|
| 融入现有 Skill | 在 requirement-analysis/test-strategy 中添加 wiki 指导 | |
| 独立 wiki-query Skill | 创建单独的 wiki-query SKILL.md | ✓ |

**User's choice:** 独立 wiki-query Skill

### 配置管理

| Option | Description | Selected |
|--------|-------------|----------|
| 环境变量配置 | .env + config.py Settings 类 | ✓ |
| 独立配置文件 | wiki-mcp-config.json | |

**User's choice:** 环境变量配置

---

## Phase 3 范围调整

| Option | Description | Selected |
|--------|-------------|----------|
| 精简版 | MCP 集成 + Skill，无前端变更 | ✓ |
| 精简版 + 前端状态 | + Wiki 连接状态显示 | |
| 完整版 | 保留原始范围但替换 LightRAG | |

**User's choice:** 精简版

### 用户补充说明
- llm-wiki 本体（https://github.com/nashsu/llm_wiki）是开源项目，用户直接使用它创建/维护 wiki 内容
- wiki-mcp 只做查询，不做写入/编辑
- "你要明确一点 已经没有rag这个东西了" — 所有 RAG 相关概念（中间件、开关、强制策略）均不适用

---

## Claude's Discretion

- wiki-query SKILL.md 的具体 Prompt 内容
- wiki-mcp 在 Agent 中的具体注册代码
- config.py 新增字段的命名

## Deferred Ideas

- 前端 Wiki 知识库状态显示
- 多知识库动态切换
- Wiki 内容创建/维护集成
- LightRAG 配置清理
