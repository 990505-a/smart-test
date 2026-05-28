# Roadmap: Smart Test Platform (智能测试平台)

## Overview

This roadmap delivers an AI-powered intelligent testing platform in 7 phases. The journey starts with shared infrastructure and a frontend shell (Phase 1), then delivers the core TestCase Agent MVP — the platform's primary value (Phase 2). From there, the RAG Knowledge System adds the biggest competitive differentiator (Phase 3), followed by advanced TestCase capabilities including dual-model switching and quality scoring (Phase 4). Two independent automation domains follow: Web Automation Agent with the 7-Agent director pipeline (Phase 5) and API Automation Agent with MASTEST methodology (Phase 6). The roadmap closes with multi-tenant hardening for production readiness (Phase 7).

## Phases

**Phase Numbering:**
- Integer phases (1-7): Planned milestone work
- Decimal phases (e.g., 2.1): Urgent insertions via `/gsd:insert-phase`

- [x] **Phase 1: Core Infrastructure + Frontend Shell** - Shared DeepAgents server, lightweight storage (no Docker), MCP services, and complete chat UI (completed 2026-05-11)
- [x] **Phase 2: TestCase Agent MVP** - Upload documents, generate test cases via 5-stage workflow with 4 skills, export to Excel (completed 2026-05-12)
- [x] **Phase 3: RAG Knowledge System** - wiki-mcp stdio MCP server, 6 knowledge query tools, wiki-query skill, agent tool registration (completed 2026-05-12)
- [x] **Phase 4: Advanced TestCase** - Dual-model switching, image/Excel parsing, quality scoring, test data generation, multi-format export (completed 2026-05-13)
- [x] **Phase 5: Web Automation Agent** - Playwright CLI dual-mode, 7-Agent director pipeline, component-aware testing, QA skills (completed 2026-05-14)
- [x] **Phase 6: API Automation Agent** - MASTEST methodology, OpenAPI parsing, Graphify integration, Human-in-the-Loop, coverage reports (completed 2026-05-14)
- [x] **Phase 7: Multi-Workspace & Infrastructure Hardening** - Workspace isolation, connection pooling, circuit breakers, retry logic (completed 2026-05-15)
- [x] **Phase 8: FastAPI Backend & Database** - REST API CRUD backend, PostgreSQL models, local file storage, Agent result persistence (completed 2026-05-15)
- [x] **Phase 9: Platform Management UI** - Project list, test case editor, folder navigation, test execution dashboard (completed 2026-05-15)
- [x] **Phase 10: Agent-Database Integration** - Agent results auto-save to database, test report visualization, Human-in-the-Loop (completed 2026-05-15)
- [x] **Phase 11: API Test Execution Engine & GitNexus Integration** - API test scripts, scenario orchestration, execution engine, 6 API skills (completed 2026-05-16)
- [x] **Phase 12: GitNexus Code Analysis Integration** - Embed gitnexus-web via iframe, register gitnexus-impact-analysis skill (completed 2026-05-19)
- [x] **Phase 13: Workspace Management** - Workspace CRUD API, frontend workspace selector, directory auto-provisioning (completed 2026-05-20)
- [x] **Phase 14: Skills and Middleware Migration** - 14 classroom skills, ContextInjectionMiddleware, ToolErrorHandler, context_schema (completed 2026-05-21)
- [x] **Phase 15: Web Agent Playwright MCP Upgrade** - Replace Shell Backend with Playwright MCP, new tool registry, 8 web skills (completed 2026-05-21)
- [x] **Phase 16: Backend and Frontend Alignment** - New endpoints, models, frontend pages for web test management (completed 2026-05-21)

## Phase Details

