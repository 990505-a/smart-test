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

import re
from pathlib import Path

from langgraph.config import get_config

from src.app.core.config import settings

#: 合法的目录片段：字母数字开头，其余为字母数字/点/下划线/连字符，最长 64。
#: 刻意**不允许** ``/``、``\``、空格、以及任何以 ``.`` 开头的东西——目录穿越
#: （``../..``）、绝对路径（``/etc``）、隐藏目录（``.ssh``）一律挡在门外。
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def safe_segment(value: str, *, field: str = "segment") -> str:
    """校验一个会被当作**单层目录名**使用的片段，通过则原样返回。

    这些值（``space_id`` / ``agent_name`` / ``thread_id``）来自请求，过去被直接
    拼进 ``settings.workspace_dir / space_id / agent_name / ...``。因为拼接没有
    任何校验，一个 ``space_id="../../../../tmp/pwned"`` 的请求就能把文件写到
    workspace 之外的任意目录（上传接口会真的落盘）。

    用**白名单**而不是过滤黑名单：``..`` 被禁只是顺带结果，真正的要求是这个
    片段只能是"一层普通目录名"。同样地，这也挡住了 Windows 的反斜杠与盘符。

    Raises:
        ValueError: 片段为空、含路径分隔符、以点开头、或含白名单外字符。
    """
    text = (value or "").strip()
    if not _SAFE_SEGMENT_RE.match(text):
        raise ValueError(
            f"{field} 不合法：只允许字母数字开头、由字母数字/._- 组成的单层目录名"
            f"（收到 {value!r}）"
        )
    return text


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

    Raises:
        ValueError: space_id / agent_name 不是合法的单层目录名（见 safe_segment）。
            这里是**所有** workspace 路径拼接的收口点（上传、记忆、agent 默认目录
            都经过它），所以校验放在这里能一次覆盖全部调用方。
    """
    if space_id is None:
        space_id = get_space_id()
    base = settings.workspace_dir / safe_segment(space_id, field="space_id")
    if agent_name:
        base = base / safe_segment(agent_name, field="agent_name")
    return base
