# Feature Landscape

**Domain:** AI-Powered Intelligent Testing Platform (Agent + RAG + MCP + Skills)
**Researched:** 2026-05-11
**Confidence:** HIGH (based on competitor analysis + 12 weeks of reference codebase + PROJECT.md requirements)

## Table Stakes

Features users expect from an AI testing platform. Missing any of these means the product feels incomplete or non-functional.

### Core Platform Features

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Document parsing (PDF/Word/Excel/Image) | Users will upload requirements in every format. PDF is the universal requirements format. | Medium | Use PyMuPDF4LLM + Docling MCP. Must handle tables, images, mixed layouts. |
| Test case generation from requirements | This IS the core product promise. Without it, nothing else matters. | High | 5-phase forced workflow (analysis -> strategy -> design -> data -> quality). Requires Skills architecture. |
| Multi-format export (Excel/CSV/JSON/Markdown) | Test teams live in Excel. No export = no adoption. | Low | openpyxl for Excel. Must support Zentao, TestRail, Jira Xray column formats. |
| Chat-based conversational interface | AI tools in 2026 are expected to be conversational. Form-based UIs feel outdated. | Medium | Next.js + @langchain/langgraph-sdk streaming. File upload within chat. |
| File upload (drag-drop + paste) | Users will not navigate file dialogs for every document. Drag-drop and paste are baseline UX. | Low | react-dropzone. Must handle PDF, images, Excel, URLs. |
| Streaming responses | Users expect to see the agent "thinking" in real-time. Full-page waits feel broken. | Medium | SSE streaming via langgraph-sdk. Token-by-token rendering. |
| Test report generation | "I ran tests, now what?" Reports with pass/fail/skip counts are the minimum. | Medium | Structured output from agents. Must include coverage metrics and failure analysis. |
| Session/thread management | Users run multiple test tasks. Need to switch between conversations without losing context. | Medium | LangGraph thread_id. List/filter/resume threads. Infinite scroll for history. |

### Web Automation Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| URL-based exploratory testing | "Here's my site, test it." The most natural user request. | High | Mode A of Web Agent. 6-phase exploratory QA with Playwright CLI. |
| Playwright script generation | Teams need executable scripts, not just "the AI tried something." Output must be versionable and CI-runnable. | High | TypeScript .spec.ts files with proper assertions. Must be syntactically valid. |
| Screenshot/video evidence | "Show me what happened." Test evidence is mandatory for bug reports. | Low | Playwright built-in screenshots, video recording, trace viewer. |
| Multi-browser support | Playwright handles this natively, users expect it. | Low | Chromium, Firefox, WebKit. Playwright config handles browser selection. |

### API Automation Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| OpenAPI/Swagger spec import | "Here's my API spec, test it." The standard entry point for API testing. | Medium | $ref resolution, parameter/response/Schema extraction. Must handle Swagger 2.0 and OpenAPI 3.x. |
| Positive + negative test scenarios | Users expect both happy path and error cases. Only testing 200 responses is obviously incomplete. | Medium | MASTEST methodology: forward, reverse, boundary, cross-operation sequence scenarios. |
| Playwright API test scripts | Same as web: executable scripts, not just descriptions. | High | TypeScript with test.step() annotations. Must be runnable via `npx playwright test`. |
| Syntax validation | Generated scripts must actually run. Syntax errors destroy trust immediately. | Low | TypeScript AST parsing. Check imports, types, assertions. |
| Coverage metrics | "How much of my API did you test?" Quantified coverage is expected. | Medium | Data type coverage + status code coverage. Percentage-based reporting. |

## Differentiators

Features that set this platform apart from competitors (mabl, Katalon, Testsigma, Reflect, Applitools). These are not expected by users but provide significant competitive advantage.

### Strong Differentiators (Unique or Rare in Market)

