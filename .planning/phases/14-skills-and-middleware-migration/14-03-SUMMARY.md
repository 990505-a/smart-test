---
phase: 14-skills-and-middleware-migration
plan: 03
subsystem: agent-middleware
tags: [deepagents, middleware, context-injection, error-handling, web-agent, asynccontextmanager]

# Dependency graph
requires:
  - phase: 14-01
    provides: "Web agent agent.py with SkillsMiddleware and CompositeBackend"
provides:
  - "WebContextInjectionMiddleware class for injecting project_identifier and folder_id into system prompt"
  - "Tool error handler (wrap_tool_with_error_handling / wrap_tools_with_error_handling) for Web agent"
  - "WebAgentContext dataclass with project_identifier, folder_id, current_user_id"
  - "make_agent() asynccontextmanager factory pattern for Web agent"
affects: [15-web-agent-playwright-mcp]

# Tech tracking
tech-stack:
  added: []
  patterns: [asynccontextmanager-agent-factory, onion-middleware-web, tool-error-json-return]

key-files:
  created:
    - src/app/agents/web/middleware/__init__.py
    - src/app/agents/web/middleware/context_injection.py
    - src/app/agents/web/middleware/tool_error_handler.py
  modified:
    - src/app/agents/web/agent.py

key-decisions:
  - "Default tool_patterns=None in wrap_tools_with_error_handling wraps ALL tools (Web agent tools frequently fail)"
  - "WebAgentContext uses DEFAULT_USER_ID pattern matching API agent"
  - "make_agent() asynccontextmanager prepares for Playwright MCP lifecycle in Phase 15"

patterns-established:
  - "Asynccontextmanager factory for agent creation (matches API agent pattern)"
  - "JSON tuple error return pattern (content, artifact) from wrapped tools"
  - "Runtime context injection via AgentMiddleware awrap_model_call"

requirements-completed: [WEB-MCP-MIDW-01, WEB-MCP-MIDW-02]

# Metrics
duration: 2min
completed: 2026-05-21
---

# Phase 14 Plan 03: Web Agent Middleware Summary

**WebContextInjectionMiddleware and ToolErrorHandler added to Web agent with asynccontextmanager make_agent() factory and WebAgentContext schema**

## Performance

- **Duration:** 2 min
- **Started:** 2026-05-21T05:57:16Z
- **Completed:** 2026-05-21T05:59:39Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- WebContextInjectionMiddleware injects project_identifier and folder_id into system prompt at runtime
- Tool error handler wraps all tools so errors become JSON messages instead of crashes
- Web agent changed from module-level agent variable to make_agent() asynccontextmanager factory
- WebAgentContext dataclass registered as context_schema with create_deep_agent

## Task Commits

Each task was committed atomically:

1. **Task 1: Create middleware package with ContextInjection and ToolErrorHandler** - `68404a8` (feat)
2. **Task 2: Wire middleware into Web agent with context_schema** - `856e926` (feat)

## Files Created/Modified
- `src/app/agents/web/middleware/__init__.py` - Package exports for WebContextInjectionMiddleware and wrap_tools_with_error_handling
- `src/app/agents/web/middleware/context_injection.py` - WebContextInjectionMiddleware class that injects runtime context into system prompt
- `src/app/agents/web/middleware/tool_error_handler.py` - Tool error wrapping with JSON return pattern for _run and _arun
- `src/app/agents/web/agent.py` - Updated with make_agent() factory, WebAgentContext, middleware wiring

## Decisions Made
- Default tool_patterns=None wraps ALL tools for Web agent (browser automation tools frequently encounter errors that should not crash the agent)
- WebAgentContext uses same DEFAULT_USER_ID pattern as API agent for consistency
- make_agent() asynccontextmanager pattern prepares for Playwright MCP lifecycle management in Phase 15

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Web agent middleware infrastructure ready for Phase 15 (Playwright MCP upgrade)
- make_agent() asynccontextmanager ready to wrap MCP client session lifecycle
- Tool error handler will be critical when browser automation tools are added in Phase 15

---
*Phase: 14-skills-and-middleware-migration*
*Completed: 2026-05-21*
