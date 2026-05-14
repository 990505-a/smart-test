"""Workspace directory resolution for multi-space isolation.

Provides helpers to extract the current space_id from LangGraph's
configurable mechanism and resolve workspace directory paths for
per-space agent isolation.

Usage:
    from src.app.core.workspace import get_space_id, get_workspace_dir

    # Inside an agent tool (per-request resolution):
    space_id = get_space_id()
    workspace = get_workspace_dir(space_id, "web")

    # Module-level default workspace (for graph compilation):
    default_dir = get_workspace_dir("default", "web")
"""

from __future__ import annotations

from pathlib import Path

from langgraph.config import get_config

from src.app.core.config import settings


def get_space_id() -> str:
    """Extract space_id from LangGraph configurable, default to 'default'.

    Safe to call outside runnable context (returns 'default').

    Returns:
        The configured space_id string, or 'default' if not set.
    """
    try:
        config = get_config()
        return config.get("configurable", {}).get("space_id", "default")
    except RuntimeError:
        # Outside runnable context (tests, imports, direct calls)
        return "default"


def get_workspace_dir(space_id: str | None = None, agent_name: str = "") -> Path:
    """Resolve workspace directory for a given space_id and agent.

    Args:
        space_id: Workspace ID. If None, reads from current LangGraph config.
        agent_name: Agent subdirectory name (e.g., "web", "api", "testcase").

    Returns:
        Path like workspace/{space_id}/{agent_name}/
    """
    if space_id is None:
        space_id = get_space_id()
    base = settings.workspace_dir / space_id
    if agent_name:
        base = base / agent_name
    return base