| Feature | Value Proposition | Complexity | Competitors | Notes |
|---------|-------------------|------------|-------------|-------|
| RAG knowledge base with 6 query modes | Test cases grounded in REAL project documentation, not hallucinated. LightRAG's graph + vector hybrid retrieval finds relationships that pure vector search misses. | Very High | None in testing tools. Dify has RAG but not for testing. | LightRAG server + RAG MCP Server (7 tools). PostgreSQL + Neo4j + Milvus stack. This is the biggest moat. |
| Skills architecture (SKILL.md) | Modular, versionable, discoverable professional capabilities. Users can add custom skills without code changes. No competitor has this. | High | None. All competitors hardcode agent behavior. | 6 TestCase skills + web skills + API skills. SKILL.md files define activation, execution flow, output templates. |
| Onion middleware pipeline | Clean separation of concerns: Skills -> Model Selection -> PDF Context -> RAG. Each layer is independently testable and replaceable. | Medium | None. Most platforms have monolithic agent logic. | DeepAgents middleware framework. 4-layer stack for TestCase agent, subsets for other agents. |
| 7-Agent director pipeline (Web Mode B) | Cinema metaphor pipeline: Script Analyst -> Stage Manager -> Blocking Coach -> Set Designer -> Choreographer -> Assistant Director -> Continuity Lead. Each agent has a focused role, producing higher-quality scripts than a single agent. | Very High | Katalon has 6 AI agents but not for web scripting. | Source code analysis -> data-testid injection -> POM generation -> TypeScript scripts. Requires Graphify MCP. |
| MASTEST academic methodology (API) | Published research (arXiv:2511.18038) for RESTful API testing. Rigorous scenario design with forward/reverse/boundary/sequence coverage. Scientific backing that no commercial tool has. | High | None. Academic method not yet in commercial tools. | Evaluated on GPT-4o and DeepSeek. Proven methodology with measurable coverage improvements. |
| Dual-model dynamic switching | DeepSeek (cheap text) + Doubao Vision (multimodal). Automatic detection switches without user intervention. Cost optimization invisible to users. | Medium | Most platforms use a single model. | DynamicModelSelection middleware. Detects images in messages, overrides model. Saves 5-10x cost on text-only tasks. |
| Component-aware web testing (Mode B) | Analyzes SOURCE CODE (not just the running page) to generate targeted tests. Injects data-testid, generates Page Object Models. | Very High | None. All competitors test the running page only. | Requires Graphify code knowledge graph MCP. Parses component tree, generates POM files. |
| MCP protocol standardization | All external tools use the same protocol. New tools plug in without agent code changes. Future-proof integration architecture. | Medium | mabl has MCP server. Others do not. | Docling, Graphify, Playwright, Chart visualization all via MCP. SSE or stdio transport. |

### Moderate Differentiators (Some Competitors Have Partial Versions)

| Feature | Value Proposition | Complexity | Competitors | Notes |
|---------|-------------------|------------|-------------|-------|
| Multi-tenant RAG isolation | Per-workspace knowledge base with JWT + API Key auth. Enterprise-ready from day one. | High | Most SaaS tools have multi-tenancy but not RAG-specific isolation. | X-Space-Id header routing. JWT with auto re-login. API Key fallback. |
| Four-dimensional quality scoring | Completeness (30%) + Accuracy (25%) + Effectiveness (25%) + Executability (20%). Quantified quality gate prevents low-quality output. | Medium | CodiumAI has coverage analysis. None have 4D quality scoring for test cases. | Score < 75 triggers re-generation loop. Forces quality standard. |
| Forced 5-phase workflow | Requirements analysis -> Strategy -> Design -> Data -> Quality review. Prevents the LLM from skipping steps and producing shallow output. | Low | None. Most tools let the LLM freelance. | System prompt enforces phase transitions. Each phase activates specific skills. |
| Human-in-the-Loop interrupts | Pause at critical decision points for human review. Prevents error amplification in multi-stage pipelines. | Medium | Standard in ML pipeline tools. Rare in testing tools. | LangGraph interruptBefore/interruptAfter. Frontend renders approve/reject/edit actions. |
| Test case numbering standard (TC-[PROJECT]-[MODULE]-[NNN]) | Enterprise traceability. Links test cases to projects and modules. Required for audit compliance. | Low | Most enterprise tools (TestRail, Zentao) support custom numbering. | Simple string formatting. Important for integration with existing test management systems. |
| Graph visualization for test reports | antvis/chart-visualization-skills MCP for graphical coverage and quality dashboards. | Medium | Applitools has visual reports. Most have basic charts. | G2 or S2 for coverage heatmaps, quality radar charts, trend lines. |