### Phase 1: Core Infrastructure + Frontend Shell
**Goal**: All shared infrastructure runs locally (no Docker) and the frontend chat interface is fully operational, ready for Agent integration
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06, PARS-04, UI-01, UI-02, UI-03, UI-04, UI-05, UI-08, UI-09, UI-10, UI-11, UI-12
**Success Criteria** (what must be TRUE):
  1. User can open the frontend and see a chat interface with streaming message rendering via SSE
  2. User can upload PDF, image, and Excel files via drag-drop or paste, and see base64 conversion working in the request payload
  3. User can manage conversation threads (create, filter by status, scroll through history) and switch between TestCase/Web/API agent routing
  4. LightRAG Server starts with lightweight storage (NanoVectorDB + NetworkX + JSON), Ollama runs with qwen3-embedding model, no Docker required
  5. DeepAgents server responds on port 2026 with multi-agent routing configured via graph.json, and MCP services (Docling, Graphify, Playwright) are reachable
**Plans**: 4 plans

Plans:
- [x] 01-01-PLAN.md — Backend infrastructure: Python project, DeepAgents agent stubs, graph.json, start_server.py
- [x] 01-02-PLAN.md — Frontend shell: Next.js 15 project, layout, theme, resizable panels, providers
- [x] 01-03-PLAN.md — Chat features: SSE streaming, file upload, thread management, agent tabs, MCP client
- [x] 01-04-PLAN.md — Infrastructure services: LightRAG lightweight storage, MCP integration

**UI hint**: yes

### Phase 2: TestCase Agent MVP
**Goal**: Users can upload a document and receive structured, numbered test cases exported as a professionally formatted Excel file
**Depends on**: Phase 1
**Requirements**: PARS-01, PARS-05, MIDW-01, MIDW-02, MIDW-03, MIDW-06, SKILL-01, SKILL-02, SKILL-03, SKILL-06, SKILL-07, EXPT-01, EXPT-02, EXPT-04
**Success Criteria** (what must be TRUE):
  1. User can upload a PDF document and receive parsed content via the PDFContextMiddleware injected into the agent's system prompt, with session isolation per thread
  2. User receives test cases generated through a mandatory 5-stage workflow (requirement analysis, strategy, case design, data construction, quality self-check) powered by 3 core skills (requirement-analysis, test-strategy, test-case-design)
  3. User can download an Excel file with professional formatting (headers, borders, alignment, auto-wrap) and standardized case numbering (TC-[PROJECT]-[MODULE]-[NNN])
  4. Previously parsed documents are cached via MD5 hash and not re-processed on repeated uploads
  5. Skills are loaded from SKILL.md files on the filesystem and injected into the agent via the SkillsMiddleware onion layer
**Plans**: 3 plans
nPlans:
- [x] 10-01-PLAN.md — Agent auto-save and HITL: ensure_project tool, DB tools registration, system prompt update, SKILL.md HITL checkpoints
- [x] 10-02-PLAN.md — Chat inline cards: ToolResultCard component, regex detection in ChatMessage, deep links to management
- [x] 10-03-PLAN.md — Test reports and SWR revalidation: /reports page with recharts, SWR mutate after auto-save

Plans:
- [x] 02-01-PLAN.md — PDF processing pipeline: PDFProcessor with MD5 caching, PDFContextMiddleware with session isolation
- [x] 02-02-PLAN.md — Skills system and Excel export: 5 SKILL.md files, Excel export tool with field extraction
- [x] 02-03-PLAN.md — Agent wiring: middleware chain, system prompt, tool registration, integration

### Phase 3: RAG Knowledge System
**Goal**: wiki-mcp knowledge query tools integrated into TestCase Agent via stdio MCP, with wiki-query skill guiding agent usage during requirement analysis and test strategy stages
**Depends on**: Phase 2
**Requirements**: MIDW-05, SKILL-08, RAGS-01, RAGS-03, RAGS-04, RAGS-05, UI-06
**Success Criteria** (what must be TRUE):
  1. wiki-mcp registers as stdio MCP server providing 6 tools (list_wikis, list_pages, get_page, search, graph_query, reload) to the TestCase Agent
  2. Agent has wiki-query skill loaded via SkillsMiddleware, guiding when and how to query wiki knowledge during requirement-analysis and test-strategy stages
  3. wiki-mcp configuration (command, args, config path) is managed through environment variables and config.py Settings
  4. All integration tests pass: config settings, MCP client registration, SKILL.md validity, agent tool availability
  5. Agent degrades gracefully when wiki-mcp is unavailable (tools list falls back to base tools only)
**Plans**: 2 plans

