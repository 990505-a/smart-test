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
| 用户模块 | **2026-09-17 去登录**：界面无登录/登出入口，`CurrentUserDep` 无 token 时返回内置本地用户（`api/v2/auth.py`）；`/auth/login` 等仍保留给外部脚本与验收测试 | —（原 `/login` 已删） |
| 设置模块 | `api/v2/settings.py` + `services/settings_service.py`（DB KV + .env 同步） | `/settings` |
| 用例生成→飞书 | `services/feishu_service.py`（lark-cli：mindnotes 思维导图 + docs 拉取）；testcase agent 新工具 `export_project_mindmap`（按 project_name 读 MD 文档导图） | — |
| 用例存储 | **2026-08-28 MD 重构**：一个项目 = `workspace/default/cases/{项目名}.md`（唯一事实源），`services/case_docs_service.py` 解析（标题层级=导图节点层级，[P0-P3] 优先级，「前置：」+ `- 操作 ⇒ 预期` 缩进步骤）；智能体工具收敛为 save/read/list_case_document*；API `/api/v2/case-docs`；旧 test_cases/test_steps/case_groups/tags/case_review* 五张表与数据已删除 | `/cases`（MD 查看/编辑器 + 标注工具栏 + 飞书导图按钮） |
| 用例标注 | 用户直接在 MD 源文件上标注：标题尾部 ✅/❌/⚠️ + `>` 引用批注；漏测用例直接补进文档。无打分表、无 API——下游全是 LLM 读原文 | `/cases` 编辑模式 |
| 记忆（harness 风格 MD） | **2026-09-17 重构**：记忆 = `workspace/<space>/memory/` 下的 Markdown 模块（`AGENTS.md` 工作区指令 / `MEMORY.md` 长期记忆 / `USER.md` 用户画像 / `failures.md` 失败教训 / `PROJECT.md` 项目上下文 / `DECISIONS.md` 决策记录 + 用户自建），`manifest.json` 记启用状态。`services/memory_service.py` 负责种子落盘/读写/启停/关键词检索/注入块拼装；`middleware/memory_injection.py` 把启用模块交给**官方 MemoryMiddleware**（AGENTS.md 规范）注入 system prompt——官方语义是「参考材料而非指令」、**不做截断**（平台那套带预算裁剪的手写拼装 2026-09-18 已删，线上从来没有调用方）；agent 工具 `save_memory/record_failure/search_memories/read_memory_module/list_memory_modules/update_memory_module`；`api/v2/memories` CRUD。**EverOS 服务整体移除**（含 `everos_compat` 垫片、`tools/patch_everos.py`、launcher 服务项、`EVEROS_*` 配置）；旧数据自动迁移：`user.md`→`USER.md`、episodes 主题→`MEMORY.md`（各一次） | `/memories` |
| 技能库 | `api/v2/skills.py`：上传 SKILL.md / zip 技能包、浏览、删除（技能库由用户手动维护，蒸馏功能已移除） | `/skills` |
| MCP | `mcp_servers/rag_server.py`（FastMCP stdio，按需拉起）；codebase-memory 由 `mcp_client.py` stdio 直连 exe | `/mcp` |
| RAG | `services/lightrag_service.py`（LightRAG Server HTTP API）+ `services/rag_kbs.py`（**知识库注册表**：一个库 = 一个实例 + 一个 workspace + 一个端口；官方没有按请求切库的能力——`/query`/`/documents/*` 的请求体里没有 workspace 字段，隔离单位就是进程，见官方 MultiSiteDeployment）+ 能力清单里的 `rag` 能力（6 个工具 `rag_list_kbs/rag_health/rag_query/rag_ingest_text/rag_ingest_file/rag_list_documents`，都带 `kb` 参数；与 `mcp_servers/rag_server.py`（dsh 用）**共用同一 service 层**；`requires=("lightrag",)` —— 本体不在线时工具被 `middleware/assembly.py::_offline_tools` 藏掉并在提示词里写明缺什么，从启动器启起来后 20s 内自动回来，不用重启）。lightrag-hku 1.5.7；LLM 绑定看 `LIGHTRAG_LLM_*`（留空跟随平台主模型），Embedding=本机 MLX bge-m3 / :7997。**分工**：平台只做展示与检索验证（状态/文档/图谱规模/检索测试 + 服务起停）；入库、删除、重新解析、图谱与实体关系编辑在 LightRAG 自带界面里做；**配置**（模型 / Embedding / 知识库清单）在它自带界面的「RAG 设置」页 —— `tools/lightrag-ui` 静态页由启动器每次拉起知识库时同步进它的 WebUI 目录并注入入口按钮（官方 WebUI 是打包好的静态产物、也没有改配置的 API，这是唯一能"进"它界面的办法） | `/rag`（展示+验证）+ 对话页 `rag_*` 工具 + LightRAG 自带界面 |
| 代码图谱 | `services/codebase_service.py`（**平台侧全走 `exe cli <tool>` 一锤子模式**，参数经 **stdin** 传、读工具带 `format=json`——官方 v0.11.0 起读工具默认回给人看的紧凑树，位置参数 JSON 已 deprecated；stdio MCP 会话在 index 长调用上偶发挂起弃用于平台路径，仅 Agent 的图谱工具继续走 `cbm_call`+垫片）。仓库管理/索引编排/定时增量/图数据代理。**exe 为官方 codebase-memory-mcp**（v0.11.0 起一个二进制同时提供 stdio MCP / `cli` / `--ui=true` 图服务，**旧的双 exe（GS 定制版索引 + 官方版出图）已废弃**；GS 版的索引存储与官方版不通用，切回官方后需重新建库）。二进制由平台自管安装（`services/cbm_install.py`，按当前系统下载官方 release + 校验 sha256，「代码图谱」页一键装/升级），项目名规则见 `project_name()`（realpath + 去首斜杠 + 分隔符换 `-`，与 exe 不一致会记 warning） | `/codebase` |
| 接口自动化 | `services/api_auto_service.py`（飞书文档→LLM 生成 pytest→执行→AI 自修复，最多 API_AUTO_MAX_REPAIR 次） | `/api-auto` |
| **通用测试智能体**<br>（能力清单驱动） | `agents/capabilities.py`（**能力=数据**：工具符号 / 技能 / 领域提示词 / CLI 白名单 / MCP server / 外部依赖 / 人工审批项）+ `agents/harness.py`（唯一装配器 `build_agent`）+ `agents/general/`（graph: `smart_test_agent`）。**对话页只有它一个**，专项能力平铺在同一工具面上，由模型自己分诊（提示词里的分诊表来自各能力的 `description`）。加能力 = 在清单里加一条，不用新建 agent / 注册 graph / 改前端。装配是**用户数据**：层级 **智能体 → 能力 → 工具/技能/权限**，存 `workspace/<space>/assembly.json`（v2，`GET/PUT/DELETE /api/v2/agents` + `/catalog`，`/agents` 页可建智能体与能力、挑工具/技能、勾审批）；代码清单退化为种子 + 工具候选池（53 个）。**一个 graph 服务任意多个智能体**：构建期挂全量工具，每轮按 `configurable.agent_id` 现算能力集合，`middleware/assembly.py` 过滤工具面 + 重排提示词能力段（身份/分诊表/领域规则）+ 按能力声明的技能并集过滤技能清单，审批走 `interrupt_on` 的 when 谓词现查——**下一轮对话生效、不用重启**；旧单能力 graph 不受影响。⚠️ 技能是提示级绑定（卸载只是摘掉清单项，文件仍只读可读） | `/chat`（唯一入口）+ `/agents`（装配清单 + 装卸开关） |
| 旧单能力 graph<br>（兼容） | `testcase_agent` / `unity_agent` / `webui_agent` 保留为**薄壳**（`build_agent((一个能力,))`），只为让历史会话续跑。新会话一律 `smart_test_agent`；没有会话再指向它们后可删 `graph.json` 对应条目 | — |
| 智能体测评<br>（2026-09 新增） | `src/app/eval/`：确定性 traceId + LangGraph 事件流 → Langfuse trace 树；YAML 评测集；确定性打分器 + LLM-as-judge；门禁表达式；CLI（`python -m src.app.eval.cli`，退出码可做 CI 门禁）。设计参照 dsh-eval-automation，详见 `EVAL.md`。表 `eval_batches`/`eval_case_results` | `/eval` |
| 代码分析 | `agents/codebase/`（graph: `codebase_agent`）+ 能力清单里的 `codebase` 能力（`requires_repo=True`）。**交互式入口只有一个**：对话页输入框旁的「代码图谱仓库」选择器挂一个「代码图谱」里注册的仓库（`?repo=<id>` → `configurable.workspace_path`，即 cwd）。原「代码图谱 → AI 分析」Tab 2026-09 删除（与对话页重复），`codebase_agent` graph 保留只为跑无头影响分析。**没挂仓库时那 4 个图谱工具不进工具面**（`middleware/assembly.py` 按 `requires_repo` 过滤）——否则它们只会返回"无法使用代码图谱"的降级提示。双轨检索=图谱工具（graph_search/trace_symbol/read_symbol/repo_architecture，经 cbm_call）+ 原生 grep/read_file（**没注册过的仓库也走这条**，文件工具不限范围）。定时任务用它跑无头「增量影响分析」（`services/codebase_analysis_service.py`，报告表 `codebase_impact_reports`） | `/codebase`「AI 分析」Tab + `/chat` 代码图谱仓库选择器 |