## Anti-Features

Features to explicitly NOT build. Documented with reasoning to prevent scope creep.

### Explicitly Out of Scope (from PROJECT.md)

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Performance/load testing module | Requires dedicated压测 framework (Locust/k6), separate infrastructure, different expertise. Classroom did not implement this fully. | Focus on functional testing quality. Performance testing is a separate product. |
| Code-level security testing (SAST) | Requires SonarQube/SAST tool integration, vulnerability databases, security expertise. Entirely different domain. | Do NOT integrate static analysis. If users ask, point them to dedicated SAST tools. |
| Mobile app automation | Requires Appium, Device Farm, mobile-specific selectors. Classroom focused on Web only. | Web testing only. If mobile demand arises, it's Phase 8+ and needs its own agent. |
| Multi-user collaboration/permissions | Frontend has no backend user system. Building user management is a full product in itself. | Single-user mode. Multi-tenant RAG isolation (workspace) handles data separation, not user management. |
| CI/CD integration (Jenkins/GitHub Actions) | Pipeline integration is DevOps territory, not testing platform territory. Adds operational complexity. | Generate executable scripts that users can plug into their own CI/CD. Do NOT build pipeline orchestration. |
| Hermes/OpenClaw third-party agent platform integration | Deployment and运维 complexity. Agent platforms are competitors, not integration targets. | Standalone platform. If demand exists, provide API/webhook for external triggers, not deep integration. |
| Visual regression testing | Applitools owns this space. Requires pixel-level comparison AI, baseline management, visual diff rendering. | Do NOT build visual comparison. Focus on functional correctness testing. |
| No-code/low-code test builder | Reflect and Testsigma do this well. Building a visual test builder is a massive frontend undertaking unrelated to AI testing. | AI-powered chat is the "no-code" interface. Users describe what they want in natural language. |
| Test management system (TMS) | TestRail, Zentao, Jira already own this space. We GENERATE test assets; we do not MANAGE them. | Export to TMS formats. Integration via Excel/CSV export, not bidirectional sync. |

### Implicitly Avoided (Architecture Prevents)

| Anti-Feature | Why Architecture Prevents It | What to Do Instead |
|--------------|------------------------------|-------------------|
| Real-time collaborative editing | No WebSocket broadcast layer, no operational transform. Single-user agent sessions. | Each user gets their own workspace and thread. No shared state. |
| Live test execution dashboard | No test runner infrastructure. Agents generate scripts but do not run them in a managed environment. | Users run scripts locally or in their CI/CD. Platform generates scripts, not runs them. |
| Plugin/extension marketplace | No plugin API surface. Skills are file-based, not dynamically loaded. | Skills are SKILL.md files that advanced users can write manually. No marketplace needed. |

## Feature Dependencies