Plans:
- [x] 03-01-PLAN.md — wiki-mcp foundation: config.py settings, MCP client stdio entry, wiki-query SKILL.md
- [x] 03-02-PLAN.md — Agent wiring and tests: wiki-mcp tool registration, integration test suite

**UI hint**: no

### Phase 4: Advanced TestCase
**Goal**: Users can generate test cases from images and Excel files, with dual-model intelligence, quality scoring, test data generation, and multi-format export
**Depends on**: Phase 3
**Requirements**: PARS-02, PARS-03, PARS-06, MIDW-04, SKILL-04, SKILL-05, EXPT-03, UI-07
**Success Criteria** (what must be TRUE):
  1. User can upload images (parsed by GPT-4o) and Excel files (parsed by openpyxl), and the DynamicModelSelection middleware automatically switches between DeepSeek (text) and GPT-4o (multimodal) based on content type
  2. User receives a four-dimensional quality score for each generated test case set (completeness 30%, accuracy 25%, effectiveness 25%, executability 20%)
  3. User receives generated test data covering valid, boundary, invalid, and security-attack categories via the test-data-generator skill
  4. User can export test cases in multiple formats — CSV (compatible with ZenTao/TestRail), JSON (compatible with Jira Xray), and Markdown — in addition to Excel
  5. User can toggle multimodal mode via the UI switch, controlling the ENABLE_PDF_MULTIMODAL parameter
**Plans**: 3 plans
nPlans:
- [x] 10-01-PLAN.md — Agent auto-save and HITL: ensure_project tool, DB tools registration, system prompt update, SKILL.md HITL checkpoints
- [x] 10-02-PLAN.md — Chat inline cards: ToolResultCard component, regex detection in ChatMessage, deep links to management
- [ ] 10-03-PLAN.md — Test reports and SWR revalidation: /reports page with recharts, SWR mutate after auto-save

Plans:
- [x] 04-01-PLAN.md — Backend middleware: DynamicModelSelection, FileContextMiddleware refactor, ImageProcessor, ExcelProcessor, config updates
- [x] 04-02-PLAN.md — Export and Skills: unified export_test_cases (CSV/JSON/Markdown), test-data-generator SKILL.md
- [x] 04-03-PLAN.md — Integration wiring: 3-layer agent middleware, frontend multimodal toggle, system prompt update

**UI hint**: yes

### Phase 5: Web Automation Agent
**Goal**: Users can generate executable Playwright TypeScript test scripts from either a target URL (exploratory QA) or source code repository (component-aware testing), with evidence artifacts
**Depends on**: Phase 4
**Requirements**: WEB-01, WEB-02, WEB-03, WEB-04, WEB-05, WEB-06, WEB-07, WEB-08, UI-14
**Success Criteria** (what must be TRUE):
  1. User provides a target URL and the Web Agent automatically detects exploratory QA mode, runs a 6-stage professional QA workflow, and generates Playwright TypeScript test scripts with trace/screenshots evidence
  2. User provides a source code repository URL and the Web Agent detects component-aware mode, analyzes source for data-testid injection, generates Page Object Model files, and produces component-level test scripts
  3. The 7-Agent director pipeline executes end-to-end (Script Analyst through Continuity Lead) for complex web testing scenarios, with each agent's output visible as a sub-agent in the UI
  4. User can activate specialized QA skills (system exploration, evidence collection, performance, security, accessibility, responsive) via the Agent-Browser mode
  5. Playwright CLI integration supports session management, stored state, network control, multi-tab handling, and video recording for all generated test scripts
**Plans**: 3 plans
nPlans:
- [ ] 10-01-PLAN.md — Agent auto-save and HITL: ensure_project tool, DB tools registration, system prompt update, SKILL.md HITL checkpoints
- [ ] 10-02-PLAN.md — Chat inline cards: ToolResultCard component, regex detection in ChatMessage, deep links to management
- [ ] 10-03-PLAN.md — Test reports and SWR revalidation: /reports page with recharts, SWR mutate after auto-save