## 新路由（/api/v2）

`auth` `settings` `feishu` `skills` `api-auto` `unity-auto` `web-ui-auto` `eval` `rag` `codebase`（`evolution` 已随自进化移除；`memories` 重写为记忆模块 API（2026-09-17 起与 EverOS 无关）；`ui-auto` 于 2026-09 更名为 `unity-auto`）
新模块路由强制 Bearer 登录；旧路由保持可选认证兼容。

## 运行前提

- 飞书：本机 `lark-cli` 已登录（`lark-cli auth login`）；设置页填 FEISHU_MINDNOTE_ID
- RAG：启动器(:5010)启动 lightrag 本体（:5014）；需 `LIGHTRAG_EMBEDDING_API_KEY`（`.env` 当前指向本机 MLX 服务 `:7997` 的 bge-m3，OpenAI 兼容；留空才回落硅基流动）；LLM 复用 DEEPSEEK_API_KEY；知识库管理在 `/rag` 页，图谱可视化 `:5014/webui`
- 代码图谱：独立平台模块（不接智能体）。`/codebase` 页三 Tab：仓库管理（多仓库 + 文件类型 include/exclude，规则写入仓库根 `.cbmignore` 代管块，卡片可查看实际内容）/ 图谱可视化（**Sigma.js WebGL** + graphology + 客户端 ForceAtlas2 布局；不用 exe 预计算坐标——那是 3D 布局投影到 2D 无结构，且前 N 节点多为同色 File/Module。节点按 label 配色、度数定大小、默认隐藏结构节点）/ 定时任务（APScheduler IntervalTrigger 每 N 小时，只增量已建库仓库）。索引进度：CLI stderr 逐行回调 → runs API progress 字段 → 前端阶段+最新日志行。exe：管理走 `cli <tool> <json>` 一锤子模式；HTTP 图数据服务 `--ui=true :9749` 由 `ensure_graph_daemon()` 探活+自动拉起。表 `codebase_repos`/`codebase_index_runs`
- Unity 自动化：**通用桥（标准 MCP）**。平台侧在启动器启动 `unity-mcp`(:5016，需 uv)；Unity 工程里装「MCP for Unity」包（CoplayDev/unity-mcp，MIT），窗口里 Transport 选 HTTP(Remote) 并把 URL 指向本机 5016。平台不含任何游戏侧代码，操作经 MCP：对象查询 / 编辑器控制 / 任意 C#；用例脚本（python，prelude 注入 `u`）在 `/unity-auto` 页管理。旧版 LuaRemoteServer(:16666) 已删除
- Web-UI 自动化：需要一个 Playwright 执行器。容器部署由 compose 的 `playwright` 服务提供（agent 用 `PLAYWRIGHT_RUNNER_URL=http://playwright:5015`）；本机开发跑 `./tools/playwright-runner/start-local.sh`（首次自动装依赖 + chromium）
- 智能体测评：需要 Langfuse（`LANGFUSE_*`）与 judge 端点（`JUDGE_*`，缺省回退主 LLM）。容器部署时 `LANGFUSE_BASE_URL` 覆盖为 `host.docker.internal:3000`（Langfuse 跑在宿主）
- 记忆：无需外部服务；`workspace/<space>/memory/` 下的 Markdown 即事实源，页面改完下一轮对话生效（注入是每个模型调用前重算的）。总闸 `MEMORY_ENABLED` 与单模块开关都在 `/memories` 页（关总闸 = 完全不注入，模型连"有记忆"都不知道）
- 启动器(:5010)管理 6 个服务：LangGraph(:5011) / FastAPI(:5012) / WebUI(:5013) / Playwright 执行器(:5015) / LightRAG(:5014，autostart=False) / Unity MCP 桥(:5016，autostart=False)。这份名单 = "平台能自己拉起的全部服务"，与 `core/integrations.py` 注册表的 `launch` 字段一一对应（有测试保证）。codebase-memory 的 stdio 会话由 FastAPI/LangGraph 进程内部按需拉起，不进启动器

