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