Plans:
- [x] 05-01-PLAN.md — Backend foundation: custom tools (detect_test_mode, check_environment, ensure_output_dir), CompositeBackend, config.py updates, 5 Skill directories from classroom reference (completed 2026-05-14)
- [x] 05-02-PLAN.md — Agent core: dual-mode agent.py, validate_agent.py, MCP Graphify config, test suite (test_web_tools, test_web_skills, test_web_agent)
- [x] 05-03-PLAN.md — Frontend UI-14: pipeline stage visualization in ChatMessage for 7-Agent Director Pipeline progress

**UI hint**: yes

### Phase 6: API Automation Agent
**Goal**: Users can import an OpenAPI/Swagger spec and receive generated, syntax-validated Playwright TypeScript API test scripts with coverage metrics and graphical reports
**Depends on**: Phase 5
**Requirements**: API-01, API-02, API-03, API-04, API-05, API-06, API-07, API-08, API-09, UI-13
**Success Criteria** (what must be TRUE):
  1. User imports an OpenAPI/Swagger specification and the agent resolves all $ref references, extracts parameters/responses/schemas, and generates test scenarios (positive, negative, boundary, cross-operation sequences)
  2. User receives executable Playwright TypeScript scripts with test.step organization and soft assertions, validated by the syntax checker tool
  3. User sees coverage metrics (data type coverage and status code coverage) calculated for the generated test suite
  4. User can approve or reject agent actions at critical stages via Human-in-the-Loop interrupts displayed in the UI, preventing unsupervised destructive operations
  5. User can retrieve source-code-level interface information through Graphify MCP integration and view graphical reports via the chart-visualization skill
**Plans**: 2 plans

Plans:
- [x] 06-01-PLAN.md — Backend foundation: tools (api_parser, metrics, playwright_mcp_server), CompositeBackend, GitNexus config, 3 Skills
- [x] 06-02-PLAN.md — Agent core: MASTEST agent.py, GitNexus MCP registration, test suite (test_api_tools, test_api_skills, test_api_agent)

**UI hint**: yes

### Phase 7: Multi-Workspace & Infrastructure Hardening
**Goal**: The platform supports multiple isolated workspaces via X-Space-Id header with resilient infrastructure patterns for production-quality reliability
**Depends on**: Phase 6
**Requirements**: INFRA-07, INFRA-08, RAGS-02
**Success Criteria** (what must be TRUE):
  1. User can switch between workspaces via X-Space-Id header, and all RAG data (documents, entities, chunks) is isolated per workspace without user authentication
  2. RAG knowledge base queries return only documents belonging to the selected workspace (NanoVectorDB + NetworkX directory-level isolation)
  3. External service calls use connection pooling (httpx.AsyncClient), exponential backoff retry, and circuit breaker patterns — repeated failures to any MCP service are gracefully handled without cascading errors
**Plans**: 2 plans

Plans:
- [x] 07-01-PLAN.md — Backend workspace infrastructure: workspace helper, ResilientClient, agent backend refactoring, api_parser httpx migration, data migration
- [x] 07-02-PLAN.md — Frontend workspace UI: WorkspaceSelect component, useChat space_id propagation, page layout wiring

**UI hint**: yes

### Phase 8: FastAPI Backend & Database
**Goal**: Add a FastAPI CRUD backend alongside the existing LangGraph Agent, with PostgreSQL database models, local file storage, and API endpoints for project/test case/folder management — following the classroom's three-layer architecture (FastAPI :8000 + LangGraph :2026 + Next.js :3000)
**Depends on**: Phase 7
**Requirements**: PLAT-01, PLAT-02, PLAT-03, PLAT-04, PLAT-05, PLAT-06, PLAT-07, PLAT-08
**Success Criteria** (what must be TRUE):
  1. FastAPI server starts on port 8000 with /api/v2 endpoints for projects, folders, test cases, and attachments
  2. PostgreSQL database with 9 core tables (Projects, Folders, TestCases, TestSteps, TestRuns, TestResults, APIEndpoints, TestScenarios, Attachments) following classroom schema
  3. CRUD operations work end-to-end: create project, add folder, create test case with steps, list/filter
  4. Local filesystem storage under workspace/ directory for test artifacts (per D-07, no MinIO)
  5. Agent-generated test cases can be saved to database via tools (per D-05/D-06)
  6. Frontend can call FastAPI endpoints alongside existing LangGraph streaming
