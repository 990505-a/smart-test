# Phase 7: Multi-Workspace & Infrastructure Hardening - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.

**Date:** 2026-05-14
**Phase:** 07-multi-workspace-infrastructure-hardening
**Areas discussed:** 工作空间隔离策略, 前端工作空间切换, 基础设施弹性范围

---

## 工作空间隔离策略

### 目录结构

| Option | Description | Selected |
|--------|-------------|----------|
| Agent 子目录隔离 | workspace/{space_id}/testcase/, workspace/{space_id}/web/, workspace/{space_id}/api/ | ✓ |
| 功能层隔离 | workspace/{space_id}/skills/, workspace/{space_id}/output/ | |
| 最小改动 | workspace/{space_id}/ 下直接放 web/、api/ | |

**User's choice:** Agent 子目录隔离

### X-Space-Id 传递方式

| Option | Description | Selected |
|--------|-------------|----------|
| LangGraph config | configurable 字段传递 space_id，Agent 从 config 获取 | ✓ |
| Middleware 注入 | 加一层 Middleware 提取 X-Space-Id 注入 workspace_dir | |

**User's choice:** LangGraph config

---

## 前端工作空间切换

### UI 切换方式

| Option | Description | Selected |
|--------|-------------|----------|
| 下拉菜单 | Agent Tabs 同一行加下拉菜单，localStorage 存储 | ✓ |
| URL 参数 | ?space=xxx 可分享链接 | |

**User's choice:** 下拉菜单

### 默认行为

| Option | Description | Selected |
|--------|-------------|----------|
| default 默认空间 | 无头时使用 "default" 工作空间，向后兼容 | ✓ |
| 强制选择 | 无头时返回错误 | |

**User's choice:** default 默认空间

---

## 基础设施弹性范围

### 弹性层范围

| Option | Description | Selected |
|--------|-------------|----------|
| 统一弹性层 | httpx 连接池 + 重试 + 熔断器，包裹 MCP + api_parser | ✓ |
| 仅连接池+重试 | 不做熔断器 | |
| Claude 决定 | 根据代码库实际情况决定 | |

**User's choice:** 统一弹性层

### 熔断器参数

| Option | Description | Selected |
|--------|-------------|----------|
| 中等阈值 | 5次失败熔断，30秒恢复，config.py 配置 | ✓ |
| Claude 决定 | 自行决定参数 | |

**User's choice:** 中等阈值

---

## Claude's Discretion

- graph.json configurable 字段配置
- workspace 数据迁移策略
- ResilientClient 实现方式
- MCP 客户端弹性层集成方式

## Deferred Ideas

- 用户认证 (JWT) — 后续版本
- LightRAG 集成代码 — 后续版本
- 工作空间管理 API — 后续版本
