"""Tests for workspace directory resolution and multi-space isolation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_default_space_id():
    """get_space_id() returns 'default' when called outside LangGraph context."""
    from src.app.core.workspace import get_space_id

    result = get_space_id()
    assert result == "default"


def test_configured_space_id():
    """get_space_id() returns the configured space_id from LangGraph configurable."""
    from src.app.core.workspace import get_space_id

    with patch(
        "src.app.core.workspace.get_config",
        return_value={"configurable": {"space_id": "custom-space"}},
    ):
        result = get_space_id()
        assert result == "custom-space"


def test_workspace_dir_path():
    """get_workspace_dir('default', 'web') returns Path ending with 'workspace/default/web'."""
    from src.app.core.workspace import get_workspace_dir

    result = get_workspace_dir("default", "web")
    assert isinstance(result, Path)
    assert str(result).endswith(str(Path("workspace") / "default" / "web"))


def test_workspace_dir_auto_resolve():
    """get_workspace_dir(None, 'api') resolves space_id from get_config() automatically."""
    from src.app.core.workspace import get_workspace_dir

    with patch(
        "src.app.core.workspace.get_config",
        return_value={"configurable": {"space_id": "team-a"}},
    ):
        result = get_workspace_dir(None, "api")
        assert isinstance(result, Path)
        assert str(result).endswith(str(Path("workspace") / "team-a" / "api"))


def test_workspace_dir_no_agent():
    """get_workspace_dir('space1') returns path ending with 'workspace/space1'."""
    from src.app.core.workspace import get_workspace_dir

    result = get_workspace_dir("space1")
    assert isinstance(result, Path)
    assert str(result).endswith(str(Path("workspace") / "space1"))


def test_space_isolation():
    """Different space_ids produce different workspace paths."""
    from src.app.core.workspace import get_workspace_dir

    path_a = get_workspace_dir("team-a", "web")
    path_b = get_workspace_dir("team-b", "web")
    assert path_a != path_b
    assert "team-a" in str(path_a)
    assert "team-b" in str(path_b)
