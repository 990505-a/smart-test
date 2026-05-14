# Phase 8: FastAPI Backend & Database - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a FastAPI CRUD backend (port 8000) alongside the existing LangGraph Agent service (port 2026), with PostgreSQL database (9 tables following classroom schema), local file storage, and Agent tools that write directly to the database. The three-layer architecture matches the classroom: Next.js frontend :3000 → FastAPI backend :8000 → PostgreSQL database, with LangGraph Agent :2026 as the AI service layer.

This phase does NOT include frontend management pages (Phase 9) or Agent-database auto-save integration (Phase 10).

</domain>

<decisions>
## Implementation Decisions

### Database Strategy
- **D-01:** PostgreSQL only + JSONB for flexible data. No MongoDB.
  - **Why:** JSONB provides MongoDB-like flexibility within PostgreSQL (indexed queries, nested documents, jsonb_path_query). Our data volume doesn't need MongoDB's horizontal scaling. Already have Neo4j for LightRAG graph data — fewer databases = easier maintenance.
  - **How to apply:** Use JSONB columns for TestScenarios.data_dependencies, TestResults.step_results, TestCases.custom_fields, Projects.settings.

- **D-02:** SQLAlchemy async (2.0 style) as ORM.
  - **Why:** Matches classroom reference code. Best FastAPI integration with async session management. Largest ecosystem.
  - **How to apply:** Use `from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker`. Define models with `Mapped` type annotations.

### Data Model Scope
- **D-03:** Implement all 9 classroom tables: Projects, Folders, TestCases, TestSteps, TestRuns, TestResults, APIEndpoints, TestScenarios. No Users table (see D-04).
  - **Why:** User explicitly chose full classroom model for completeness.
  - **How to apply:** Follow classroom schema relationships: Projects → Folders (hierarchical), Folders → TestCases, TestCases → TestSteps, TestRuns → TestResults. APIEndpoints and TestScenarios for API testing domain.

- **D-04:** No user authentication. Single default user, no login flow.
  - **Why:** Development focus mode. Classroom code has Users table but doesn't enforce auth in dev mode. Phase scope is backend + DB, not auth.
  - **How to apply:** Skip Users table entirely. Use default user_id in any user-referencing fields. Add auth in future phase if needed.

### Agent-Database Integration
- **D-05:** Agent tools write directly to database via SQLAlchemy session.
  - **Why:** Simplest integration. Agent tools already use @tool decorator pattern. Direct DB access avoids HTTP overhead and keeps Agent self-contained. Matches classroom pattern where agent tools have DB session injected.
  - **How to apply:** Create shared database utility (get_db_session) used by both FastAPI endpoints and Agent tools. Agent tools like `save_test_case_to_db` will create their own async session.

- **D-06:** FastAPI serves as the CRUD API layer for frontend management pages (Phase 9). Agent tools bypass FastAPI and write directly to the same database.
  - **Why:** Separation of concerns. FastAPI handles structured CRUD operations from UI. Agent handles AI-generated data directly.
  - **How to apply:** FastAPI endpoints and Agent tools share the same SQLAlchemy models and session factory. No API calls between them.

### File Storage
- **D-07:** Local filesystem storage under workspace/ directory. No MinIO.
  - **Why:** Zero-config development. Consistent with existing export_test_cases output path. MinIO adds deployment complexity (Docker container, credentials management).
  - **How to apply:** Store attachments in `workspace/{space_id}/attachments/`, test scripts in `workspace/{space_id}/scripts/`. Database records store relative paths. Future MinIO migration via abstract storage interface if needed.

### API Design
- **D-08:** FastAPI on port 8000 with /api/v2 prefix (matching classroom).
  - **Why:** Classroom convention. /api/v2 allows versioning.
  - **How to apply:** `app = FastAPI()`, routers under `/api/v2/projects`, `/api/v2/test-cases`, etc.

