# Phase 7: Multi-Workspace & Infrastructure Hardening - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning

<domain>
## Phase Boundary

实现多工作空间隔离和基础设施弹性加固，使平台支持生产级可靠性：
- X-Space-Id 头传递工作空间 ID，各 Agent 数据按工作空间隔离
- 前端下拉菜单切换工作空间，默认 "default" 工作空间（向后兼容）
- 统一弹性层（httpx 连接池、指数退避重试、熔断器）包裹外部服务调用

技术基础：LangGraph configurable 机制传递 space_id，config.py 管理弹性参数

本阶段不实现用户认证（JWT 等）、不实现 LightRAG 集成代码（仅有配置）。

**关键约束：** 这是最后一个阶段。需确保向后兼容现有单工作空间行为。
</domain>

<decisions>
## Implementation Decisions

### 工作空间隔离策略 (INFRA-07, RAGS-02)
- **D-01:** Agent 子目录隔离 — workspace/{space_id}/testcase/, workspace/{space_id}/web/, workspace/{space_id}/api/。每个 Agent 的 workspace_dir 动态解析为 `settings.workspace_dir / space_id / agent_name`
- **D-02:** LangGraph configurable 传递 space_id — 前端通过 X-Space-Id 请求头传入，LangGraph 的 configurable 字段传递到 Agent，Agent 从 config 中提取 space_id 并动态设置 workspace 路径
- **D-03:** 默认工作空间 "default" — 无 X-Space-Id 头时使用 "default" 工作空间，确保向后兼容。现有 workspace/ 目录数据迁移到 workspace/default/ 下
- **D-04:** FilesystemBackend 根路径动态化 — 不再硬编码 workspace_dir，改为运行时根据 space_id 计算：`workspace_dir = settings.workspace_dir / space_id`

### 前端工作空间切换 (UI)
- **D-05:** 下拉菜单切换 — 在 Agent Tabs 同一行添加工作空间下拉菜单，列出可用工作空间。当前工作空间 ID 存储在 localStorage
- **D-06:** 切换工作空间时清空当前线程列表（threadId 重置），防止跨工作空间数据泄露

### 基础设施弹性加固 (INFRA-08)
- **D-07:** 统一弹性层 — 创建 ResilientClient 包装层，提供 httpx.AsyncClient 连接池、指数退避重试、熔断器。包裹 MCP 客户端和 api_parser 的外部调用
- **D-08:** api_parser 的 `requests` 替换为 `httpx` — 统一异步 HTTP 客户端
- **D-09:** 熔断器参数 — 5 次连续失败触发熔断，30 秒后半开状态尝试恢复。所有参数通过 config.py Settings 配置
- **D-10:** 重试策略 — 指数退避（初始 1 秒，最大 30 秒，最多 3 次重试），仅重试可恢复错误（连接超时、服务器错误 5xx）

### Claude's Discretion
- graph.json 如何配置 configurable 字段
- workspace 数据迁移策略（现有 default 数据移到 workspace/default/）
- ResilientClient 具体实现方式（装饰器、上下文管理器、或包装类）
- MCP 客户端弹性层集成方式（langchain_mcp_adapters 本身管理连接，弹性层可能在更高层包裹）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 工作空间配置
- `src/app/core/config.py` — 当前 workspace_dir 硬编码路径，需改为动态解析
- `src/app/agents/testcase/agent.py` — TestCase Agent workspace 使用模式
- `src/app/agents/web/agent.py` — Web Agent workspace 使用模式
- `src/app/agents/api/agent.py` — API Agent workspace 使用模式
- `src/app/agents/web/tools.py` — Phase 5 CompositeBackend + workspace 路径模式
- `src/app/agents/api/tools/__init__.py` — Phase 6 CompositeBackend 模式

### MCP 客户端
- `src/app/mcp/mcp_client.py` — MCP 客户端配置（wiki-mcp, graphify, gitnexus）

### 外部调用
- `src/app/agents/api/tools/api_parser.py` — 使用 requests 库（需替换为 httpx）

### 前端
- `webui/src/lib/config.ts` — 前端配置（需添加 workspace 设置）
- `webui/src/app/types/types.ts` — 前端类型定义
- `webui/src/app/hooks/useChat.ts` — Chat hook（需传递 space_id）
- `webui/src/app/components/AgentTabs.tsx` — Agent Tabs 组件（需添加工作空间下拉）
- `webui/src/app/page.tsx` — 主页面布局

### Agent 路由
- `graph.json` — Agent 路由配置（需确认 configurable 字段支持）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **CompositeBackend 模式**: Phase 5/6 已建立 LocalShell + Filesystem 组合，workspace 路径可动态化
- **config.py Settings**: 所有配置统一管理，弹性参数可加入
- **MCP 客户端**: 已有 wiki-mcp、graphify、gitnexus 注册模式
- **AgentTabs 组件**: 已有 tab 切换逻辑，可添加工作空间选择

### Established Patterns
- **settings.workspace_dir**: 所有 Agent 通过 config.py 的 workspace_dir 获取工作目录
- **Module-level backend instantiation**: Phase 5/6 在模块级别实例化 backend（需改为延迟初始化或工厂模式以支持动态 workspace）
- **localStorage 持久化**: ConfigDialog 已使用 localStorage 存储配置
- **threadId 清空**: Agent tab 切换时已实现 threadId 清空防止状态泄露

### Integration Points
- **graph.json**: 所有 Agent 路由入口
- **useChat hook**: 前端聊天请求发送点（需添加 space_id 参数）
- **MCP client**: 外部服务调用入口（需弹性包裹）
- **api_parser**: HTTP 外部调用点（需从 requests 迁移到 httpx）

</code_context>

<specifics>
## Specific Ideas

- 默认工作空间 "default" 确保现有单工作空间用户无感知迁移
- 弹性层优先包裹 MCP 客户端调用（最高频的外部交互）
- 工作空间下拉菜单可用 Select 组件（shadcn/ui），位置在 AgentTabs 同行

</specifics>

<deferred>
## Deferred Ideas

- **用户认证 (JWT)**: 不在本阶段实现，X-Space-Id 仅做隔离不做鉴权
- **LightRAG 集成代码**: config.py 有配置但无集成代码，不在本阶段添加
- **工作空间管理 API**: 创建/删除/列出工作空间的 REST API 可在后续版本添加

</deferred>

---

*Phase: 07-multi-workspace-infrastructure-hardening*
*Context gathered: 2026-05-14*
