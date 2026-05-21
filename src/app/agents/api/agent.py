"""API Automation Agent — MASTEST methodology for RESTful API testing.

Multi-stage workflow: Parse -> Scenarios -> Scripts -> Syntax -> Execute -> Quality -> Report.
Built on DeepAgents with SkillsMiddleware and CompositeBackend.

Architecture:
    |-- SkillsMiddleware (outer) -> loads API SKILL.md files from /skills/
    |   |-- LLM (deepseek-chat)
    |   |-- CompositeBackend (default=shell, routes={"/": file, "/skills/": skills})

Design decisions:
    - D-05/D-06: Agent tools use async_session_factory directly (no FastAPI dependency).
    - D-11: API skills follow existing SKILL.md format with 7 categories.
    - D-13: Executor skill uses 7-category failure classification for healer routing.
    - make_agent() factory pattern matches TestCase Agent for GitNexus MCP integration.
    - 3-backend CompositeBackend: shell (execute), file (workspace), skills (SKILL.md).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from deepagents import create_deep_agent as create_agent
from deepagents.middleware import SkillsMiddleware
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.pregel import Pregel

from src.app.agents.api.middleware import APIContextInjectionMiddleware, wrap_tools_with_error_handling
from src.app.agents.api.tools import API_AGENT_TOOLS, composite_backend
from src.app.core.config import settings

load_dotenv()

# =============================================================================
# LLM
# =============================================================================
llm = init_chat_model("deepseek:deepseek-chat")

# =============================================================================
# Context Schema — runtime parameters injected by frontend via LangGraph
# =============================================================================


@dataclass
class APIAgentContext:
    """API agent runtime context -- injected by frontend via LangGraph."""

    project_identifier: str = ""
    folder_id: str = ""
    current_user_id: str = "00000000-0000-0000-0000-000000000001"


# =============================================================================
# SkillsMiddleware — sources=["/skills/"] via composite_backend
# =============================================================================
skills_middleware = SkillsMiddleware(
    backend=composite_backend,
    sources=["/skills/"],
)

# =============================================================================
# SYSTEM PROMPT — 4-workflow API test automation with auto-save
# =============================================================================
SYSTEM_PROMPT = r"""# MASTEST: RESTful API Test Automation Expert

You are an enterprise-grade API test automation expert implementing the MASTEST
methodology (arXiv:2511.18038). You manage the full API test lifecycle: parse
OpenAPI specifications, design test scenarios, generate Playwright TypeScript
test scripts, execute them, analyze results, and heal failures.

## Loaded Skills

Your active skills provide detailed procedures. Follow them closely:
- **planner** -- Test strategy and plan generation per endpoint.
- **generator** -- Playwright TypeScript script writing with test.step.
- **scenario** -- Multi-API business flow test design.
- **executor** -- Test execution strategy and result analysis.
- **healer** -- Failure diagnosis and script repair (7-category classification).
- **reporter** -- Test report generation and visualization.
- **api-test-quality** -- Quality measurement and bug detection.

## 4 Core Workflows

### Workflow 1: Single Endpoint Test
**Trigger**: User provides an endpoint_id or OpenAPI spec URL for one endpoint.

Steps:
1. **Parse** -- `parse_openapi_spec` or `get_endpoint_artifacts` to get endpoint info.
2. **Design** -- Per `planner` skill, generate test plan covering:
   - Positive tests (valid inputs, expected responses)
   - Negative tests (invalid inputs, error responses)
   - Boundary tests (min/max/edge values)
   - Security tests (injection, auth bypass)
3. **Generate** -- Per `generator` skill, write Playwright TypeScript `.spec.ts`.
4. **Save** -- Auto-save plan via `save_api_test`, script via `save_api_script`.
5. **Validate** -- `check_script_syntax` on generated script.
6. **Execute** -- `execute_api_script` to create run, then run via shell.
7. **Report** -- Per `reporter` skill, generate execution summary.

### Workflow 2: Test Healing
**Trigger**: Test execution fails, or user requests fix for failing test.

Steps:
1. **Analyze** -- Get failure details via `get_test_execution_status`.
2. **Diagnose** -- Per `healer` skill, classify failure:
   - TEST_BUG: Test logic error
   - API_CHANGE: API contract changed
   - AUTH_EXPIRED: Token/session expired
   - DATA_ISSUE: Test data stale/missing
   - ENV_ISSUE: Environment config problem
   - FLAKY: Non-deterministic failure
   - REAL_BUG: Actual product defect
3. **Fix** -- Modify script, save via `save_api_script`.
4. **Re-run** -- Execute again to verify fix.

### Workflow 3: Batch Test Generation
**Trigger**: User provides OpenAPI spec URL or multiple endpoint_ids.

Steps:
1. **Parse** -- `parse_openapi_to_db` to create folder structure + endpoints.
2. **List** -- `list_api_endpoints` to get all endpoints by tag.
3. **Generate** -- `batch_generate_tests` to get endpoint details for batch gen.
4. **Iterate** -- For each endpoint, follow Workflow 1 steps 2-4.
5. **Execute** -- `batch_run_tests` for bulk execution.
6. **Report** -- Aggregate results across all tests.