**Plans**: 3 plans
nPlans:
- [ ] 10-01-PLAN.md — Agent auto-save and HITL: ensure_project tool, DB tools registration, system prompt update, SKILL.md HITL checkpoints
- [ ] 10-02-PLAN.md — Chat inline cards: ToolResultCard component, regex detection in ChatMessage, deep links to management
- [ ] 10-03-PLAN.md — Test reports and SWR revalidation: /reports page with recharts, SWR mutate after auto-save

Plans:
- [x] 08-01-PLAN.md — Database foundation: SQLAlchemy async models (9 tables), session factory, Pydantic schemas/enums, base repository, identifier generator, file storage utility
- [ ] 08-02-PLAN.md — FastAPI app + project/folder CRUD: create_app, CORS, /api/v2 router, deps.py, project CRUD endpoints, folder CRUD with tree structure
- [x] 08-03-PLAN.md — Test case/run CRUD + Agent DB tools: test case CRUD with steps, test run management, attachment upload, agent tools (save_test_case_to_db, save_test_cases_batch, list_project_test_cases)

**UI hint**: no

### Phase 9: Platform Management UI
**Goal**: Add frontend management pages for project list, test case editor, folder navigation, and test execution dashboard — transforming the platform from chat-only to a full test management system
**Depends on**: Phase 8
**Requirements**: PLAT-09, PLAT-10, PLAT-11, PLAT-12, PLAT-13
**Success Criteria** (what must be TRUE):
  1. Users see a project list page and can create/edit/delete projects
  2. Folder tree navigation with hierarchical structure and drag-drop reordering
  3. Test case editor with steps, expected results, priority, and BDD support
  4. Test execution dashboard showing run history, pass/fail statistics, and results
  5. Navigation between chat interface (Agent) and management pages (CRUD)
**Plans**: 4 plans

Plans:
- [x] 09-01-PLAN.md — Routing restructure, API client, types, shared layout components (Wave 1) (completed 2026-05-15)
- [x] 09-02-PLAN.md — Project list page with DataTable and SWR CRUD hooks (Wave 2) (completed 2026-05-15)
- [x] 09-03-PLAN.md — Folder tree with @dnd-kit and test case editor with BDD mode (Wave 2) (completed 2026-05-15)
- [x] 09-04-PLAN.md — Test execution dashboard with recharts (Wave 3)

**UI hint**: yes

### Phase 10: Agent-Database Integration
**Goal**: Connect Agent results to the database for automatic persistence, add test report visualization (antvis), and implement Human-in-the-Loop for critical decision points
**Depends on**: Phase 9
**Requirements**: PLAT-14, PLAT-15, PLAT-16, PLAT-17
**Success Criteria** (what must be TRUE):
  1. Agent-generated test cases auto-save to database (no manual copy-paste)
  2. Test reports display with recharts graphical charts
  3. Human-in-the-Loop interrupts at critical stages for approval
  4. Full end-to-end flow: chat with agent, generate cases, auto-save, view in management UI, execute tests, see results
**Plans**: 3 plans
Plans:
- [x] 10-01-PLAN.md — Agent auto-save and HITL: ensure_project tool, DB tools registration, system prompt update, SKILL.md HITL checkpoints
- [x] 10-02-PLAN.md — Chat inline cards: ToolResultCard component, regex detection in ChatMessage, deep links to management
- [ ] 10-03-PLAN.md — Test reports and SWR revalidation: /reports page with recharts, SWR mutate after auto-save

**UI hint**: yes

