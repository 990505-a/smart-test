---
phase: 15-web-agent-playwright-mcp-upgrade
plan: 02
subsystem: web-agent
tags: [playwright, mcp, agent, langchain_mcp_adapters, deepagents]
dependency_graph:
  requires:
    - phase: 15-01
      provides: [WEB_AGENT_TOOLS, composite_backend, file_backend, web_mcp_root_resolved]
    - phase: 14
      provides: [WebContextInjectionMiddleware, wrap_tools_with_error_handling, 8 web_mcp skills]
  provides:
    - make_agent asynccontextmanager with Playwright MCP session lifecycle
    - 4-workflow system prompt replacing dual-mode prompt
    - Targeted error handling for browser_/playwright-test/ tools
    - validate_agent.py updated for tools package structure
  affects: [web-agent-creation, langgraph-api, frontend-chat]
tech_stack:
  added: ["langchain_mcp_adapters (MultiServerMCPClient, load_mcp_tools)"]
  patterns: ["Session-level MCP pattern (client.session vs client-level)", "Targeted tool error wrapping by name prefix"]
key_files:
  created: []
  modified:
    - src/app/agents/web/agent.py
    - src/app/agents/web/validate_agent.py
  deleted: []
decisions:
  - "Session-level MCP pattern (async with client.session) for persistent browser state, not client-level load_mcp_tools"
  - "Targeted error wrapping only for browser_ and playwright-test/ prefixed tools, not all tools"
  - "No graceful degradation -- Playwright MCP failure means agent cannot function (needs browser tools)"
  - "SkillsMiddleware uses composite_backend instead of file_backend for full routing"
patterns-established:
  - "Session-level MCP: client.session(name) + load_mcp_tools(session) for stateful MCP servers"
  - "MCP tools first, local tools second: mcp_tools + WEB_AGENT_TOOLS"
requirements-completed: [WEB-MCP-05, WEB-MCP-06, WEB-MCP-07, WEB-MCP-08]
metrics:
  duration: 5min
  tasks: 2
  files: 2
  completed: 2026-05-21
---

# Phase 15 Plan 02: Playwright MCP Agent Rewrite Summary

Session-level Playwright MCP integration with 4-workflow Chinese system prompt, targeted browser tool error handling, and 128k context LLM configuration.

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-21T10:10:55Z
- **Completed:** 2026-05-21T10:16:15Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Rewrote agent.py with full Playwright MCP integration using session-level pattern
- Replaced dual-mode system prompt with classroom 4-workflow Chinese prompt (generate, create, execute, heal)
- Configured targeted error handling wrapping only browser_/playwright-test/ prefixed tools
- Updated validate_agent.py for new tools package structure with 5-check validation suite

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite agent.py with Playwright MCP integration** - `83c67bc` (feat)
2. **Task 2: Fix validate_agent.py file_backend attribute check** - `4f47a54` (fix)

## Files Created/Modified
- `src/app/agents/web/agent.py` - Complete rewrite: MCP session lifecycle, 4-workflow prompt, targeted error handling
- `src/app/agents/web/validate_agent.py` - Updated for tools package structure, 5-check validation suite

## Decisions Made
- Session-level MCP pattern (`async with client.session("web_mcp")`) chosen over client-level (`load_mcp_tools(client, server_name=...)`) because Playwright Test MCP requires persistent browser state across tool calls
- Targeted error wrapping (only `browser_` and `playwright-test/` tools) instead of wrapping all tools, since local DB/file tools rarely fail and should propagate errors normally
- No graceful degradation fallback -- if Playwright MCP server fails, the agent cannot function as it requires browser tools
- SkillsMiddleware uses `composite_backend` (not `file_backend`) so shell execute routing works for skill file operations

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] validate_agent.py referenced non-existent file_backend.root_dir**
- **Found during:** Task 2 (smoke test)
- **Issue:** validate_agent.py check 3 tried to print `file_backend.root_dir` which does not exist as a public attribute on FilesystemBackend
- **Fix:** Replaced with `file_backend.ls("/")` check that verifies the backend is functional
- **Files modified:** src/app/agents/web/validate_agent.py
- **Verification:** All 5 validation checks pass
- **Committed in:** 4f47a54

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor fix to validation script. No scope creep.

## Verification Results

```
Import chain (make_agent, SYSTEM_PROMPT, WebAgentContext) -> PASS
WEB_AGENT_TOOLS count -> 18 tools
System prompt contains planner_setup_page, browser_snapshot, save_web_test_plan, healer -> PASS
MCP pattern (MultiServerMCPClient, client.session, load_mcp_tools(session)) -> PASS
Error targeting (browser_, playwright-test/) -> PASS
validate_agent.py all 5 checks -> PASS
```

## Next Phase Readiness
- Web agent fully integrated with Playwright MCP for real browser control
- Phase 16 can now build frontend pages and backend endpoints that invoke this agent
- Requires `npx playwright run-test-mcp-server` to be available in workspace/default/web/ for live testing

## Self-Check: PASSED

All 2 modified files exist on disk. Both commits (83c67bc, 4f47a54) found in git log.

---
*Phase: 15-web-agent-playwright-mcp-upgrade*
*Completed: 2026-05-21*
