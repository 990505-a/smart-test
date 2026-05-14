---
phase: 07-multi-workspace-infrastructure-hardening
plan: 01
subsystem: infra
tags: [langgraph, workspace, httpx, circuit-breaker, retry, async, multi-tenant]

# Dependency graph
requires:
  - phase: 06-api-testing-agent
    provides: Agent backend module-level instantiation pattern, api_parser with sync requests
provides:
  - workspace.py helper (get_space_id, get_workspace_dir) for multi-space isolation
  - ResilientClient wrapper class with retry and circuit breaker
  - CircuitBreaker state machine (CLOSED/OPEN/HALF_OPEN)
  - Async api_parser using httpx instead of sync requests
  - Dynamic workspace resolution for all three agents (web, api, testcase)
  - workspace/default/ directory structure with migrated data
affects: [07-02-PLAN, frontend-workspace-ui]

# Tech tracking
tech-stack:
  added: [httpx.AsyncClient, langgraph.config.get_config]
  patterns: [dynamic-workspace-resolution, circuit-breaker-state-machine, exponential-backoff-retry, async-http-client]

key-files:
  created:
    - src/app/core/workspace.py
    - src/app/resilient/__init__.py
    - src/app/resilient/circuit_breaker.py
    - tests/test_workspace.py
    - tests/test_resilient.py
  modified:
    - src/app/core/config.py
    - src/app/agents/api/tools/api_parser.py
    - src/app/agents/api/tools/__init__.py
    - src/app/agents/web/tools.py
    - src/app/agents/web/agent.py
    - src/app/agents/testcase/agent.py
    - tests/test_api_tools.py
    - tests/test_api_skills.py
    - tests/test_web_agent.py
    - tests/test_web_skills.py
    - .gitignore

key-decisions:
  - "Graph-level backends remain static with default workspace; tools resolve dynamically via get_space_id() at call time"
  - "Custom circuit breaker (~80 lines) over aiobreaker dependency for trivial logic"
  - "Workspace data migrated to workspace/default/{web,api,testcase}/ structure"
  - "System prompt updated to reference ensure_output_dir tool instead of hardcoded output_root paths"

patterns-established:
  - "Dynamic workspace resolution: get_space_id() + get_workspace_dir(space_id, agent_name)"
  - "Resilient HTTP: ResilientClient wraps httpx.AsyncClient with retry + circuit breaker"
  - "CircuitBreaker pattern: CLOSED -> OPEN (5 failures) -> HALF_OPEN (30s timeout) -> CLOSED (success)"
  - "Async api_parser: httpx.AsyncClient replaces sync requests for non-blocking spec fetching"

requirements-completed: [INFRA-07, INFRA-08, RAGS-02]

# Metrics
duration: 18min
completed: 2026-05-14
---

# Phase 07 Plan 01: Multi-Workspace Infrastructure Summary

**Workspace isolation via LangGraph configurable, ResilientClient with circuit breaker, and async api_parser migration**

## Performance

- **Duration:** 18 min
- **Started:** 2026-05-14T09:09:40Z
- **Completed:** 2026-05-14T09:28:04Z
- **Tasks:** 2
- **Files modified:** 17

## Accomplishments
- Built workspace.py helper enabling per-request space_id resolution via LangGraph's configurable mechanism
- Implemented CircuitBreaker state machine (CLOSED/OPEN/HALF_OPEN) and ResilientClient with exponential backoff retry
- Migrated api_parser from sync `requests` to async `httpx.AsyncClient` for non-blocking spec fetching
- Refactored all three agents (web, api, testcase) to use dynamic workspace paths instead of module-level hardcoded paths
- Migrated existing workspace data to `workspace/default/` subdirectory structure

## Task Commits

Each task was committed atomically:

1. **Task 1: Create workspace helper, resilience module, and test suite** - `5148ec9` (feat) -- TDD approach
2. **Task 2: Refactor agent backends, migrate api_parser, migrate data** - `5c3da0c` (feat)
3. **Gitignore and workspace file tracking** - `80f7a34` (chore)

