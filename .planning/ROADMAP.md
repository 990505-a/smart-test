# Roadmap: Smart Test Platform (智能测试平台)

## Overview

This roadmap delivers an AI-powered intelligent testing platform in 7 phases. The journey starts with shared infrastructure and a frontend shell (Phase 1), then delivers the core TestCase Agent MVP — the platform's primary value (Phase 2). From there, the RAG Knowledge System adds the biggest competitive differentiator (Phase 3), followed by advanced TestCase capabilities including dual-model switching and quality scoring (Phase 4). Two independent automation domains follow: Web Automation Agent with the 7-Agent director pipeline (Phase 5) and API Automation Agent with MASTEST methodology (Phase 6). The roadmap closes with multi-tenant hardening for production readiness (Phase 7).

## Phases

**Phase Numbering:**
- Integer phases (1-7): Planned milestone work
- Decimal phases (e.g., 2.1): Urgent insertions via `/gsd:insert-phase`

- [ ] **Phase 1: Core Infrastructure + Frontend Shell** - Shared DeepAgents server, lightweight storage (no Docker), MCP services, and complete chat UI
- [ ] **Phase 2: TestCase Agent MVP** - Upload documents, generate test cases via 5-stage workflow with 4 skills, export to Excel
- [ ] **Phase 3: RAG Knowledge System** - LightRAG MCP Server, RAG-first strategy, 6 query modes, knowledge query skill
- [ ] **Phase 4: Advanced TestCase** - Dual-model switching, image/Excel parsing, quality scoring, test data generation, multi-format export
- [ ] **Phase 5: Web Automation Agent** - Playwright CLI dual-mode, 7-Agent director pipeline, component-aware testing, QA skills
- [ ] **Phase 6: API Automation Agent** - MASTEST methodology, OpenAPI parsing, Graphify integration, Human-in-the-Loop, coverage reports
- [ ] **Phase 7: Multi-Workspace & Infrastructure Hardening** - Workspace isolation, connection pooling, circuit breakers, retry logic

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

Plans:
- [ ] 02-01-PLAN.md — PDF processing pipeline: PDFProcessor with MD5 caching, PDFContextMiddleware with session isolation
- [x] 02-02-PLAN.md — Skills system and Excel export: 5 SKILL.md files, Excel export tool with field extraction
- [ ] 02-03-PLAN.md — Agent wiring: middleware chain, system prompt, tool registration, integration

### Phase 3: RAG Knowledge System
**Goal**: Users can leverage a RAG knowledge base to generate test cases grounded in real project documentation, with the agent refusing to generate without retrieved context
**Depends on**: Phase 2
**Requirements**: MIDW-05, SKILL-08, RAGS-01, RAGS-03, RAGS-04, RAGS-05, UI-06
**Success Criteria** (what must be TRUE):
  1. User can toggle the RAG switch in the UI, and the agent dynamically gains/loses RAG MCP tools (7 tools: query, query_data, graph_search, graph_get, graph_labels, document_status, health)
  2. When RAG is enabled, the agent enforces a RAG-first strategy — it queries the knowledge base before generating test cases and refuses to generate without retrieved context
  3. User can issue queries using any of the 6 supported query modes (local, global, hybrid, naive, mix, bypass) and receive knowledge-grounded results with source attribution
  4. User can track document processing status (upload progress, indexing state) through the async processing pipeline
  5. The rag-query skill applies a hybrid retrieval strategy with strict citation requirements in all generated outputs
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD

**UI hint**: yes

### Phase 4: Advanced TestCase
**Goal**: Users can generate test cases from images and Excel files, with dual-model intelligence, quality scoring, test data generation, and multi-format export
**Depends on**: Phase 3
**Requirements**: PARS-02, PARS-03, PARS-06, MIDW-04, SKILL-04, SKILL-05, EXPT-03, UI-07
**Success Criteria** (what must be TRUE):
  1. User can upload images (parsed by Doubao Vision) and Excel files (parsed by openpyxl), and the DynamicModelSelection middleware automatically switches between DeepSeek (text) and Doubao Vision (multimodal) based on content type
  2. User receives a four-dimensional quality score for each generated test case set (completeness 30%, accuracy 25%, effectiveness 25%, executability 20%)
  3. User receives generated test data covering valid, boundary, invalid, and security-attack categories via the test-data-generator skill
  4. User can export test cases in multiple formats — CSV (compatible with ZenTao/TestRail), JSON (compatible with Jira Xray), and Markdown — in addition to Excel
  5. User can toggle multimodal mode via the UI switch, controlling the ENABLE_PDF_MULTIMODAL parameter
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD

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
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD

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
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD

**UI hint**: yes

### Phase 7: Multi-Workspace & Infrastructure Hardening
**Goal**: The platform supports multiple isolated workspaces via X-Space-Id header with resilient infrastructure patterns for production-quality reliability
**Depends on**: Phase 6
**Requirements**: INFRA-07, INFRA-08, RAGS-02
**Success Criteria** (what must be TRUE):
  1. User can switch between workspaces via X-Space-Id header, and all RAG data (documents, entities, chunks) is isolated per workspace without user authentication
  2. RAG knowledge base queries return only documents belonging to the selected workspace (NanoVectorDB + NetworkX directory-level isolation)
  3. External service calls use connection pooling (httpx.AsyncClient), exponential backoff retry, and circuit breaker patterns — repeated failures to any MCP service are gracefully handled without cascading errors
**Plans**: TBD

Plans:
- [ ] 07-01: TBD
- [ ] 07-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Infrastructure + Frontend Shell | 0/4 | Planning complete | - |
| 2. TestCase Agent MVP | 0/3 | Planning complete | - |
| 3. RAG Knowledge System | 0/? | Not started | - |
| 4. Advanced TestCase | 0/? | Not started | - |
| 5. Web Automation Agent | 0/? | Not started | - |
| 6. API Automation Agent | 0/? | Not started | - |
| 7. Multi-Workspace & Infrastructure | 0/? | Not started | - |