### Phase 11: API Test Execution Engine & GitNexus Integration
**Goal**: Implement the full API test lifecycle — OpenAPI parsing with auto-folder creation, Playwright-based test execution with Allure reports, scenario-based testing with real HTTP requests, GitNexus code analysis MCP integration, and 6 API-specific agent skills
**Depends on**: Phase 10
**Requirements**: API-10, API-11, API-12, API-13, API-14, API-15, API-16, PLAT-18, PLAT-19, PLAT-20
**Success Criteria** (what must be TRUE):
  1. User uploads an OpenAPI/Swagger spec and the system auto-parses it, creates tag-based folder structure, and stores endpoint metadata in the database
  2. API Agent generates Playwright test scripts from endpoint definitions, with test execution engine downloading scripts, running via npx playwright test, parsing JSON results, and generating Allure HTML reports
  3. Scenario engine executes multi-step business flows with real HTTP requests (httpx), JSONPath data extraction, template variable substitution, and assertion comparison (eq/ne/gt/lt/contains)
  4. 6 API-specific skills (planner, generator, executor, healer, reporter, scenario) loaded via SkillsMiddleware from .claude/skills/api/ directory
  5. GitNexus MCP integration provides code analysis capabilities to the API Agent for source-code-aware test generation
  6. Frontend pages for API test management: schema upload, test list, execution trigger, run history, report viewer
  7. ~28 agent tools across 7 categories registered in tool_registry.py for comprehensive API test lifecycle management
**Plans**: 6 plans

Plans:
- [x] 11-01-PLAN.md — Database models and services: APITest/APITestRun/APITestResult models, APITestService, ScenarioService (Wave 1)
- [x] 11-02-PLAN.md — FastAPI routes: 13 API test endpoints, 18 scenario endpoints (Wave 1)
- [x] 11-03-PLAN.md — Agent tools and refactor: ~28 tools in 7 categories, make_agent() factory, GitNexus MCP (Wave 2)
- [x] 11-04-PLAN.md — Execution engines: OpenAPI parser, APITestExecutor, ScenarioExecutionEngine (Wave 2)
- [x] 11-05-PLAN.md — API Skills: 6 SKILL.md files (planner, generator, scenario, executor, healer, reporter) (Wave 1)
- [x] 11-06-PLAN.md — Frontend pages: API test management, scenario editor, management navigation (Wave 3)

**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11 -> 12 -> 13 -> 14 -> 15 -> 16 -> 17

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Infrastructure + Frontend Shell | 4/4 | Complete | 2026-05-11 |
| 2. TestCase Agent MVP | 3/3 | Complete | 2026-05-12 |
| 3. RAG Knowledge System | 2/2 | Complete    | 2026-05-12 |
| 4. Advanced TestCase | 3/3 | Complete | 2026-05-13 |
| 5. Web Automation Agent | 3/3 | Complete | 2026-05-14 |
| 6. API Automation Agent | 2/2 | Complete | 2026-05-14 |
| 7. Multi-Workspace & Infrastructure | 2/2 | Complete | 2026-05-15 |
| 8. FastAPI Backend & Database | 3/3 | Complete | 2026-05-15 |
| 9. Platform Management UI | 4/4 | Complete | 2026-05-15 |
| 10. Agent-Database Integration | 3/3 | Complete | 2026-05-15 |
| 11. API Test Execution Engine & GitNexus Integration | 6/6 | Complete | 2026-05-16 |
| 12. GitNexus Code Analysis Integration | 2/2 | Complete | 2026-05-19 |
| 13. Workspace Management | 2/2 | Complete   | 2026-05-20 |
| 14. Skills and Middleware Migration | 3/3 | Complete | 2026-05-21 |
| 15. Web Agent Playwright MCP Upgrade | 2/2 | Complete | 2026-05-21 |
| 16. Backend and Frontend Alignment | 2/2 | Complete | 2026-05-21 |
| 17. Frontend Message Scroll Pagination | 0/2 | Planned | -- |

### Phase 12: GitNexus Code Analysis Integration
**Goal**: Embed GitNexus code intelligence into the platform — iframe-based frontend integration for code graph visualization, and register gitnexus-impact-analysis skill for AI-driven code analysis workflows
**Depends on**: Phase 11
**Requirements**: CODE-01, CODE-02
**Success Criteria** (what must be TRUE):
  1. User can navigate to /code-analysis page and see GitNexus web UI embedded via iframe, connecting to localhost:4747
  2. Management sidebar includes "代码分析" navigation item linking to /code-analysis
  3. gitnexus-impact-analysis skill is registered in .claude/skills/ and available to Claude Code sessions
  4. Page gracefully handles offline state when gitnexus server is not running (shows connection instructions)