## Files Created/Modified
- `src/app/core/workspace.py` - get_space_id() and get_workspace_dir() helpers for multi-space isolation
- `src/app/core/config.py` - Added resilience settings (circuit_breaker_fail_max, reset_timeout, retry params)
- `src/app/resilient/__init__.py` - ResilientClient wrapping httpx.AsyncClient with retry + circuit breaker
- `src/app/resilient/circuit_breaker.py` - CircuitBreaker state machine with CircuitOpenError
- `src/app/agents/api/tools/api_parser.py` - Migrated from sync requests to async httpx
- `src/app/agents/api/tools/__init__.py` - Dynamic workspace via get_workspace_dir, async parse_openapi_spec tool
- `src/app/agents/web/tools.py` - Dynamic workspace via get_space_id/get_workspace_dir
- `src/app/agents/web/agent.py` - Removed output_root import, updated system prompt
- `src/app/agents/testcase/agent.py` - Dynamic workspace via get_workspace_dir
- `tests/test_workspace.py` - 6 tests for workspace resolution and isolation
- `tests/test_resilient.py` - 7 tests for circuit breaker and ResilientClient
- `tests/test_api_tools.py` - Updated for async parse_api_spec and new workspace paths
- `tests/test_api_skills.py` - Updated workspace path to workspace/default/api/skills
- `tests/test_web_agent.py` - Removed output_root import
- `tests/test_web_skills.py` - Updated workspace path to workspace/default/web/skills
- `.gitignore` - Updated for workspace/default/ structure
- `workspace/default/` - Migrated web/, api/, testcase/ directories

## Decisions Made
- Graph-level backends remain static with "default" workspace path; tool functions resolve workspace dynamically via get_space_id() at call time. This preserves DeepAgents compile-time backend binding while enabling per-request isolation.
- Custom circuit breaker implementation (~80 lines) instead of aiobreaker dependency -- trivial state machine logic, no need for external library.
- System prompt for web agent now references ensure_output_dir tool instead of hardcoded output_root paths, enabling dynamic workspace resolution.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated httpx.Response mock for raise_for_status()**
- **Found during:** Task 1 (TDD GREEN phase - test_retry_on_timeout)
- **Issue:** Mock httpx.Response(200) without a request object causes RuntimeError in raise_for_status()
- **Fix:** Created _make_response() helper that builds httpx.Response with proper request object
- **Files modified:** tests/test_resilient.py
- **Verification:** All 13 new tests pass
- **Committed in:** 5148ec9 (Task 1 commit)

**2. [Rule 3 - Blocking] Updated existing tests for workspace migration and async api_parser**
- **Found during:** Task 2 (refactoring)
- **Issue:** Existing tests referenced old workspace paths (workspace/api, workspace/web) and called parse_api_spec synchronously
- **Fix:** Updated test_api_skills.py, test_web_skills.py workspace paths; made test_api_tools.py parse tests async; updated test_web_agent.py import; updated test_api_tools.py workspace_dir assertion
- **Files modified:** tests/test_api_skills.py, tests/test_web_skills.py, tests/test_api_tools.py, tests/test_web_agent.py
- **Verification:** All 198 tests pass (185 existing + 13 new)
- **Committed in:** 5c3da0c (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 blocking issues)
**Impact on plan:** Both auto-fixes were necessary follow-ups from planned changes. No scope creep.

## Issues Encountered
None beyond the deviations documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Workspace helper ready for Plan 02 (frontend workspace selector + configurable propagation)
- ResilientClient ready for wrapping MCP server calls in future phases
- All 198 tests passing, workspace data migrated to default/ structure

---
*Phase: 07-multi-workspace-infrastructure-hardening*
*Completed: 2026-05-14*

## Self-Check: PASSED
- All 5 key files verified present
- All 3 commits verified in git log
- 198 tests passing, 0 failures
