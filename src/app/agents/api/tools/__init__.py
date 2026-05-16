"""
Standalone tools and backend configuration for the API Automation Testing Agent.

This module contains no LLM initialization, so it can be imported and tested
independently of model-provider dependencies.

Design principle: only pure, deterministic operations go here.
All LLM-based reasoning (scenario gen, quality analysis) lives in the
system prompt so the orchestrator agent can compose them intelligently.

Tool categories (7 categories, ~28 tools total):
  1. MASTEST core: parse_openapi_spec, check_script_syntax, compute_coverage
  2. Playwright MCP: playwright_api_tools (dynamically loaded)
  3. DB CRUD: save_api_test, list_api_tests_db, get_api_test_detail, etc.
  4. OpenAPI: parse_openapi_to_db, save_api_endpoint, get_endpoint_artifacts, etc.
  5. Execution: execute_api_script, run_tests, parse_test_results, etc.
  6. Scenario: create_test_scenario, add_scenario_step, add_data_mapping, etc.
  7. Script management: save_api_script, download_api_script, etc.

Backends:
    - shell_backend: LocalShellBackend for executing commands (npx playwright test)
    - file_backend: FilesystemBackend for reading SKILL.md and writing artifacts
    - skills_backend: FilesystemBackend for skills directory
    - composite_backend: CompositeBackend routing all three backends
"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from src.app.agents.api.tools.api_parser import parse_api_spec
from src.app.agents.api.tools.metrics import check_script_syntax as _check_syntax
from src.app.agents.api.tools.metrics import compute_coverage as _compute_coverage
from src.app.agents.api.tools.playwright_mcp_server import playwright_api_tools

# New tool categories
from src.app.agents.api.tools.db_tools import DB_TOOLS
from src.app.agents.api.tools.openapi_tools import OPENAPI_TOOLS
from src.app.agents.api.tools.execution_tools import EXECUTION_TOOLS
from src.app.agents.api.tools.scenario_tools import SCENARIO_TOOLS

# -- Tool 1: API Parser -------------------------------------------------------

@tool
async def parse_openapi_spec(spec_url: str) -> str:
    """Load and parse an OpenAPI/Swagger specification into structured data.

    Fetches from a URL or reads a local file (JSON or YAML). Resolves all
    ``$ref`` references and extracts operations, parameters, responses, and
    component schemas.

    Args:
        spec_url: URL (https://...) or file path to the specification.

    Returns:
        JSON string with ``title``, ``version``, ``base_url``,
        ``operations`` (list), and ``schemas`` (dict).
    """
    return json.dumps(await parse_api_spec(spec_url), indent=2, default=str)


# -- Tool 2: Syntax Checker ---------------------------------------------------

@tool
def check_script_syntax(script: str) -> str:
    """Check a TypeScript test script for common syntax issues.

    Validates bracket balance and required Playwright constructs.
    Fast heuristic -- for full checking, use ``npx tsc --noEmit``.

    Args:
        script: Complete TypeScript test script content.

    Returns:
        JSON with ``valid``, ``errors`` list, and ``error_count``.
    """
    return _check_syntax(script)


# -- Tool 3: Coverage Calculator ----------------------------------------------

@tool
def compute_coverage(
    parsed_api_json: str,
    *,
    generated_scenarios_json: str = "[]",
    accepted_scenarios_json: str = "[]",
    tested_operation_ids_json: str = "[]",
    original_script: str = "",
    final_script: str = "",
) -> str:
    """Compute deterministic test quality metrics.

    Args:
        parsed_api_json: JSON output from ``parse_openapi_spec``.
        generated_scenarios_json: JSON array of LLM-generated scenario names.
        accepted_scenarios_json: JSON array of scenarios after human review.
        tested_operation_ids_json: JSON array of tested operationIds.
        original_script: Raw LLM-generated script (for usability).
        final_script: Edited final script (for usability).

    Returns:
        JSON with ``scenario_coverage``, ``operation_coverage``, and optionally
        ``usability`` (Levenshtein distance).
    """
    return _compute_coverage(
        parsed_api_json,
        generated_scenarios_json=generated_scenarios_json,
        accepted_scenarios_json=accepted_scenarios_json,
        tested_operation_ids_json=tested_operation_ids_json,
        original_script=original_script,
        final_script=final_script,
    )


# -- Tool list used by create_deep_agent --------------------------------------

MASTEST_TOOLS: list = [
    parse_openapi_spec,
    check_script_syntax,
    compute_coverage,
] + playwright_api_tools

# Combined tool list for the full API agent
API_AGENT_TOOLS: list = (
    MASTEST_TOOLS +     # 3 core + playwright MCP tools
    DB_TOOLS +          # 9 DB CRUD tools
    OPENAPI_TOOLS +     # 5 OpenAPI/endpoint tools
    EXECUTION_TOOLS +   # 7 execution/batch tools
    SCENARIO_TOOLS      # 10 scenario/step tools
)


# =============================================================================
# Backends (Phase 5 pattern - integrated into package __init__.py)
# =============================================================================

from pathlib import Path

from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend

from src.app.core.config import settings
from src.app.core.workspace import get_workspace_dir

_default_workspace_dir = get_workspace_dir("default", "api")
_default_workspace_dir.mkdir(parents=True, exist_ok=True)

shell_backend = LocalShellBackend(
    root_dir=_default_workspace_dir,
    virtual_mode=False,
    inherit_env=True,
    timeout=180,
)

file_backend = FilesystemBackend(
    root_dir=_default_workspace_dir,
    virtual_mode=True,
)

skills_backend = FilesystemBackend(
    root_dir=Path(__file__).parent.parent.parent / "skills",  # src/app/skills/
    virtual_mode=True,
)

composite_backend = CompositeBackend(
    default=shell_backend,
    routes={
        "/": file_backend,
        "/skills/": skills_backend,
    },
)
