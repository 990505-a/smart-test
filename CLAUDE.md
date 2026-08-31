<!-- GSD:project-start source:PROJECT.md -->
## Project

**智能测试平台 (Smart Test Platform)**

基于 Agent + RAG + MCP + Skills + Tools 技术栈的企业级智能测试平台，覆盖测试用例自动生成、Web UI 自动化测试、RESTful API 自动化测试三大领域。平台通过 DeepAgents 框架整合多种专业技能（Skills），借助 RAG 知识库提供上下文增强，通过 MCP 协议标准化工具集成，为测试工程师提供从需求分析到测试报告的全流程 AI 辅助能力。

**Core Value:** 通过 AI 智能体 + 企业级 Skills 技能体系，自动生成高质量、可执行、可追溯的测试资产（用例/脚本/报告），大幅提升测试效率和覆盖率。

### Constraints

- **技术栈**: Python 3.13 后端 + Next.js 16 前端，与课堂代码保持一致
- **Agent 框架**: DeepAgents >= 0.4.12 作为主要框架（支持 Skills/中间件/MCP/Backend）
- **LLM**: DeepSeek Chat（文本）+ 豆包 Vision（多模态），需配置 API Key
- **RAG**: LightRAG + RAGAnything + Ollama（qwen3-embedding:0.6b），需本地部署
- **数据库**: PostgreSQL 16 + Neo4j + Redis + Milvus（通过 Docker 部署）
- **MCP 服务**: Docling（文档解析）、Graphify（代码图谱）、Playwright（自动化）
- **端口约定**: LangGraph API 2026, 前端 3000, LightRAG Server 9621
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Core Framework (Backend)
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | 3.13.13 | Runtime | Bugfix stage, stable through Oct 2029. Matches classroom code constraint. 3.14.4 is available but 3.13 is the safer choice for compatibility with all dependencies. | HIGH |
| DeepAgents | >= 0.5.5 | Agent framework | LangChain-maintained, built on LangGraph. Provides Skills, Middleware, MCP integration, Backend server out of the box. Latest release Apr 30, 2026. Requires Python >= 3.11. | HIGH |
| LangGraph | >= 0.4.x | Agent orchestration | State machines for multi-step agent workflows (5-stage test case pipeline, 7-Agent web automation pipeline). DeepAgents is built on this. | HIGH |
| LangChain Core | >= 0.3.x | LLM abstraction | Model interfaces, prompt templates, output parsers. Required by DeepAgents. | HIGH |
### Core Framework (Frontend)
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Next.js | 15.4.4 | Frontend framework | Latest stable (released May 10, 2026). Ships with React 19. **IMPORTANT: PROJECT.md references "Next.js 16" which does not exist. Use 15.4.4.** | HIGH |
| React | 19.x | UI library | Ships with Next.js 15. Server Components, Actions, streaming support built in. | HIGH |
| @langchain/langgraph-sdk | >= 0.0.31 | Agent API client | Streaming chat via SSE/WebSocket. Has React/Vue/Svelte/Angular adapters. ThreadStream API for real-time message flow. | HIGH |
| Tailwind CSS | 4.x | Styling | Utility-first CSS. v4 introduces CSS-native configuration, better performance. | HIGH |
| Shadcn/ui | latest | Component library | Copy-paste components built on Radix UI. Full control over code, no vendor lock-in. | HIGH |
| nuqs | latest | URL state management | Type-safe URL query string state. Persist UI state in URL for shareable links. | MEDIUM |
### Database
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| PostgreSQL | 16 | Primary relational store | LightRAG supports PostgreSQL as all-in-one storage (vector + graph + KV). Production-grade, well-supported. | HIGH |
| Neo4j | 5.x | Knowledge graph | Optional for advanced graph queries. LightRAG can use Neo4j for enhanced graph capabilities. Deploy if graph-heavy workloads expected. | MEDIUM |
| Redis | 7.x | Cache + session store | API rate limiting, session management, LangGraph state caching. Lightweight, fast. | HIGH |
| Milvus | 2.x | Vector database | Dedicated vector search for embeddings. Can be replaced by pgvector if PostgreSQL-only deployment desired. | MEDIUM |
| Ollama | latest | Local LLM + embedding host | Runs qwen3-embedding:0.6b locally for RAG embeddings. No API costs for embedding calls. | HIGH |
### LLM Providers
| Technology | Purpose | Why | Confidence |
|------------|---------|-----|------------|
| DeepSeek Chat | Text generation | Cost-effective text LLM. Used for text-based test case generation, strategy planning, code analysis. API compatible with OpenAI SDK. | HIGH |
| Doubao Vision (豆包) | Multimodal analysis | Image/PDF visual understanding. Used when ENABLE_PDF_MULTIMODAL is on for scanning documents, screenshots, diagrams. | HIGH |
### Infrastructure
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Docker + Docker Compose | latest | Service orchestration | PostgreSQL, Neo4j, Redis, Milvus, Ollama all containerized. Single `docker-compose up` for full stack. | HIGH |
| LangGraph API Server | >= 0.2.x | Agent backend | Serves DeepAgents/LangGraph agents via REST + streaming. Runs on port 2024 by convention (PROJECT.md says 2026). | HIGH |
| LightRAG Server | latest | RAG API | WebUI + REST API on port 9621. Built-in knowledge graph visualization. 6 query modes. | HIGH |
### Supporting Libraries (Backend)
| Library | Purpose | When to Use | Confidence |
|---------|---------|-------------|------------|
| PyMuPDF4LLM | PDF to text/markdown conversion | When processing uploaded PDF files for test case generation. Faster and more accurate than PyPDF2. | HIGH |
| python-docx | Word document parsing | When .docx files are uploaded as test requirements documents. | HIGH |
| openpyxl | Excel read/write | Reading uploaded Excel test data, writing exported test cases in Excel format. | MEDIUM |
| FastAPI | REST API endpoints | LangGraph API handles agent routes. Use FastAPI only for custom endpoints (file upload, health checks, RAG management). | HIGH |
| PyJWT | JWT token handling | Multi-tenant authentication. Workspace + JWT + API Key triple isolation. | HIGH |
| httpx | Async HTTP client | Calling MCP servers (Docling, Graphify, Playwright). Async-native, better than requests for concurrent calls. | HIGH |
| qwen3-embedding:0.6b | Text embeddings | Run via Ollama for local embedding generation. Sufficient quality for RAG, zero API cost. | MEDIUM |
### Supporting Libraries (Frontend)
| Library | Purpose | When to Use | Confidence |
|---------|---------|-------------|------------|
| @tanstack/react-query | Server state management | Fetching threads, messages, agent status. Cache invalidation, optimistic updates. | HIGH |
| lucide-react | Icons | Lightweight icon set that pairs well with Shadcn/ui. | HIGH |
| react-dropzone | File upload | Drag-and-drop + paste file upload for PDF/image/Excel. | HIGH |
| antvis (G2 or S2) | Data visualization | Test report charts, coverage dashboards, quality metrics visualization. | MEDIUM |
| sonner | Toast notifications | Non-blocking notifications for async operations (file upload progress, agent status). | HIGH |
### MCP Servers
| Server | Purpose | Why | Confidence |
|--------|---------|-----|------------|
| Docling | Document parsing | Converts PDF/Word/PPT/HTML to structured markdown. MCP protocol integration. Maintained by IBM. | HIGH |
| Graphify | Code knowledge graph | Extracts API endpoints, data models, call graphs from source code. Enables component-aware testing. | MEDIUM |
| Playwright | Browser automation | CLI mode preferred over MCP mode for token efficiency. Single `execute` tool reduces LLM token consumption. | HIGH |
## Alternatives Considered
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Agent Framework | DeepAgents | CrewAI | CrewAI lacks Skills system and onion middleware. Less suitable for structured multi-stage workflows. |
| Agent Framework | DeepAgents | AutoGen | Microsoft's framework is more research-oriented. No Skills concept, weaker MCP integration. |
| Agent Framework | DeepAgents | Raw LangGraph | DeepAgents provides higher-level Skills/Middleware/Backend abstractions. Raw LangGraph requires more boilerplate. |
| Frontend Framework | Next.js 15.4.4 | Remix | Remix is solid but Next.js has larger ecosystem, better App Router, more hiring availability. |
| Frontend Framework | Next.js 15.4.4 | Nuxt/Vue | Classroom constraint specifies React ecosystem. |
| RAG Engine | LightRAG | LangChain RAG | LightRAG provides knowledge graph + vector hybrid retrieval. Pure LangChain RAG is vector-only, misses graph relationships. |
| RAG Engine | LightRAG | LlamaIndex | LlamaIndex is document-centric. LightRAG's graph-enhanced approach better suits test knowledge management. |
| Vector DB | PostgreSQL (pgvector) | Dedicated Milvus | pgvector sufficient for moderate scale. Milvus needed only for >1M vectors. Start with pgvector, add Milvus later. |
| Browser Automation | Playwright CLI | Selenium | Playwright has native async, auto-wait, better multi-browser, network interception. Selenium is legacy. |
| Browser Automation | Playwright CLI | Cypress | Cypress runs in-browser only, cannot handle multiple tabs or cross-origin well. Playwright CLI is more flexible for agent use. |
| Browser Automation | Playwright CLI | Playwright MCP Mode | CLI mode uses single `execute` tool, fewer tokens consumed by LLM. MCP mode exposes many tools, confusing for agent. |
| PDF Parsing | PyMuPDF4LLM | PyPDF2 | PyMuPDF4LLM produces cleaner markdown output, better table extraction, faster performance. |
| PDF Parsing | PyMuPDF4LLM | Docling | Docling is MCP server for document links. PyMuPDF4LLM for direct file uploads. Complementary, not competing. |
| CSS Framework | Tailwind CSS 4 | CSS Modules | Tailwind utility classes speed development. CSS Modules require more boilerplate. |
| Component Library | Shadcn/ui | Material UI | Shadcn/ui gives full code ownership, better customization, lighter bundle. MUI imposes design decisions. |
| State Management | nuqs | Zustand | nuqs persists state in URL (shareable, bookmarkable). Zustand is app-memory only. For chat UI, URL state is more valuable. |
| API Client | httpx | requests | httpx is async-native, critical for concurrent MCP server calls. requests is sync-only. |
## Version Discrepancy Warning
## Installation
# === Backend (Python) ===
# Create virtual environment
# .venv\Scripts\activate   # Windows
# Core agent framework
# LLM providers
# RAG
# Document processing
# Web framework + auth
# Embedding model (via Ollama)
# Install Ollama separately, then:
# === Frontend (Node.js) ===
# Core dependencies
# UI
# File handling
# State + data
# Visualization
# Icons + notifications
# === Infrastructure (Docker) ===
# docker-compose.yml should include:
# - PostgreSQL 16 (port 5432)
# - Neo4j 5.x (port 7474/7687)
# - Redis 7.x (port 6379)
# - Milvus 2.x (port 19530)
# - Ollama (port 11434)
# - LightRAG Server (port 9621)
# - LangGraph API (port 2024 or 2026 per project convention)
## Sources
- Python 3.13 status: https://www.python.org/downloads/ (3.13.13, bugfix stage, Apr 7, 2026)
- DeepAgents: https://pypi.org/project/deepagents/ (0.5.5, released Apr 30, 2026, LangChain maintained)
- Next.js: https://www.npmjs.com/package/next (15.4.4, released May 10, 2026 - NO version 16 exists)
- @langchain/langgraph-sdk: https://www.npmjs.com/package/@langchain/langgraph-sdk (streaming via SSE/WebSocket)
- LightRAG: https://github.com/HKUDS/LightRAG (EMNLP 2025, PostgreSQL support, Docker deployment)
- React 19: Ships with Next.js 15 (https://react.dev/blog)
- Tailwind CSS 4: https://tailwindcss.com (CSS-native config, better performance)
- Shadcn/ui: https://ui.shadcn.com (copy-paste components on Radix UI)
- Playwright: https://playwright.dev (CLI mode preferred for agent integration)
- PyMuPDF4LLM: https://pypi.org/project/PyMuPDF4LLM/ (PDF to markdown conversion)
- MASTEST paper: arXiv:2511.18038 (API testing methodology)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->

---

# 2026-08 大改造（游戏测试全生命周期平台）

在原有 用例生成 / Web 自动化 / API 自动化 三智能体基础上，新增以下模块（详见 `.planning/TRANSFORMATION.md`）：

## 新模块

| 模块 | 后端 | 前端页面 |
|---|---|---|
| 用户模块 | `db/models/user.py` + `api/v2/auth.py`（PBKDF2 + Bearer Token，默认 admin/admin123） | `/login` |
| 设置模块 | `api/v2/settings.py` + `services/settings_service.py`（DB KV + .env 同步） | `/settings` |
| 用例生成→飞书 | `services/feishu_service.py`（lark-cli：mindnotes 思维导图 + docs 拉取）；testcase agent 新工具 `export_project_mindmap`（按 project_name 读 MD 文档导图） | — |
| 用例存储 | **2026-08-28 MD 重构**：一个项目 = `workspace/default/cases/{项目名}.md`（唯一事实源），`services/case_docs_service.py` 解析（标题层级=导图节点层级，[P0-P3] 优先级，「前置：」+ `- 操作 ⇒ 预期` 缩进步骤）；智能体工具收敛为 save/read/list_case_document*；API `/api/v2/case-docs`；旧 test_cases/test_steps/case_groups/tags/case_review* 五张表与数据已删除 | `/cases`（MD 查看/编辑器 + 标注工具栏 + 飞书导图按钮） |
| 用例标注 | 用户直接在 MD 源文件上标注：标题尾部 ✅/❌/⚠️ + `>` 引用批注；漏测用例直接补进文档。无打分表、无 API——下游全是 LLM 读原文 | `/cases` 编辑模式 |
| 自进化 | `services/evolution_service.py` + `services/scheduler.py`（APScheduler 每日 02:00 Asia/Shanghai）：扫描 cases 目录 → 内容 hash 与 `.evolution_state.json` 比对增量 → 有标注的文档原文喂 LLM 反思（含漏测教训）→ 记 evolution_runs；不改技能文件 | `/evolution` |
| 技能库 | `api/v2/skills.py`：上传 SKILL.md / zip 技能包、浏览、删除（技能库由用户手动维护，蒸馏功能已移除） | `/skills` |
| MCP | `mcp_servers/rag_server.py`（FastMCP stdio，按需拉起）；codebase-memory 由 `mcp_client.py` stdio 直连 exe | `/mcp` |
| RAG | `services/lightrag_service.py`（LightRAG Server HTTP API；本体由启动器常驻 :9621，LLM=DeepSeek，Embedding=硅基流动 bge-m3） | `/rag` |
| 代码图谱 | `services/codebase_service.py`（**平台侧全走 `exe cli <tool> <json>` 一锤子模式**，stdout 纯 JSON；stdio MCP 会话在 index 长调用上偶发挂起弃用于平台路径，仅 Agent `search_codebase` 工具继续走 `cbm_call`+垫片）；仓库管理/索引编排/定时增量/图数据代理；exe 为 **GS/Lua 定制版** `C:/codebase/cbm-gs.exe`（备份于 `C:/codebase/*.bak-20260826` + git bundle；官方 v0.10.8 无 GS，勿回切）；HTTP 图服务用官方版 `build/c` exe（GS 版构建未内嵌 UI 资源，`--ui=true` 起不来；两 exe 共享索引存储） | `/codebase` |
| 接口自动化 | `services/api_auto_service.py`（飞书文档→LLM 生成 pytest→执行→AI 自修复，最多 API_AUTO_MAX_REPAIR 次） | `/api-auto` |
| UI 自动化 | `skills/unity-ui-test/`（vendor 自 unity-auto-test-skill）+ `agents/unity/`（graph: unity_agent）+ `services/unity_service.py` | `/ui-auto` + 聊天页「UI自动化」tab |
| 代码分析智能体 | `agents/code_analyst/`（graph: code_analyst_agent）：双轨检索=图谱工具（graph_search/trace_symbol/read_symbol，经 cbm_call）+ `/repo/` 原生 grep/read_file；与用例智能体的区别——不生成用例，专注功能定位/调用链/影响面/实现解读，图谱缺失时自动降级文件工具。testcase 的 `search_codebase` 工具共用同一会话 | 聊天页「代码分析」tab |

## 新路由（/api/v2）

`auth` `settings` `feishu` `evolution` `skills` `api-auto` `ui-auto` `rag` `codebase`（原 `reviews` 路由已随评审沉淀合并进 test-cases 移除）
新模块路由强制 Bearer 登录；旧路由保持可选认证兼容。

## 运行前提

- 飞书：本机 `lark-cli` 已登录（`lark-cli auth login`）；设置页填 FEISHU_MINDNOTE_ID
- RAG：启动器(:9000)启动 lightrag 本体（:9621）；需 `LIGHTRAG_EMBEDDING_API_KEY`（默认硅基流动 bge-m3，OpenAI 兼容）；LLM 复用 DEEPSEEK_API_KEY；知识库管理在 `/rag` 页，图谱可视化 `:9621/webui`
- 代码图谱：独立平台模块（不接智能体）。`/codebase` 页三 Tab：仓库管理（多仓库 + 文件类型 include/exclude，规则写入仓库根 `.cbmignore` 代管块，卡片可查看实际内容）/ 图谱可视化（**Sigma.js WebGL** + graphology + 客户端 ForceAtlas2 布局；不用 exe 预计算坐标——那是 3D 布局投影到 2D 无结构，且前 N 节点多为同色 File/Module。节点按 label 配色、度数定大小、默认隐藏结构节点）/ 定时任务（APScheduler IntervalTrigger 每 N 小时，只增量已建库仓库）。索引进度：CLI stderr 逐行回调 → runs API progress 字段 → 前端阶段+最新日志行。exe：管理走 `cli <tool> <json>` 一锤子模式；HTTP 图数据服务 `--ui=true :9749` 由 `ensure_graph_daemon()` 探活+自动拉起。表 `codebase_repos`/`codebase_index_runs`
- UI 自动化：Unity Editor 打开 m72 项目，Tools > LuaTestTool 启动 Server（:16666），进入 Play Mode
- 自进化：FastAPI 进程内调度器，每日 02:00 消费新标注；也可 /evolution 页手动触发
- 启动器(:9000)管理 4 个服务：LangGraph(:2026) / FastAPI(:8001) / WebUI(:3000) / LightRAG(:9621，autostart=False)。MCP（rag/codebase-memory）全部 stdio 按需拉起，不进启动器

## 数据库

现存表 users/auth_tokens/evolution_runs/api_doc_imports/api_scripts/api_script_runs/
ui_scripts/ui_script_runs/settings_kv/workspaces/projects/attachments/configurations/
memories/thread_infos/thread_messages/identifier_seq/codebase_repos/codebase_index_runs，启动自动 create_all。
（2026-08-28 用例 MD 重构：test_cases/test_steps/case_groups/tags/test_case_tags/
case_reviews/case_review_batches 及 api/web 自动化等 30 张遗留表连同数据已 DROP，
备份于 smart_test_platform.backup_*.db；projects 表仅为附件归属锚点保留）

## 2026-08-26 去 git / 去 wiki-mcp 改造

聊天链路彻底移除 git 与 wiki-mcp，改为**按会话挂载目录直接检索**：
- 前端每次对话强制选择仓库（`ChatInterface` 发送前拦截），`configurable.repo_path` 随 run 传入
- `agents/testcase/repo_backend.py` `RepoProxyBackend` 挂为 CompositeBackend 的 `/repo/` **只读**路由，
  agent 用自带 `grep/glob/ls/read_file` 直接查仓库（grep 为字面量匹配，ripgrep 优先自动降级纯 Python）
- `agents/testcase/tools/codebase_tools.py` 提供 `search_codebase` 图谱检索工具（项目名由 repo_path 推导：`E:/a/b`→`E-a-b`，未建库时降级提示）
- 已删除：`git_tools.py`（6 个 git 工具）、`mcp_servers/git_server.py`、`services/git_service.py`、
  `services/code_analysis_service.py`、`api/v2/code_analysis.py`、`db/models/code_analysis.py`、
  wiki-mcp 全链路（agent wiki 工具加载、`api/v2/wikis.py`、config wiki_* 设置、前端 Wiki 选择器与 `useWikis.ts`）
- SYSTEM_PROMPT：「代码变更分析」章节重写为「代码检索（挂载仓库 /repo/）」；Wiki 章节删除
- codebase-memory exe 于 2026-08-26 曾升级官方 v0.10.8（丢失 GS 解析），2026-08-31 已切回
  GS/Lua 定制版（`C:/codebase/cbm-gs.exe`，源自 `feat/gs-structured-ast` 分支备份，索引格式与新版互通）

## 2026-08-28 用例存储 MD 化（去关系库）

- **LangGraph 并发**：`start_server.py` 的 `N_JOBS_PER_WORKER` 由写死 1（全局串行，
  多窗口聊天排队）改为默认 4、可在 .env 覆盖；重启 LangGraph 生效
  （内存态会话状态丢失属正常，历史消息在 SQLite）

用例全生命周期收敛到一份 Markdown 文件（`workspace/default/cases/{项目名}.md`），
关系库用例链路整体移除：

- **格式契约**：`#` 根标题 → `##`+ 分组树 → 用例标题 `[P0-P3]` → `前置：` 行 →
  `- 操作 ⇒ 预期` 缩进步骤（2 空格一级，叶子可带 √/X）；**禁止 TC-xxx 编号**。
  解析器 `services/case_docs_service.py`（两遍式：标题树 → 分组/用例归类；
  顶层裸用例兜底进「未分组」）
- **人工标注**：标题尾 ✅/❌/⚠️ + `>` 批注行；漏测用例直接补进文档。
  导出/解析时标注自动剥离，不进飞书导图
- **智能体**：save/read/list_case_document + get_beijing_timestamp + export_project_mindmap
  （签名从 project_id 改 project_name）；系统提示词与 testcase-workflow 技能改 MD 契约；
  MCP agent_tools_server 同步。SAVE_RESULT 卡片字段 project_name/case_count
- **飞书**：`feishu_service.load_doc_tree(project_name)` 读 MD → 分层写入导图。
  导图连线样式（直线/曲线）是飞书文档自身设置、API 改不了：配置
  `FEISHU_TEMPLATE_MINDNOTE_ID`（一张调好样式、只留根节点的干净模板导图）后
  走「drive +copy 复制模板 → 改根标题 → 逐层写树」，副本与追加节点继承样式；
  留空回退 OPML 导入（默认曲线）。实测约束：同批节点 parent 必须已存在
  （3411001）、单批 ≤50 节点（99992402）——`build_tree_levels` 分层 +
  `_create_nodes_by_level` 分块；lark-cli `--data @file` 只收 cwd 相对路径
  （草稿一律落 `workspace/.feishu_tmp`）
- **自进化**：扫 cases 目录 + sha256 与 `.evolution_state.json` 增量去重 →
  标注文档原文（截 60k 字符）逐份喂 LLM 反思（好模式/反模式/漏测教训）→ evolution_runs
- **已删**：test_cases 等 7 张用例相关表 + 23 张更早期遗留表（数据全删，备份
  smart_test_platform.backup_*.db）；verdict 列/API、/organize 端点、
  save_cases_tree 等 6 个 DB 工具、3 个启动迁移函数、前端打分组件群（约 1400 行）
- **前端 /cases**：重写为「文档列表 + MD 预览/编辑器」，编辑模式带 ✅/❌/⚠️/批注
  插入工具栏与飞书导图按钮；hooks `useCaseDocs.ts` 替代 useTestCases/useProjects。
  预览排版依赖 `@tailwindcss/typography`（globals.css `@plugin` 注册，2026-08-28 新装）