**Plans**: 2 plans

Plans:
- [x] 12-01-PLAN.md — Frontend code analysis page: /code-analysis route with iframe embedding, ManagementLayout nav update, offline detection (completed 2026-05-19)
- [x] 12-02-PLAN.md — GitNexus skill registration: gitnexus-impact-analysis SKILL.md in .claude/skills/, GitNexus MCP config verification (completed 2026-05-19)

**UI hint**: yes


### Phase 13: Workspace Management - Add workspace CRUD API, frontend workspace selector with create/switch/delete, directory auto-provisioning

**Goal**: Replace the hardcoded single-workspace system with a database-driven workspace management API and dynamic frontend selector, supporting create, switch, delete operations with automatic directory provisioning and skill copying
**Depends on**: Phase 12
**Requirements**: WS-CRUD-01, WS-CRUD-02, WS-CRUD-03, WS-DIR-01, WS-DIR-02, WS-SEED-01, WS-FE-01, WS-FE-02, WS-FE-03, WS-FE-04
**Success Criteria** (what must be TRUE):
  1. GET /api/v2/workspaces returns a list of workspace objects from the database, with auto-seeded default workspace on first call
  2. POST /api/v2/workspaces creates a workspace DB record and provisions the directory structure (api/, web/, testcase/, attachments/, scripts/) with skills copied from default workspace
  3. DELETE /api/v2/workspaces/{slug} removes the workspace DB record and deletes its directory, but the default workspace cannot be deleted
  4. Frontend workspace selector fetches workspaces from the API instead of using a hardcoded constant
  5. User can create a new workspace from the selector UI and switch to it; user can delete non-default workspaces
**Plans**: 2 plans

Plans:
- [x] 13-01-PLAN.md -- Backend workspace CRUD: Workspace model, schemas, repository, service (with directory provisioning and skill copying), FastAPI routes, deps and router registration (Wave 1)
- [x] 13-02-PLAN.md -- Frontend workspace selector: TypeScript types, SWR hooks, data-driven WorkspaceSelect component with create/delete UI, type propagation (Wave 2)

**UI hint**: yes

### Phase 14: Skills and Middleware Migration

**Goal**: Migrate 14 classroom skills (6 API + 8 Web MCP) into the project workspace, add ContextInjectionMiddleware and ToolErrorHandler for both agents, and upgrade agent wiring with context_schema for runtime parameter injection
**Depends on**: Phase 13
**Requirements**: API-13, SKILL-MIGRATION, MIDW-CTX-01, MIDW-ERR-01
**Success Criteria** (what must be TRUE):
  1. 6 classroom API skills replace existing skills in workspace/default/api/skills/ (3 extra API skills preserved)
  2. 8 new web_mcp skills replace 5 old web skills in workspace/default/web/skills/ (including test-cases.json data)
  3. API agent has APIContextInjectionMiddleware that injects project_identifier and folder_id into system prompt
  4. Web agent has WebContextInjectionMiddleware with same context injection capability
  5. Both agents have ToolErrorHandler wrapping tools to return JSON errors instead of crashing
  6. Both agents register context_schema dataclass with create_deep_agent for runtime context support
**Plans**: 3 plans

Plans:
- [x] 14-01-PLAN.md -- Skills migration: copy 14 classroom skills (6 API + 8 Web MCP) to workspace, remove 5 old web skills (Wave 1)
- [x] 14-02-PLAN.md -- API agent middleware: APIContextInjectionMiddleware, ToolErrorHandler, APIAgentContext, agent wiring (Wave 2)
- [x] 14-03-PLAN.md -- Web agent middleware: WebContextInjectionMiddleware, ToolErrorHandler, WebAgentContext, make_agent() factory (Wave 2)

### Phase 15: Web Agent Playwright MCP Upgrade

