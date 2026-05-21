---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: verifying
stopped_at: Completed 15-02-PLAN.md
last_updated: "2026-05-21T10:24:16.870Z"
last_activity: 2026-05-21
progress:
  total_phases: 16
  completed_phases: 14
  total_plans: 42
  completed_plans: 44
  percent: 88
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-11)

**Core value:** AI Agent + Skills system to auto-generate high-quality, executable, traceable test assets (cases/scripts/reports)
**Current focus:** Phase 15 — web-agent-playwright-mcp-upgrade

## Current Position

Phase: 16
Plan: Not started
Status: Phase complete — ready for verification
Last activity: 2026-05-21

Progress: [██████████░] 88% (14/16 phases)

## Performance Metrics

**Velocity:**

- Total plans completed: 12
- Average duration: ~8min
- Total execution time: ~1.5 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 01 | 4 | 36min | 9min |
| Phase 02 | 3 | 35min | 12min |
| Phase 03 | 2 | 10min | 5min |
| Phase 04 | 3 | 23min | 8min |

**Recent Trend:**

- Last 5 plans: 04-03 (5min), 04-02 (7min), 04-01 (11min), 03-02 (4min), 03-01 (6min)
- Trend: Steady

| Phase 01 P01 | 2min | 2 tasks | 15 files |
| Phase 01 P02 | 13min | 2 tasks | 39 files |
| Phase 01 P03 | 19min | 2 tasks | 14 files |
| Phase 01 P04 | 2min | 1 tasks | 3 files |
| Phase 02 P01 | 14min | 2 tasks | 15 files |
| Phase 02 P02 | 13min | 1 tasks | 9 files |
| Phase 02 P03 | 8min | 1 tasks | 1 files |
| Phase 03 P01 | 6min | 2 tasks | 4 files |
| Phase 03 P02 | 4min | 2 tasks | 2 files |
| Phase 04 P01 | 11min | 2 tasks | 10 files |
| Phase 04 P02 | 7min | 2 tasks | 4 files |
| Phase 04 P03 | 5min | 2 tasks | 4 files |
| Phase 05 P01 | 5min | 2 tasks | 31 files |
| Phase 05 P02 | 12min | 2 tasks | 6 files |
| Phase 05 P03 | 3min | 1 tasks | 2 files |
| Phase 06 P01 | 12min | 2 tasks | 10 files |
| Phase 06 P02 | 6min | 2 tasks | 5 files |
| Phase 07 P01 | 18min | 2 tasks | 17 files |
| Phase 08 P01 | 11min | 2 tasks | 26 files |
| Phase 08 P03 | 15min | 2 tasks | 31 files |
| Phase 09 P01 | 17min | 2 tasks | 15 files |
| Phase 09 P02 | 18min | 2 tasks | 17 files |
| Phase 09 P03 | 29min | 2 tasks | 24 files |
| Phase 09 P04 | 10min | 2 tasks | 6 files |
| Phase 10 P01 | 5min | 2 tasks | 4 files |
| Phase 10 P02 | 3min | 2 tasks | 2 files |
| Phase 10 P03 | 5min | 2 tasks | 7 files |
| Phase 11 P02 | 3min | 1 tasks | 3 files |
| Phase 11 P01 | 4min | 2 tasks | 9 files |
| Phase 11 P05 | 5min | 1 tasks | 6 files |
| Phase 11 P04 | 7min | 2 tasks | 4 files |
| Phase 13 P01 | 2min | 2 tasks | 8 files |
| Phase 13 P02 | 2min | 2 tasks | 4 files |
| Phase 14 P01 | 3min | 2 tasks | 41 files |
| Phase 14 P03 | 2min | 2 tasks | 4 files |
| Phase 14 P02 | 2min | 2 tasks | 4 files |
| Phase 15 P01 | 7min | 2 tasks | 10 files |
| Phase 15 P02 | 5min | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- DeepAgents >= 0.5.5 as primary Agent framework
- Onion middleware architecture for layered processing
- LightRAG二次開発 for RAG knowledge system
- Playwright CLI mode over MCP for token efficiency
- Three-domain Agent architecture (TestCase / Web / API)
- [Phase 01]: Used Python 3.12 via uv for backend (deepagents 0.2.8, langgraph 1.1.10)
- [Phase 01]: Three agent stubs use five .parent calls for workspace_dir path resolution
- [Phase 01]: Used react-resizable-panels v4 API (orientation, no autoSaveId/order)
- [Phase 01]: Agent tab switching clears threadId to prevent state leakage
- [Phase 01]: Used inline message object in useChat instead of SDK Message type to match StateType shape
- [Phase 01]: Extracted ConfigDialog from inline page.tsx into separate component
- [Phase 02]: extract_images=False for basic PDF processor; multimodal deferred to Phase 4
- [Phase 02]: PDFContextMiddleware uses v4 immutable pattern (request.system_message as base)
- [Phase 02]: Session isolation via thread_id-keyed dicts with __default__ fallback
- [Phase 02]: Used @tool.func for direct testing of LangChain StructuredTool objects
- [Phase 02]: Separated Excel export scope from RAG/MCP tools to keep plan focused on D-09/D-10/D-11
- [Phase 02]: Removed CSV/JSON/multi-language/version-control from output-formatter as Phase 4+ scope
- [Phase 02]: Separate FilesystemBackend for SkillsMiddleware rooted at src/app/ to avoid path conflicts with workspace backend
- [Phase 02]: Onion middleware order: SkillsMiddleware(outer) -> PDFContextMiddleware(inner) -> LLM
- [Phase 02]: System prompt adapted from classroom reference with RAG/multimodal/test-data-generator removed for Phase 2 scope
- [Phase 03]: wiki-mcp uses npx tsx src.index.ts (not node dist/index.js) because dist/ is not built
- [Phase 03]: wiki_mcp_args stored as space-separated string with .split() for MCP client stdio pattern
- [Phase 03]: wiki-query skill replaces original rag-query, using wiki-mcp's 6 tools via stdio MCP
- [Phase 03]: asyncio.new_event_loop() for safe module-level async tool fetching (avoids asyncio.run crash in LangGraph server)
- [Phase 03]: Graceful wiki-mcp tool fallback -- agent works with just Excel tool if wiki-mcp unavailable
- [Phase 04]: Lazy-init ImageProcessor model to avoid OpenAI API key error at construction
- [Phase 04]: PDFContextMiddleware backward-compat alias for existing imports
- [Phase 04]: Dual-source file extraction: attachments + inline image_url content blocks
- [Phase 04]: Unified export_test_cases dispatches to format-specific private functions (_export_csv/_export_json/_export_markdown)
- [Phase 04]: test-data-generator added as 7th skill with four concrete data categories (valid/boundary/invalid/security)
- [Phase 04]: 3-layer onion middleware: Skills(outer) -> DynamicModel(middle) -> FileContext(inner)
- [Phase 04]: GPT-4o as vision model (changed from Doubao Vision per user request)
- [Phase 04]: Frontend multimodal toggle via Switch in ConfigDialog, persisted via localStorage
- [Phase 05]: settings.workspace_dir / "web" for Web Agent workspace path (not hardcoded)
- [Phase 05]: CompositeBackend pattern: default=shell for execute, routes={"/": file} for file ops
- [Phase 05]: workspace/web/skills/ tracked in git (negation rule in .gitignore)
- [Phase 05]: Module-level backend instantiation instead of factory function
- [Phase 05]: SkillsMiddleware uses sources=['/skills/'] because file_backend rooted at workspace/web/
- [Phase 05]: Agent import tests catch (ImportError, Exception) for pydantic ValidationError when API key unset
- [Phase 05]: useMemo for pipeline stage detection in ChatMessage to avoid re-computation — Stage markers scanned via useMemo on AI message content change
- [Phase 06]: Integrated backend config into tools/__init__.py instead of separate tools.py (Python package shadows flat module)
- [Phase 06]: asyncio.new_event_loop() for playwright_mcp_server (Phase 3 pattern, prevents LangGraph server crash)
- [Phase 06]: sources=['/skills/'] (not '/api/skills/') because file_backend rooted at workspace/api/
- [Phase 06]: composite_backend in create_agent (not file_backend) for shell execute support
- [Phase 07]: Graph-level backends remain static with default workspace; tools resolve dynamically via get_space_id()
- [Phase 07]: Custom circuit breaker (~80 lines) over aiobreaker dependency
- [Phase 07]: Async api_parser: httpx.AsyncClient replaces sync requests for spec fetching
- [Phase 08]: SQLAlchemy Base class lives in database.py to avoid circular imports with engine
- [Phase 08]: DEFAULT_USER_ID (00000000-0000-0000-0000-000000000001) replaces all User FK references per D-04
- [Phase 08]: TestRun.test_plan_id is plain UUID column (no FK) since TestPlan table not in scope per D-03
- [Phase 08]: Agent tools use async_session_factory() directly, bypassing FastAPI Depends (per D-05/D-06)
- [Phase 08]: Converted tools.py to tools/ package to add db_tools module alongside existing export tools
- [Phase 08]: Test run service manages denormalized stats with update_stats helper
- [Phase 09]: Header uses children slot for chat-specific controls, empty for management pages
- [Phase 09]: TypeScript types aligned with actual backend schemas (step_index not step_number)
- [Phase 09]: apiClient reads config from localStorage per-request for immediate workspace switch
- [Phase 09]: SWR key array format [/projects, page, pageSize] prevents cache collisions across pagination
- [Phase 09]: Created 09-01 infrastructure inline (api-client, types, ManagementLayout) as dependency since 09-01 not yet executed
- [Phase 09]: Added template field to TestCaseUpdate type for BDD/standard mode switching in editor
- [Phase 09]: Used @base-ui/react render prop pattern instead of asChild for shadcn v4 Button+Link
- [Phase 09]: zod v4 uses error.issues (not error.errors) for validation error access
- [Phase 09]: Recursive FolderTreeLevel with per-level DndContext for same-level drag-drop reorder
- [Phase 09]: [Phase 09]: Recharts stacked bar chart with stackId='a' for proportional pass/fail/skipped/blocked visualization
- [Phase 09]: [Phase 09]: base-ui Select onValueChange returns string|null, requires null guard for string state setters
- [Phase 10]: ensure_project queries first project (limit=1), creates with DEFAULT_USER_ID if none exists
- [Phase 10]: Auto-save triggered via system prompt instructions at Phase 5, not code-level hooks
- [Phase 10]: HITL via chat text prompts in SKILL.md (per D-03/D-04), not LangGraph interrupt
- [Phase 10]: Regex-based [SAVE_RESULT] marker detection for inline card rendering in chat messages
- [Phase 10]: Cards render only after streaming completes to avoid UI flicker
- [Phase 10]: Named SWR revalidation exports (revalidateTestCases/revalidateProjects) for targeted cache invalidation after Agent auto-saves
- [Phase 11]: Lazy async service factory pattern for parallel plan dependencies (import at call-time)
- [Phase 11]: dict body types for endpoints whose schemas are defined in parallel Plan 01
- [Phase 11]: Scenario route count is 17 (not 18) -- plan listed 17 distinct URL/method pairs
- [Phase 11]: APITest models use flat column design matching test_scenario.py pattern
- [Phase 11]: Script files stored in workspace/api/scripts/ via local filesystem
- [Phase 11]: ScenarioService uses raw dicts for step/mapping data for flexibility
- [Phase 11]: API skills follow existing SKILL.md format with YAML frontmatter, activation triggers, procedures, output templates, quality standards, and inter-skill handoff protocols
- [Phase 11]: Executor skill uses 7-category failure classification (TEST_BUG, API_CHANGE, AUTH_EXPIRED, DATA_ISSUE, ENV_ISSUE, FLAKY, REAL_BUG) for precise healer routing
- [Phase 11]: Execution services use async_session_factory for background tasks (not FastAPI Depends)
- [Phase 11]: Simple dot-notation JSONPath in ScenarioExecutionEngine instead of jsonpath_ng dependency
- [Phase 11]: APITestExecutor uses asyncio.create_subprocess_exec for npx playwright test
- [Phase 13]: WorkspaceServiceDep uses single-line Annotated pattern matching existing deps
- [Phase 13]: SUBDIRS constant defines 5 directories (api, web, testcase, attachments, scripts)
- [Phase 13]: Skill copying only copies api/skills/ and web/skills/ from default when source exists
- [Phase 13]: Inline create form (input + Add/Cancel) for workspace creation instead of dialog/popover
- [Phase 13]: Delete button conditionally rendered only for non-default workspaces (is_default check)
- [Phase 13]: WorkspaceId changed from literal type to string alias for API-driven flexibility
- [Phase 14]: API skills replaced with classroom Chinese versions for consistency with classroom codebase
- [Phase 14]: 5 old exploratory web skills replaced by 8 professional web_mcp pipeline skills
- [Phase 14]: 3 extra API skills preserved from Phase 11 (api-test-quality, playwright-api-testing, test-scenario-design)
- [Phase 14]: Web agent: default tool_patterns=None wraps ALL tools (browser tools frequently fail)
- [Phase 14]: Web agent make_agent() asynccontextmanager prepares for Playwright MCP lifecycle in Phase 15
- [Phase 14]: Used getattr with defaults for safe context attribute access in APIContextInjectionMiddleware
- [Phase 14]: Tool error wrapping returns tuple (content, artifact) for response_format compatibility
- [Phase 15]: 18 tools implemented (plan said 16 but listed 18); all listed tools created as specified
- [Phase 15]: JSON file storage for function/sub-function data; Phase 16 adds WebFunction/WebSubFunction DB models
- [Phase 15]: Session-level MCP pattern (async with client.session) for Playwright persistent browser state
- [Phase 15]: Targeted error wrapping only for browser_/playwright-test/ prefixed tools, not all tools
- [Phase 15]: No graceful degradation for Playwright MCP -- browser tools are required for agent function
- [Phase 15]: SkillsMiddleware uses composite_backend (not file_backend) for full routing

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260517-166 | 全面对比课堂前端代码与我们的前端实现，找出差距并修复 | 2026-05-16 | 8b491fe | [260517-166-frontend-compare-fix](./quick/260517-166-frontend-compare-fix/) |
| 260518-ln9 | 同步 wiki-query SKILL.md 与 wiki-mcp 官方工具定义对齐 | 2026-05-18 | 41e8683 | [260518-ln9-llm-wiki-skill-github-smart-test-platfor](./quick/260518-ln9-llm-wiki-skill-github-smart-test-platfor/) |

### Roadmap Evolution

- Phase 12 added: GitNexus Code Analysis Integration — embed gitnexus-web frontend via iframe, register gitnexus-impact-analysis skill
- Phase 13 added: Workspace Management - Add workspace CRUD API, frontend workspace selector with create/switch/delete, directory auto-provisioning
- Phase 14 added: Skills and Middleware Migration — 14 classroom skills + ContextInjection + ToolErrorHandler + MASTEST system prompt
- Phase 15 added: Web Agent Playwright MCP Upgrade — Replace Shell Backend with Playwright MCP, new tool registry, 8 web skills
- Phase 16 added: Backend and Frontend Alignment — New endpoints (web_tests, web_functions, configurations), new models, frontend pages

## Session Continuity

Last session: 2026-05-21T10:17:28.310Z
Stopped at: Completed 15-02-PLAN.md
Resume file: None
