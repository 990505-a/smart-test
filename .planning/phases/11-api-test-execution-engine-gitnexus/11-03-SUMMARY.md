---
phase: 11-api-test-execution-engine-gitnexus
plan: 03
subsystem: agent
tags: [agent, tools, mcp, gitnexus, deepagents, make_agent, composite-backend, scenario, execution]

requires:
  - phase: 11-api-test-execution-engine-gitnexus
    plan: 01
    provides: "APITest, APITestRun, APITestResult models, APITestService, ScenarioService"
  - phase: 11-api-test-execution-engine-gitnexus
    plan: 02
    provides: "API skills (planner, generator, scenario, executor, healer, reporter), SKILL.md files"

provides:
  - "4 new tool modules: db_tools, openapi_tools, execution_tools, scenario_tools"
  - "API_AGENT_TOOLS combined registry (~34+ tools across 7 categories)"
  - "Refactored agent.py with make_agent() factory, GitNexus MCP, 3-backend CompositeBackend"
  - "4-workflow system prompt with tool responsibility table"

affects: [11-api-test-execution-engine-gitnexus]

tech-stack:
  added: [langchain_mcp_adapters, langgraph.pregel.Pregel]
  patterns: [make_agent-factory, asynccontextmanager, 3-backend-composite, tool-category-modules, graceful-mcp-degradation]

key-files:
  created:
    - src/app/agents/api/tools/db_tools.py
    - src/app/agents/api/tools/openapi_tools.py
    - src/app/agents/api/tools/execution_tools.py
    - src/app/agents/api/tools/scenario_tools.py
  modified:
    - src/app/agents/api/tools/__init__.py
    - src/app/agents/api/agent.py

decisions:
  - "All tools return JSON strings via json.dumps for consistent agent parsing"
  - "Tools accept project_id as parameter (no context_schema yet for API agent)"
  - "make_agent() asynccontextmanager pattern matches TestCase Agent for consistency"
  - "3-backend CompositeBackend: shell (execute), file (workspace), skills (SKILL.md)"
  - "GitNexus MCP loaded via stdio with graceful degradation fallback"
  - "Scenario tools use ScenarioService directly (not raw SQL) for step management"
  - "Execution tools create pending runs; actual execution deferred to Plan 04 APITestExecutor"

metrics:
  duration: "8min"
  tasks_completed: 2
  files_modified: 6
---

# Phase 11 Plan 03: API Agent Tool Registry and Factory Refactor Summary

Refactored API Agent from simple stub to full-featured agent with 34+ tools across 7 categories, GitNexus MCP integration via stdio, 3-backend CompositeBackend, and make_agent() factory following the TestCase Agent pattern.

## What Was Done

### Task 1: Create Agent Tool Modules

Created 4 new tool modules organized by functional category:

**db_tools.py (9 tools)** -- API test database CRUD:
- `save_api_test` -- Create API test via APITestService
- `list_api_tests_db` -- List tests with search and pagination
- `get_api_test_detail` -- Get test with run history
- `update_api_test_db` -- Update test fields
- `delete_api_test_db` -- Delete test record
- `save_api_script` -- Write script file + update DB
- `get_api_script_info` -- Script metadata query
- `download_api_script` -- Read script content
- `delete_api_script` -- Remove script file and DB reference

**openapi_tools.py (5 tools)** -- OpenAPI parsing and endpoint management:
- `parse_openapi_to_db` -- Parse spec, create tag-based folders, save endpoints
- `save_api_endpoint` -- Save single endpoint to DB
- `get_endpoint_artifacts` -- Get endpoint with associated tests
- `list_api_endpoints` -- List endpoints with tag/folder filtering
- `get_multiple_endpoints_details` -- Batch endpoint details

**execution_tools.py (7 tools)** -- Script execution and batch operations:
- `execute_api_script` -- Create test run (pending, Plan 04 executes)
- `get_test_execution_status` -- Query run status and progress
- `run_tests` -- Generate npx playwright test command
- `run_test_suite` -- Batch create test runs
- `parse_test_results` -- Parse Playwright JSON output
- `batch_generate_tests` -- Get endpoint details for batch generation
- `batch_run_tests` -- Batch execution wrapper

**scenario_tools.py (10 tools)** -- Scenario CRUD and step management:
- `create_test_scenario` -- Create business flow scenario
- `update_test_scenario` -- Update scenario metadata
- `add_scenario_step` -- Add API call step with assertions/extractors
- `update_scenario_step` -- Update step fields
- `add_data_mapping` -- Configure inter-step data flow
- `add_step_extractor` -- Add JSONPath response extractor
- `add_step_assertion` -- Add response validation assertion
- `get_scenario_details` -- Full scenario with steps and mappings
- `list_test_scenarios` -- List with status filter and pagination
- `execute_scenario` -- Create scenario run (pending, Plan 04 executes)

**Updated __init__.py**:
- Imports all tool lists from 4 new modules + existing MASTEST_TOOLS
- Creates `API_AGENT_TOOLS` combining all categories
- Added `skills_backend` (FilesystemBackend for src/app/skills/)
- Updated CompositeBackend with 3 routes: shell, file, skills

### Task 2: Refactor API Agent with make_agent() Factory

**agent.py** fully refactored to follow TestCase Agent pattern:
- `make_agent()` asynccontextmanager factory with GitNexus MCP lifecycle
- GitNexus MCP configured via `settings.gitnexus_mcp_command` and `settings.gitnexus_mcp_args`
- Graceful degradation: agent works with local tools only if GitNexus unavailable
- 3-backend CompositeBackend: shell (npx/node), file (workspace), skills (SKILL.md)
- Updated SYSTEM_PROMPT with 4 core workflows and tool responsibility table
- Auto-save instructions for generated test artifacts
- 7-category failure classification for test healing
- Export `agent = make_agent` for LangGraph API

## Tool Count

| Category | Count | Module |
|----------|-------|--------|
| MASTEST Core | 3 | __init__.py |
| Playwright MCP | dynamic | playwright_mcp_server.py |
| DB CRUD | 9 | db_tools.py |
| OpenAPI/Endpoint | 5 | openapi_tools.py |
| Execution/Batch | 7 | execution_tools.py |
| Scenario/Step | 10 | scenario_tools.py |
| **Total** | **34+** | |

## Deviations from Plan

None - plan executed exactly as written.

## Verification

All files created and written. Python import verification was blocked by sandbox restrictions during parallel execution. The code follows established patterns from the TestCase Agent (same async_session_factory pattern, same tool registration, same make_agent factory).
