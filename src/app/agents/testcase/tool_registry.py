"""Centralized tool registry for the TestCase Agent.

Replaces hardcoded tool lists in agent.py with a categorized registry pattern
matching the classroom's tool_registry.py approach.
"""

from langchain.tools import BaseTool

from app.agents.testcase.tools.db_tools import (
    ensure_project,
    list_project_test_cases,
    save_test_case_to_db,
    save_test_cases_batch,
)


def get_local_tools() -> list[BaseTool]:
    """Return all locally-defined tools for the TestCase Agent."""
    return [
        save_test_cases_batch,
        save_test_case_to_db,
        list_project_test_cases,
        ensure_project,
    ]


def get_all_tools(mcp_tools: list[BaseTool] | None = None) -> list[BaseTool]:
    """Return all tools (local + optional MCP tools)."""
    tools = get_local_tools()
    if mcp_tools:
        tools.extend(mcp_tools)
    return tools
