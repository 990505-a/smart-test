---
phase: 19-agent-memory
plan: 01
subsystem: database, api, agent
tags: [sqlalchemy, fastapi, langchain, agent-tools, middleware, memory]

# Dependency graph
requires:
  - phase: 08-database-models
    provides: SQLAlchemy Base, UUIDMixin, TimestampMixin, BaseRepository, async_session_factory, PaginationInfo schemas
provides:
  - Memory SQLAlchemy model with space_id, key, content, category columns
  - MemoryRepository with space-scoped queries, search, and category filtering
  - MemoryService with full CRUD and get_all_for_injection method
  - 5 REST endpoints at /api/v2/memories (list, get, create, update, delete)
  - save_memory agent tool with key-based upsert logic
  - search_memories agent tool with ILIKE keyword search
  - MemoryInjectionMiddleware auto-loading 20 recent memories into system prompt
  - Full wiring into TestCase agent (tools + middleware chain)
affects: [19-02, frontend-memory-management]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Agent memory tools use async_session_factory directly (bypass FastAPI DI, per D-05/D-06)"
    - "MemoryInjectionMiddleware uses awrap_model_call pattern with _load_memories static method"
    - "Key-based upsert: save_memory checks existing key before create vs update"

key-files:
  created:
    - src/app/db/models/memory.py
    - src/app/db/repositories/memory_repo.py
    - src/app/db/schemas/memory.py
    - src/app/db/services/memory_service.py
    - src/app/api/v2/memories.py
    - src/app/agents/testcase/tools/memory_tools.py
    - src/app/middleware/memory_injection.py
  modified:
    - src/app/db/models/__init__.py
    - src/app/api/deps.py
    - src/app/api/__init__.py
    - src/app/agents/testcase/agent.py

key-decisions:
  - "Memory model scoped by space_id (no FK to Workspace), independent entity for cross-workspace potential"
  - "Agent tools use async_session_factory directly bypassing FastAPI DI (per D-05/D-06 pattern)"
  - "save_memory implements key-based upsert: updates content if same key exists in default space"
  - "MemoryInjectionMiddleware placed between file_middleware and tool_result_limiter in onion chain"
  - "Middleware uses awrap_model_call (not deprecated process method) for DeepAgents compatibility"

patterns-established:
  - "Memory injection pattern: middleware loads DB records and appends to system_message.content"
  - "Agent memory tools: @tool with async_session_factory, try/except with rollback"

requirements-completed: [MEM-01, MEM-02, MEM-03, MEM-04]

# Metrics
duration: 3min
completed: 2026-06-01
---

# Phase 19 Plan 01: Agent Persistent Memory Backend Summary

**Memory SQLAlchemy model, 5 CRUD API endpoints, save_memory/search_memories agent tools with key-based upsert, and MemoryInjectionMiddleware auto-injecting 20 recent memories into the agent system prompt**

## Performance

- **Duration:** 3min
- **Started:** 2026-06-01T13:13:45Z
- **Completed:** 2026-06-01T13:16:47Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- Memory model with space_id, key, content, category columns registered in SQLAlchemy metadata
- MemoryRepository with space-scoped queries, category filter, and ILIKE text search on key/content
- MemoryService with full CRUD operations and get_all_for_injection for middleware consumption
- 5 REST endpoints at /api/v2/memories (GET list, GET by id, POST create, PATCH update, DELETE)
- save_memory tool with key-based upsert (updates existing memory or creates new)
- search_memories tool with ILIKE keyword search returning formatted results
- MemoryInjectionMiddleware loading up to 20 recent memories appended to system prompt
- Full wiring into TestCase agent: tools registered in _all_tools, middleware in onion chain

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Memory model, schemas, repository, service, and CRUD API endpoints** - `92a7952` (feat)
2. **Task 2: Create save_memory agent tool, MemoryInjectionMiddleware, and wire into TestCase agent** - `f55fa57` (feat)

## Files Created/Modified
- `src/app/db/models/memory.py` - Memory SQLAlchemy model (Base, UUIDMixin, TimestampMixin)
- `src/app/db/repositories/memory_repo.py` - MemoryRepository with get_by_space and count_by_space
- `src/app/db/schemas/memory.py` - MemoryCreate, MemoryUpdate, MemoryInfo Pydantic schemas
- `src/app/db/services/memory_service.py` - MemoryService with CRUD + get_all_for_injection
- `src/app/api/v2/memories.py` - FastAPI router with 5 CRUD endpoints
- `src/app/api/deps.py` - Added MemoryServiceDep dependency injection
- `src/app/api/__init__.py` - Registered memories router with Memories tag
- `src/app/db/models/__init__.py` - Registered Memory model import
- `src/app/agents/testcase/tools/memory_tools.py` - save_memory and search_memories @tool functions
- `src/app/middleware/memory_injection.py` - MemoryInjectionMiddleware (AgentMiddleware subclass)
- `src/app/agents/testcase/agent.py` - Wired memory tools and middleware into agent

## Decisions Made
- Memory model scoped by space_id string column (no FK to Workspace) for independence and simplicity
- Agent tools use async_session_factory directly, bypassing FastAPI DI (established D-05/D-06 pattern)
- save_memory implements key-based upsert within default space: checks for existing key, updates if found
- MemoryInjectionMiddleware uses awrap_model_call method (DeepAgents compatible, not deprecated process)
- Middleware placed between file_middleware and tool_result_limiter so memories are context but do not override file content

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Backend memory system fully operational with CRUD API, agent tools, and auto-injection middleware
- Phase 19 Plan 02 can build frontend memory management UI on top of these endpoints
- Memory table will be auto-created on next server start via SQLAlchemy metadata

## Self-Check: PASSED

- All 7 created files verified present
- Task 1 commit 92a7952 verified present
- Task 2 commit f55fa57 verified present

---
*Phase: 19-agent-memory*
*Completed: 2026-06-01*