```
Core Infrastructure (Phase 1)
  |
  +---> TestCase Agent Foundation (Phase 2)
  |       |
  |       +---> PDF Parsing (PyMuPDF4LLM + PDFContextMiddleware)
  |       |       |
  |       |       +---> Dual-Model Selection (Doubao Vision for PDF images)
  |       |
  |       +---> Skills System (SkillsMiddleware + first 3 skills)
  |       |       |
  |       |       +---> Full 6 Skills (test-strategy, test-data, quality-review)
  |       |               |
  |       |               +---> 5-Phase Forced Workflow (all skills chained)
  |       |                       |
  |       |                       +---> 4D Quality Scoring (quality-review skill)
  |       |
  |       +---> Excel Export (openpyxl + multi-format)
  |               |
  |               +---> TMS Format Export (Zentao/TestRail/Jira Xray)
  |
  +---> RAG Knowledge System (Phase 3)
  |       |
  |       +---> LightRAG Server (Docker: PostgreSQL + Neo4j + Milvus + Redis)
  |       |       |
  |       |       +---> 6 Query Modes (naive/local/global/hybrid/naive-community/global-community)
  |       |
  |       +---> RAG MCP Server (7 tools, SSE transport)
  |       |       |
  |       |       +---> Multi-Tenant Isolation (JWT + API Key + X-Space-Id)
  |       |
  |       +---> RAGMiddleware (dynamic tool injection based on enable_rag flag)
  |               |
  |               +---> Frontend RAG Toggle (user controls RAG usage per query)
  |
  +---> Advanced TestCase (Phase 4, depends on Phase 2 + Phase 3)
  |
  +---> Web Automation Agent (Phase 5)
  |       |
  |       +---> Mode A: URL Exploratory QA
  |       |       |
  |       |       +---> Playwright CLI Integration
  |       |               |
  |       |               +---> Screenshot/Video/Trace Evidence
  |       |
  |       +---> Mode B: Source Code Component Testing
  |               |
  |               +---> Graphify MCP (code knowledge graph)
  |               |       |
  |               |       +---> data-testid Injection
  |               |       |
  |               |       +---> POM Generation
  |               |
  |               +---> 7-Agent Director Pipeline
  |                       |
  |                       +---> TypeScript Script Generation
  |
  +---> API Automation Agent (Phase 6)
          |
          +---> OpenAPI Parser ($ref resolution)
          |       |
          |       +---> MASTEST Scenario Design (forward/reverse/boundary/sequence)
          |
          +---> Human-in-the-Loop Interrupts (scenario review + script review)
          |       |
          |       +---> Playwright TypeScript Script Generation (test.step)
          |
          +---> Syntax Validation + Coverage Computation
          |       |
          |       +---> Chart Visualization (antvis MCP)
          |
          +---> Quality Report Generation
```

### Critical Dependency Chains

1. **RAG depends on infrastructure**: LightRAG Server requires PostgreSQL + Neo4j + Milvus + Redis + Ollama. All must be running before RAG tools work. Docker Compose is mandatory.

2. **Dual-model depends on PDF pipeline**: DynamicModelSelection only activates when images are detected, which happens through PDFContextMiddleware. The PDF middleware must extract images before the model switcher can evaluate.

3. **Component-aware testing depends on Graphify**: Mode B of Web Agent cannot function without the Graphify MCP server parsing source code into a knowledge graph. If Graphify is unavailable, only Mode A (URL-based) works.

4. **Quality scoring depends on all 6 skills**: The 4D quality score requires the quality-review skill, which requires test cases to have been generated through the test-case-design and test-data-generator skills. Short-circuiting the pipeline produces unscorable output.

5. **Human-in-the-Loop depends on LangGraph interrupts**: The pause/resume mechanism is a LangGraph framework feature. It requires the frontend to use langgraph-sdk's interrupt handling. Both sides must implement the protocol.

## MVP Recommendation

### Phase 1: Core Infrastructure (Must Ship First)
Everything else depends on this.

1. **Project scaffolding** -- Python 3.13 + Next.js 15.4.4 + DeepAgents + LangGraph API
2. **LangGraph API server** -- graph.json routing, streaming, thread state
3. **FilesystemBackend + CompositeBackend** -- workspace for skills, uploads, outputs
4. **Frontend shell** -- Chat UI with streaming, file upload, thread management

### Phase 2: TestCase Agent MVP (Core Value Proposition)
The single most valuable agent. Ship this to prove the concept.

1. **Basic test case generation** -- 3 skills (requirement-analysis, test-case-design, output-formatter)
2. **PDF parsing** -- PyMuPDF4LLM + PDFContextMiddleware
3. **Excel export** -- Multi-format output
4. **Chat-driven workflow** -- Upload doc, get test cases, export to Excel

**Defer:** Full 5-phase workflow, quality scoring, dual-model, RAG integration

### Phase 3: RAG Knowledge System (Biggest Differentiator)
This is what makes the platform unique.

