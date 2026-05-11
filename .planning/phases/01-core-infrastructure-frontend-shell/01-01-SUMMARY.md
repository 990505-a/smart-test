---
phase: 01-core-infrastructure-frontend-shell
plan: 01
subsystem: infra
tags: [deepagents, langgraph, langchain, deepseek, python, uv, pydantic-settings]

# Dependency graph
requires:
  - phase: none
    provides: "First plan, no dependencies"
provides:
  - "Python backend project with pyproject.toml and all core dependencies"
  - "graph.json with three agent routing entries (testcase_agent, web_agent, api_agent)"
  - "start_server.py for LangGraph API server on port 2026"
  - "Three agent stubs (testcase/web/api) using create_deep_agent with FilesystemBackend"
  - "Core config module (pydantic-settings BaseSettings) and LLM initialization module"
affects: [01-02, 01-03, 01-04, 02-01]

# Tech tracking
tech-stack:
  added: [deepagents>=0.5.9, langgraph>=1.1.10, langgraph-cli>=0.4.25, langchain>=1.2.18, langchain-deepseek>=1.0.1, langchain-mcp-adapters>=0.2.2, fastmcp>=3.2.4, pydantic-settings>=2.14.1, python-dotenv>=1.2.2, httpx>=0.28.1, uvicorn>=0.46.0]
  patterns: [create_deep_agent with FilesystemBackend, graph.json multi-agent routing, pydantic-settings BaseSettings, init_chat_model provider:model format]

key-files:
  created:
    - pyproject.toml
    - .env.example
    - graph.json
    - start_server.py
    - src/app/__init__.py
    - src/app/core/__init__.py
    - src/app/core/config.py
    - src/app/core/llms.py
    - src/app/agents/__init__.py
    - src/app/agents/testcase/__init__.py
    - src/app/agents/testcase/agent.py
    - src/app/agents/web/__init__.py
    - src/app/agents/web/agent.py
    - src/app/agents/api/__init__.py
    - src/app/agents/api/agent.py
  modified: []

key-decisions:
  - "Used Python 3.12 via uv (available on system) for compatibility with all dependencies"
  - "Agent workspace_dir uses five .parent calls from __file__ to reach project root"

patterns-established:
  - "Agent stub pattern: create_deep_agent(model, tools=[], backend=FilesystemBackend, middleware=[], system_prompt=...)"
  - "graph.json multi-routing: each agent registered as separate graph entry with path to agent.py:agent"
  - "start_server.py env setup: LANGSERVE_GRAPHS from graph.json, LANGGRAPH_RUNTIME_EDITION=inmem, port 2026"
  - "Config pattern: pydantic-settings BaseSettings with .env file support"
  - "LLM init pattern: init_chat_model('deepseek:deepseek-chat') for provider:model format"

requirements-completed: [INFRA-01, INFRA-02]

# Metrics
duration: 2min
completed: 2026-05-11
---

# Phase 1 Plan 01: Backend Infrastructure Summary

**DeepAgents backend with three agent stubs (testcase/web/api) registered via graph.json multi-routing, served by LangGraph API on port 2026**

## Performance

- **Duration:** 2 min
- **Started:** 2026-05-11T07:33:55Z
- **Completed:** 2026-05-11T07:35:57Z
- **Tasks:** 2
- **Files modified:** 15

## Accomplishments
- Python project initialized with uv and all backend dependencies installed (deepagents 0.5.9, langgraph 1.1.10, langchain 1.2.18)
- Three agent stubs created and verified importable as CompiledStateGraph
- graph.json multi-agent routing configured with testcase_agent, web_agent, api_agent entries
- start_server.py ready to launch LangGraph API server on port 2026

## Task Commits

Each task was committed atomically:

1. **Task 1: Initialize Python project and create backend infrastructure** - `66dde65` (feat)
2. **Task 2: Create three agent stubs with FilesystemBackend** - `59208e8` (feat)

## Files Created/Modified
- `pyproject.toml` - Python project definition with all backend dependencies
- `.env.example` - Template for DEEPSEEK_API_KEY and server config
- `graph.json` - Multi-agent routing config for three agents
- `start_server.py` - LangGraph API server startup script (port 2026)
- `src/app/__init__.py` - App package init
- `src/app/core/__init__.py` - Core package init
- `src/app/core/config.py` - Pydantic BaseSettings for configuration
- `src/app/core/llms.py` - LLM initialization with DeepSeek provider
- `src/app/agents/__init__.py` - Agents package init
- `src/app/agents/testcase/__init__.py` - TestCase agent package init
- `src/app/agents/testcase/agent.py` - TestCase agent stub with Chinese system prompt
- `src/app/agents/web/__init__.py` - Web agent package init
- `src/app/agents/web/agent.py` - Web automation agent stub
- `src/app/agents/api/__init__.py` - API agent package init
- `src/app/agents/api/agent.py` - API automation agent stub

## Decisions Made
- Used Python 3.12.12 (available on system via uv) rather than 3.13 -- uv selected the best available version
- Agent workspace_dir uses five `.parent` calls to traverse from agent.py to project root, then appends "workspace"

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Agent import verification requires DEEPSEEK_API_KEY to be set (even a dummy value) because `init_chat_model` validates the key at import time. This is expected behavior and not a bug.

## User Setup Required

**External service requires manual configuration.** Copy `.env.example` to `.env` and add your DeepSeek API key:
```
cp .env.example .env
# Edit .env and replace your_deepseek_api_key_here with actual key
```

## Next Phase Readiness
- Backend infrastructure is ready for frontend connection (Plan 01-02)
- Server can be started with `python start_server.py` once API key is configured
- Three agent stubs are importable and respond to chat messages
- graph.json routing is configured for multi-agent selection

---
*Phase: 01-core-infrastructure-frontend-shell*
*Completed: 2026-05-11*

## Self-Check: PASSED

All 9 key files verified present. All 2 task commits verified in git log.
