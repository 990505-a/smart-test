---
phase: 14-skills-and-middleware-migration
plan: 02
subsystem: middleware
tags: [deepagents, middleware, context-injection, tool-error-handler, api-agent]

requires:
  - phase: 14-skills-and-middleware-migration
    plan: 01
    provides: API and Web skills in workspace

provides:
  - APIContextInjectionMiddleware for injecting runtime context into system prompt
  - Tool error handler wrapping all API agent tools with JSON error returns
  - APIAgentContext dataclass for context_schema registration
  - Updated make_agent() with middleware chain and context_schema

affects: [15-web-agent-playwright-mcp-upgrade, agent-middleware, runtime-context]

tech-stack:
  added: []
  patterns: [context-injection-middleware, tool-error-wrapping, dataclass-context-schema]

key-files:
  created:
    - src/app/agents/api/middleware/__init__.py
    - src/app/agents/api/middleware/context_injection.py
    - src/app/agents/api/middleware/tool_error_handler.py
  modified:
    - src/app/agents/api/agent.py

key-decisions:
  - "Used getattr with defaults for safe context attribute access (no context_schema yet at middleware level)"
  - "English comments and no emoji in injected text matching codebase style"
  - "Tuple return format (content, artifact) for response_format compatibility"
  - "wrap_tools_with_error_handling wraps all tools by default (tool_patterns=None)"

patterns-established:
  - "Context injection via AgentMiddleware.awrap_model_call with safe getattr pattern"
  - "Tool error wrapping via _run/_arun replacement returning JSON error info"
  - "Middleware order: [skills_middleware, context_middleware] (Skills outer, Context inner)"

requirements-completed: [API-02, API-13, MIDW-CTX-01, MIDW-ERR-01]

duration: 2min
completed: 2026-05-21
---

# Phase 14 Plan 02: API Agent Middleware Summary

**ContextInjection + ToolErrorHandler middleware wired into API agent with APIAgentContext dataclass for runtime parameter injection**

## Performance

- **Duration:** 2 min
- **Started:** 2026-05-21T05:57:31Z
- **Completed:** 2026-05-21T05:59:36Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Created middleware package with APIContextInjectionMiddleware that injects project_identifier and folder_id into system prompt
- Created tool error handler that wraps tool _run/_arun methods to return structured JSON errors instead of raising exceptions
- Added APIAgentContext dataclass with project_identifier, folder_id, current_user_id
- Wired middleware into make_agent() with correct order: [skills_middleware, context_middleware]
- Registered context_schema=APIAgentContext with create_deep_agent

## Task Commits

Each task was committed atomically:

1. **Task 1: Create middleware package with ContextInjection and ToolErrorHandler** - `68404a8` (feat)
2. **Task 2: Wire middleware into API agent with context_schema** - `856e926` (feat)

## Files Created/Modified

### Created
- `src/app/agents/api/middleware/__init__.py` - Package exports (APIContextInjectionMiddleware, wrap_tools_with_error_handling)
- `src/app/agents/api/middleware/context_injection.py` - APIContextInjectionMiddleware class with safe attribute access
- `src/app/agents/api/middleware/tool_error_handler.py` - wrap_tool_with_error_handling and wrap_tools_with_error_handling functions

### Modified
- `src/app/agents/api/agent.py` - Added imports, APIAgentContext dataclass, tool wrapping, middleware chain, context_schema

## Decisions Made
- Used getattr with defaults for safe context attribute access (handles missing runtime context gracefully)
- English comments and no emoji in injected context text (cleaner than classroom version)
- Tuple return format (content, artifact) for response_format='content_and_artifact' compatibility
- wrap_tools_with_error_handling wraps all tools by default (tool_patterns=None matches classroom pattern)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- API agent now has full middleware stack: SkillsMiddleware + APIContextInjectionMiddleware
- Tool error handling prevents agent crashes from tool exceptions
- context_schema=APIAgentContext enables frontend to inject runtime parameters
- Ready for 14-03 which adds the same middleware to the Web agent

---
*Phase: 14-skills-and-middleware-migration*
*Completed: 2026-05-21*

## Self-Check: PASSED

All 4 files verified present. Both task commits (68404a8, 856e926) verified in git log.