1. **LightRAG Docker deployment** -- PostgreSQL + Neo4j + Milvus + Redis + Ollama
2. **RAG MCP Server** -- 7 tools with SSE transport
3. **Frontend RAG toggle** -- User controls when to use knowledge base

**Defer:** Multi-tenant JWT isolation, all 6 query modes (start with hybrid)

### Phase 4: Advanced TestCase (Quality Polish)
Complete the TestCase agent with all planned features.

1. **Full 6 skills + 5-phase forced workflow** -- Quality gate prevents bad output
2. **4D quality scoring** -- Quantified quality assurance
3. **Dual-model switching** -- Doubao Vision for multimodal documents
4. **TMS format export** -- Zentao, TestRail, Jira Xray compatibility

### Phase 5-6: Web + API Agents (Expansion)
New testing domains.

1. **Web Agent Mode A** -- URL exploratory testing (simpler, ship first)
2. **API Agent** -- OpenAPI parsing + MASTEST + Human-in-the-Loop
3. **Web Agent Mode B** -- Source code analysis + 7-Agent pipeline (most complex)

### Phase 7: Multi-Tenant Hardening (Enterprise Readiness)
Cross-cutting concerns added last.

1. **JWT authentication** -- Workspace + API Key isolation
2. **Connection pooling** -- httpx.AsyncClient reuse
3. **Error handling** -- Retry logic, circuit breakers, health checks

### Defer to Post-MVP

| Feature | Reason for Deferral |
|---------|-------------------|
| Graphify code knowledge graph | Complex external service. Only needed for Web Mode B. |
| Chart visualization MCP | Nice-to-have for reports. Basic text reports work for MVP. |
| Test case numbering standard | Important for enterprise but not for proving the concept. |
| Multi-tenant RAG isolation | Only needed for multi-user deployment. Single-user first. |

## Competitive Positioning

### Where This Platform Wins

1. **vs mabl/Reflect/Testsigma (no-code testing tools):** This platform generates REAL executable scripts (TypeScript Playwright), not proprietary test recordings. Users own their test code and can run it anywhere.

2. **vs Katalon (multi-agent testing):** Katalon has 6 AI agents but no RAG knowledge base. This platform's RAG grounding means test cases are based on actual project documentation, reducing hallucination.

3. **vs CodiumAI/Qodo (code-level testing):** CodiumAI generates unit tests from code. This platform generates test CASES (requirements-level) AND test SCRIPTS (automation-level). Different market segment.

4. **vs Applitools (visual testing):** Applitools does visual regression only. This platform does functional testing across three domains. Not competing on visual; competing on AI-driven test creation.

### Where This Platform Is Weaker

1. **No CI/CD integration** -- Competitors hook into Jenkins, GitHub Actions. This platform generates scripts but does not orchestrate execution.
2. **No visual regression** -- Applitools owns this. Not attempting to compete.
3. **No test management** -- TestRail/Zentao manage test lifecycle. This platform generates assets, not manages them.
4. **No mobile testing** -- Appium/Device Farm required. Web-only for now.

## Sources

- mabl: https://mabl.com (AI-native test authoring, MCP server, failure analysis)
- Reflect: https://reflect.run (plain-English test steps, selector-free AI, no-code)
- Katalon: https://katalon.com (6 AI agents: Requirement Analyzer, Bug Reporter, Test Generation, Report Generator, Autonomous Runner, Root Cause Analyzer)
- Testsigma: https://testsigma.com (simple English test development, cross-browser execution)
- Applitools: https://applitools.com (Visual AI, Ultrafast Grid, 50+ SDKs)
- CodiumAI/Qodo: https://codium.ai (meaningful test generation, edge case coverage, PR review)
- Promptfoo: https://promptfoo.dev (AI security red teaming, vulnerability detection)
- MASTEST paper: arXiv:2511.18038 (multi-agent RESTful API testing methodology)
- Playwright: https://playwright.dev (CLI for coding agents, MCP server, accessibility)
- Dify: https://dify.ai (RAG pipeline, agent capabilities, visual workflow)
- PROJECT.md: Direct requirements from project definition
- Reference codebase: 12 weeks of classroom code (2026-03-14 through 2026-05-07)