## 数据库

现存表 users/auth_tokens/api_doc_imports/api_scripts/api_script_runs/
unity_scripts/unity_script_runs/web_ui_scripts/web_ui_script_runs/eval_batches/eval_case_results/
settings_kv/workspaces/projects/attachments/configurations/
thread_infos/thread_messages/identifier_seq/codebase_repos/codebase_index_runs，启动自动 create_all。
（2026-09-17：`thread_infos` 新增 `agent` 列（会话属于哪个模式/智能体），由 `init_db()` 就地 ALTER 迁移）
（2026-09：ui_scripts→unity_scripts、ui_script_runs→unity_script_runs 由 `init_db()` 就地
RENAME 迁移，旧库无需重建；web_ui_* 与 eval_* 为新增表）
（2026-08-31 记忆 EverOS 化 → 2026-09-17 又改为 harness 风格 Markdown 模块：
memories/evolution_runs 表早已删除；记忆存储 = `workspace/default/memory/` 下的
`*.md` + `manifest.json`，Git 跟踪；旧的 EverOS 索引目录（`.index/`、`smart-test/`）
是历史残留，可人工清理）
（2026-08-28 用例 MD 重构：test_cases/test_steps/case_groups/tags/test_case_tags/
case_reviews/case_review_batches 及 api/web 自动化等 30 张遗留表连同数据已 DROP，
备份于 smart_test_platform.backup_*.db；projects 表仅为附件归属锚点保留）