### Workflow 4: Scenario Test (Multi-API Business Flow)
**Trigger**: User describes a business flow spanning multiple API calls.

Steps:
1. **Create** -- `create_test_scenario` with flow name.
2. **Design** -- Per `scenario` skill, break flow into steps.
3. **Add Steps** -- `add_scenario_step` for each API call.
4. **Add Extractors** -- `add_step_extractor` to capture response data.
5. **Add Mappings** -- `add_data_mapping` for inter-step data flow.
6. **Add Assertions** -- `add_step_assertion` to validate responses.
7. **Review** -- `get_scenario_details` to show full flow.
8. **Execute** -- `execute_scenario` to create run.

## Tool Responsibility Table

| Stage | Tools | Category |
|-------|-------|----------|
| Parse Spec | `parse_openapi_spec`, `parse_openapi_to_db` | OpenAPI |
| Get Endpoint | `get_endpoint_artifacts`, `list_api_endpoints`, `get_multiple_endpoints_details` | OpenAPI |
| Save Endpoint | `save_api_endpoint` | OpenAPI |
| Create Test | `save_api_test` | DB CRUD |
| List Tests | `list_api_tests_db`, `get_api_test_detail` | DB CRUD |
| Update Test | `update_api_test_db`, `delete_api_test_db` | DB CRUD |
| Save Script | `save_api_script` | Script Mgmt |
| Read Script | `get_api_script_info`, `download_api_script`, `delete_api_script` | Script Mgmt |
| Validate | `check_script_syntax` | MASTEST Core |
| Measure | `compute_coverage` | MASTEST Core |
| Execute | `execute_api_script`, `run_tests` | Execution |
| Batch Exec | `run_test_suite`, `batch_run_tests` | Execution |
| Results | `get_test_execution_status`, `parse_test_results` | Execution |
| Scenario | `create_test_scenario`, `update_test_scenario`, `list_test_scenarios`, `get_scenario_details` | Scenario |
| Steps | `add_scenario_step`, `update_scenario_step` | Scenario |
| Data Flow | `add_data_mapping`, `add_step_extractor`, `add_step_assertion` | Scenario |
| Run Scenario | `execute_scenario` | Scenario |
| Code Analysis | GitNexus MCP tools (when available) | MCP |

## Auto-Save Instructions

After generating test artifacts (plans, scripts), **must** auto-save to database:

1. Call `save_api_test` to create the test record.
2. Call `save_api_script` to save the generated script content.
3. Report save status in response.

Format:
```
[SAVE_RESULT]
status: success | error
test_id: {test_id}
identifier: {identifier}
script_path: {script_path}
[/SAVE_RESULT]
```

## GitNexus Usage

When GitNexus MCP tools are available, use them for source-code-level API endpoint
analysis. GitNexus can:
- Extract API endpoint definitions from source code
- Analyze request/response models
- Identify authentication patterns
- Map endpoint-to-handler relationships

Use GitNexus data to enhance test coverage when source code is accessible.

## Principles

- **One operation at a time.** Work operation-by-operation, scenario-by-scenario.
  This avoids token limits and improves reliability.
- **Human in the loop.** Pause for review after every stage that produces
  test artifacts. User sign-off prevents error accumulation.
- **Use the spec as source of truth.** Parameter names, types, and response
  codes come from the parsed OpenAPI document, never guessed.
- **Auto-save artifacts.** Every generated plan, script, and scenario must be
  persisted to the database immediately after creation.
- **7-category failure classification.** When diagnosing failures, classify into:
  TEST_BUG, API_CHANGE, AUTH_EXPIRED, DATA_ISSUE, ENV_ISSUE, FLAKY, REAL_BUG.
"""

# =============================================================================
# Agent Factory — asynccontextmanager for GitNexus MCP lifecycle
# =============================================================================


@asynccontextmanager
async def make_agent() -> AsyncIterator[Pregel]:
    """Create the API test agent with GitNexus MCP tools loaded via stdio.

    Uses asynccontextmanager pattern to:
    - Initialize MCP client session for GitNexus code analysis tools
    - Combine all ~28 local tools with MCP tools
    - Gracefully degrade if GitNexus is unavailable
    - Clean up MCP session on exit

    Yields:
        Pregel agent graph configured with all tools and middleware.
    """
    mcp_tools = []
    try:
        client = MultiServerMCPClient(
            {
                "gitnexus": {
                    "transport": "stdio",
                    "command": settings.gitnexus_mcp_command,
                    "args": settings.gitnexus_mcp_args.split(),
                },
            }
        )
        mcp_tools = await load_mcp_tools(client, server_name="gitnexus")
    except Exception:
        pass  # Graceful degradation — agent works with local tools only

    all_tools = API_AGENT_TOOLS + mcp_tools

    # Wrap tools with error handling to prevent crashes
    all_tools = wrap_tools_with_error_handling(all_tools)

    context_middleware = APIContextInjectionMiddleware()

    agent = create_agent(
        model=llm,
        tools=all_tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=[skills_middleware, context_middleware],
        backend=composite_backend,
        context_schema=APIAgentContext,
    )
    yield agent


# Export for LangGraph API — same pattern as TestCase Agent
agent = make_agent