**Goal**: Replace Web Agent's Shell Backend with Playwright MCP for real browser control, add 16-tool registry for web testing lifecycle, activate 8 web_mcp skills from Phase 14
**Depends on**: Phase 14
**Requirements**: WEB-MCP-01, WEB-MCP-02, WEB-MCP-03, WEB-MCP-04, WEB-MCP-05, WEB-MCP-06, WEB-MCP-07, WEB-MCP-08
**Success Criteria** (what must be TRUE):
  1. Config has web_mcp_root setting pointing to workspace/default/web with @playwright/test installed
  2. Tool registry provides 16 local tools across 4 categories (function management, test artifacts, scripts, execution)
  3. Agent creates MCP client connected to Playwright Test MCP server via stdio session-level pattern
  4. System prompt describes 4 workflows (Generate Tests, Create Function, Execute Tests, Auto-Heal)
  5. Error handler targets only browser_ and playwright-test/ prefixed tools (not ALL tools)
  6. 8 web_mcp skills activate automatically when MCP tools are available
**Plans**: 2 plans

Plans:
- [x] 15-01-PLAN.md -- Config settings, Playwright MCP workspace (package.json + npm install), 16-tool registry package (Wave 1)
- [x] 15-02-PLAN.md -- Agent rewrite: MCP session lifecycle, 4-workflow system prompt, targeted error handler, integration verification (Wave 2)

### Phase 16: Backend and Frontend Alignment

**Goal**: Add missing backend endpoints (web_tests, web_functions, configurations), new database models (WebFunction, WebSubFunction, WebTest, WebTestRun, WebTestResult, Configuration), and new frontend pages for web test management to align with classroom implementation
**Depends on**: Phase 15
**Requirements**: BE-ALIGN-01, BE-ALIGN-02, BE-ALIGN-03, FE-ALIGN-01, FE-ALIGN-02, FE-ALIGN-03
**Success Criteria** (what must be TRUE):
  1. GET /api/v2/projects/{id}/web-functions returns paginated list of web functions with sub-functions
  2. GET /api/v2/projects/{id}/web-tests returns paginated list of web tests with function/sub-function filters
  3. GET /api/v2/configurations returns paginated list of OS/browser/device configurations
  4. All 6 new database tables (web_functions, web_sub_functions, web_tests, web_test_runs, web_test_results, configurations) exist in SQLite
  5. Frontend /web-tests page displays function tree with expand/collapse and associated web tests
  6. Management sidebar includes "Web测试" navigation item
**Plans**: 2 plans

Plans:
- [x] 16-01-PLAN.md — Backend models, schemas, repos, services, and routes for WebFunction, WebTest, Configuration (Wave 1)
- [x] 16-02-PLAN.md — Frontend types, SWR hooks, web-tests page with function tree, sidebar navigation update (Wave 2)

**UI hint**: yes

### Phase 17: Frontend Message Scroll Pagination

**Goal**: Implement paginated message loading so the frontend never loads 25MB+ at once. Default: load latest 20 messages, scroll up to load more. Compatible with existing streaming during active runs.
**Depends on**: Phase 16
**Requirements**: MSG-PAG-01, MSG-PAG-02, MSG-PAG-03, MSG-PAG-04, MSG-PAG-05, MSG-PAG-06
**Success Criteria** (what must be TRUE):
  1. Backend endpoint GET /api/v2/threads/{threadId}/messages returns paginated messages with conversation group integrity (AI message + tool results never split)
  2. Opening an existing thread loads only the latest 20 messages, not the full 25MB state
  3. Scrolling up triggers loading of older messages (20 per page) without scroll position jumps
  4. Active streaming auto-scrolls to bottom with new messages; scrolling up pauses auto-scroll
  5. Tool call boxes show correct pending/completed status even with paginated messages
  6. @langchain/langgraph-sdk upgraded from 1.0.3 to 1.9.9; use-stick-to-bottom replaced by react-virtuoso
**Plans**: 2 plans

Plans:
- [ ] 17-01-PLAN.md — Backend pagination endpoint + frontend data layer: FastAPI /threads/{id}/messages, SWR usePaginatedMessages hook, npm dependencies (Wave 1)
- [ ] 17-02-PLAN.md — Frontend UI wiring: Virtuoso virtual scroll in ChatInterface, dual-source message merge in useChat, human verification (Wave 2)

**UI hint**: yes