## 2026-09-17 工作区模型（取代"挂载仓库"）

对话页不再"挂仓库"，改成 **dsh 式工作区**：一次对话挂一个目录，它就是 agent 的
`cwd`（相对路径相对它解析、shell 在这里执行），路径是**真实路径**（`virtual_mode=False`）——
`read_file` 收绝对路径，完全访问档下工作区之外也能操作。

- `agents/workspace_backend.py`：`WorkspaceShellBackend`（`LocalShellBackend` 子类，`cwd`
  是**动态属性**，按 `configurable.workspace_path` 解析，兼容旧字段 `repo_path`）；
  未挂载时回退 `workspace/default/<agent>/`
- 删除：`agents/testcase/repo_backend.py`（`RepoProxyBackend` 只读 `/repo/` 路由 +
  ripgrep 看门狗 + `/repo` shell 路径翻译）、前端仓库选择器与 localStorage 列表、
  提示词里"必须读仓库"的措辞
- 新增：`middleware/workspace_context.py` 注入"当前工作区的绝对路径 + `ls/read_file`
  用绝对路径"（`ls(".")`/`ls("/")` 在真实路径语义下会列文件系统根目录，必须在提示词里说清）；
  testcase 的 `ThreadContextMiddleware` 复用它并补会话上传目录
- 上传文件路径：`/api/v2/upload-to-workspace` 返回**绝对路径**（前端消息里带上，
  agent 直接 `read_file`）
- 监控：`monitoring/tracing.py` 的 `MonitorMiddleware` 把一个 run 折叠成一条 Langfuse
  trace（generation + tool span，`sessionId`=会话 id），配置走 `LANGFUSE_MONITOR_*`
  （与测评的 `LANGFUSE_*` 分开）；未配置则空转，上报失败只记日志
- 飞书检索开关取消：`FeishuReadonlyMiddleware` 默认注入只读检索指引（显式
  `configurable.feishu_cli="off"` 才关闭）

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
