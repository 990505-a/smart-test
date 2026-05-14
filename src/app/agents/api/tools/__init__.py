"""
Standalone tools and backend configuration for the API Automation Testing Agent.

This module contains no LLM initialization, so it can be imported and tested
independently of model-provider dependencies.

Design principle: only pure, deterministic operations go here.
All LLM-based reasoning (scenario gen, quality analysis) lives in the
system prompt so the orchestrator agent can compose them intelligently.

Three tools:
  1. ``parse_openapi_spec`` — fetch + parse OpenAPI JSON/YAML, resolve $ref.
  2. ``check_script_syntax`` — bracket balance + structure validation for TS.
  3. ``compute_coverage`` — scenario / operation / usability metrics.

Backends:
    - shell_backend: LocalShellBackend for executing commands
    - file_backend: FilesystemBackend for reading SKILL.md and writing artifacts
    - composite_backend: CompositeBackend routing file ops to file_backend,
      execute ops to shell_backend

Note: Backend configuration is integrated into this __init__.py because the
tools/ package directory and a tools.py flat module cannot coexist in Python.
This follows the same pattern as web/tools.py but uses the package __init__.
"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from src.app.agents.api.tools.api_parser import parse_api_spec
from src.app.agents.api.tools.metrics import check_script_syntax as _check_syntax
from src.app.agents.api.tools.metrics import compute_coverage as _compute_coverage
from src.app.agents.api.tools.playwright_mcp_server import playwright_api_tools

# -- Tool 1: API Parser -------------------------------------------------------

@tool
def parse_openapi_spec(spec_url: str) -> str:
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
    return json.dumps(parse_api_spec(spec_url), indent=2, default=str)


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


# =============================================================================
# Backends (Phase 5 pattern — integrated into package __init__.py)
# =============================================================================

from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend

from src.app.core.config import settings

workspace_dir = settings.workspace_dir / "api"

shell_backend = LocalShellBackend(
    root_dir=workspace_dir,
    virtual_mode=False,
    inherit_env=True,
    timeout=180,
)

file_backend = FilesystemBackend(
    root_dir=workspace_dir,
    virtual_mode=True,
)

composite_backend = CompositeBackend(
    default=shell_backend,
    routes={"/": file_backend},
)
