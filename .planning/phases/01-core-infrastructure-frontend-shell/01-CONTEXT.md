# Phase 1: Core Infrastructure + Frontend Shell - Context

**Gathered:** 2026-05-11
**Status:** Ready for planning

<domain>
## Phase Boundary

搭建智能测试平台的共享基础设施和前端聊天界面：
- DeepAgents 服务端（端口 2026）+ graph.json 多 Agent 路由
- LightRAG 轻量存储（NanoVectorDB + NetworkX + JSON，无 Docker）
- Ollama 本地嵌入模型（qwen3-embedding:0.6b）
- MCP 服务集成（Docling/Graphify/Playwright）
- Next.js 前端聊天界面（流式对话、文件上传、线程管理、Agent 切换、主题切换）

本阶段不实现任何 Agent 的业务逻辑（Skills/中间件/用例生成），仅搭建骨架。

</domain>

<decisions>
## Implementation Decisions

### 服务端架构
- **D-01:** 单 graph.json 多路由模式 — 三个 Agent（TestCase/Web/API）注册在同一个 graph.json 中，前端通过 Agent 名称路由
- **D-02:** 前后端通信使用 SSE 流式传输（@langchain/langgraph-sdk）
- **D-03:** DeepAgents >= 0.5.5 为主框架（create_deep_agent），LangGraph 为底层运行时

### 数据流与集成
- **D-04:** 文件上传采用 base64 嵌入消息体方式 — 前端转 base64 放入 additional_kwargs.attachments，后端中间件提取解析
- **D-05:** 外部工具通过 MCP 标准协议集成 — Docling（SSE）、Graphify（stdio）、Playwright（stdio）

### 前端界面设计
- **D-06:** Agent 切换使用顶部 Tab 标签栏 — 三个标签：用例生成 / Web自动化 / API自动化
- **D-07:** 界面布局为左右分栏 — 左侧线程列表 + 右侧聊天区域，react-resizable-panels 可调整大小
- **D-08:** 主题风格为亮色为主 + 暗色切换 — Shadcn/ui + Tailwind CSS + next-themes

### 项目工程结构
- **D-09:** 前后端同仓库 — src/ 后端（Python）+ webui/ 前端（Next.js）
- **D-10:** 开发时分别启动 — 后端 start_server.py + 前端 npm run dev，两个终端窗口

### Claude's Discretion
- 具体目录结构细节（如 src/ 下子目录命名）
- Shadcn/ui 组件选择
- 线程管理 UI 具体实现方式
- 前端状态管理库选择

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 项目规划
- `.planning/PROJECT.md` — 项目愿景、约束、技术栈
- `.planning/REQUIREMENTS.md` — Phase 1 需求（INFRA-01~08, PARS-04, UI-01~05, UI-08~12）
- `.planning/ROADMAP.md` — Phase 1 详细描述和成功标准
- `.planning/research/SUMMARY.md` — 技术栈推荐和架构决策

### 课堂参考代码
- `../2026-03-25-testing-agent-system/` — DeepAgents + Skills + 前后端同仓库的完整参考
- `../2026-04-09-testing-deep-agents-ui/` — 前端聊天界面参考（Next.js + 流式对话 + 文件上传）
- `../2026-04-11-ai-test-agent-system/` — RAG 开关 + 多 Agent 集成参考
- `../2026-05-07-ai-test-agent-system/` — 三域 Agent 架构最新参考

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- 课堂代码提供了完整的 DeepAgents Agent 创建模式（create_deep_agent + FilesystemBackend + SkillsMiddleware）
- 前端 ChatInterface.tsx / ChatMessage.tsx / ThreadList.tsx 组件可直接参考
- useChat.ts / useThreads.ts hooks 提供了流式对话和线程管理实现
- graph.json 配置模式可直接复用

### Established Patterns
- base64 文件上传 → additional_kwargs.attachments 是课堂验证的成熟模式
- SSE 流式对话通过 @langchain/langgraph-sdk 实现
- 洋葱中间件链式调用模式（Skills → Model → PDF → RAG）

### Integration Points
- graph.json 是前端（langgraph-sdk）与后端（DeepAgents Agent）的连接点
- MCP MultiServerMCPClient 是 Agent 与外部工具（Docling/Graphify/Playwright）的连接点
- LightRAG Server（端口 9621）是 RAG 知识库的 HTTP API 入口

</code_context>

<specifics>
## Specific Ideas

- 参考 2026-03-25 之后的项目结构（前后端同仓库）
- 前端参考 2026-04-09 版本的 testing-deep-agents-ui
- Tab 切换三个 Agent 的交互模式需要新增（课堂代码中没有多 Agent 切换）

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-core-infrastructure-frontend-shell*
*Context gathered: 2026-05-11*