### Claude's Discretion
- Exact directory structure for FastAPI code within src/app/
- Database migration strategy (Alembic vs manual)
- Connection pooling configuration
- Error handling patterns for CRUD endpoints
- Repository/Service layer separation depth
- Pydantic schema design details

### Folded Todos
None — no pending todos matched this phase's scope.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Classroom Reference Code
- `d:/test_agent/2026-05-13-ai-test-agent-system-platform/backend/app/` — Classroom FastAPI backend reference (API routes, models, services, repositories)
- `d:/test_agent/2026-05-13-ai-test-agent-system-platform/backend/app/models/` — Classroom database models (PostgreSQL + MongoDB)
- `d:/test_agent/2026-05-13-ai-test-agent-system-platform/backend/app/api/` — Classroom API route definitions
- `d:/test_agent/2026-05-13-ai-test-agent-system-platform/backend/app/services/` — Classroom service layer
- `d:/test_agent/2026-05-13-ai-test-agent-system-platform/backend/app/schemas/` — Classroom Pydantic schemas
- `d:/test_agent/2026-05-13-ai-test-agent-system-platform/backend/app/repositories/` — Classroom data access layer
- `d:/test_agent/2026-05-13-ai-test-agent-system-platform/backend/main.py` — Classroom FastAPI entry point

### Project Planning
- `.planning/CLASSROOM-SUMMARY.md` — Full classroom content summary (13 weeks, all assignments)
- `.planning/REQUIREMENTS.md` — Updated requirements including PLAT-01 through PLAT-08
- `.planning/ROADMAP.md` — Updated roadmap with Phases 8-10

### Existing Codebase Integration Points
- `src/app/core/config.py` — Current Settings class (add database_url, fastapi_port)
- `src/app/core/workspace.py` — Workspace directory helpers (reuse for file storage paths)
- `src/app/agents/testcase/tools.py` — export_test_cases tool (reference for Agent tool patterns)
- `src/app/resilient/__init__.py` — ResilientClient pattern (reference for connection handling)
- `start_server.py` — LangGraph server startup (FastAPI runs alongside this)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/app/core/config.py` (Settings): Centralized pydantic-settings config. Extend with database_url, fastapi_port.
- `src/app/core/workspace.py` (get_workspace_dir): Workspace path resolution. Reuse for attachment/script file paths.
- `src/app/resilient/` (ResilientClient): Connection pooling + retry + circuit breaker pattern. Reference for DB connection patterns.
- `src/app/agents/testcase/tools.py` (@tool pattern): Agent tool decorator pattern. New DB tools follow same pattern.

### Established Patterns
- Configuration: pydantic-settings BaseSettings with .env file
- Agent tools: @tool decorator from langchain_core.tools
- Middleware: 3-layer onion (Skills → DynamicModel → FileContext)
- Workspace: `workspace/{space_id}/{agent_name}/` directory structure
- Async patterns: httpx.AsyncClient for external calls, asyncio throughout

### Integration Points
- FastAPI app runs as separate process alongside `start_server.py` (LangGraph)
- FastAPI shares `src/app/core/config.py` Settings with Agent code
- Agent tools import SQLAlchemy models directly (same Python process for tools, separate process for FastAPI)
- Frontend will call both :8000 (CRUD) and :2026 (Agent streaming) — dual API client pattern

</code_context>

<specifics>
## Specific Ideas

- Follow classroom's layered architecture: API routes → Services → Repositories → Models
- Use classroom's `backend/app/models/` as the primary reference for table schemas
- Keep FastAPI and LangGraph as separate processes (not embedded)
- Database URL pattern: `postgresql+asyncpg://user:pass@localhost:5432/smart_test_platform`

</specifics>

<deferred>
## Deferred Ideas

- MinIO object storage — can add abstract storage interface in future phase
- User authentication (JWT) — deferred to future phase, not needed for dev
- Redis caching layer — not needed for current scale
- Alembic migrations — can add when schema stabilizes
- API rate limiting — FastAPI middleware, add later if needed

</deferred>

---

*Phase: 08-fastapi-backend-database*
*Context gathered: 2026-05-14*
