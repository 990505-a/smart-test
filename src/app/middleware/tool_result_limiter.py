"""Middleware that limits tool result sizes to prevent thread state bloat.

Intercepts ALL tool call results and truncates those exceeding the character
limit. Only small-result tools (ls, glob, grep) are excluded — everything
else (read_file, etc.) gets capped.

Key lesson: read_file can return massive content when the agent reads binary
files (e.g., PDFs) or very large text files. Without truncation, a single
read_file on a 2.5MB PDF produces 3.4M chars of garbled output, instantly
overflowing the LLM context window.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ContextT,
    ResponseT,
    ToolCallRequest,
)
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

# Filesystem tools managed by FilesystemMiddleware - skip these
_FILESYSTEM_TOOLS = frozenset({
    "ls", "read_file", "write_file", "edit_file", "glob", "grep", "execute",
})

# Default character limit for tool results (~5000 tokens at 4 chars/token)
DEFAULT_TOOL_RESULT_CHAR_LIMIT = 20_000


class ToolResultLimiterMiddleware(AgentMiddleware):
    """Middleware that truncates large tool results from custom tools.

    This prevents thread state bloat by ensuring that custom tools
    (codebase/export tools) don't return results
    so large they bloat the LangGraph thread state.

    Args:
        char_limit: Maximum characters allowed in a tool result.
            Results exceeding this are truncated with a notice.
        excluded_tools: Set of tool names to exclude from truncation.
            Defaults to FilesystemMiddleware's built-in tools.
    """

    def __init__(
        self,
        *,
        char_limit: int = DEFAULT_TOOL_RESULT_CHAR_LIMIT,
        excluded_tools: set[str] | None = None,
    ) -> None:
        self._char_limit = char_limit
        self._excluded_tools = excluded_tools or _FILESYSTEM_TOOLS

    def _truncate_result(self, result: ToolMessage, tool_name: str) -> ToolMessage:
        """Truncate a tool result if it exceeds the character limit."""
        if not isinstance(result, ToolMessage):
            return result

        if tool_name in self._excluded_tools:
            return result

        content = result.content
        if not isinstance(content, str):
            # Non-string content (e.g., multimodal blocks) - skip truncation
            return result

        if len(content) <= self._char_limit:
            return result

        truncated = content[:self._char_limit]
        truncation_notice = (
            f"\n\n[Tool result truncated: {len(content)} chars total, "
            f"showing first {self._char_limit} chars. "
            f"If you need more details, use a more specific query or "
            f"narrow your search parameters.]"
        )

        return ToolMessage(
            content=truncated + truncation_notice,
            tool_call_id=result.tool_call_id,
            name=result.name,
            id=result.id,
            artifact=result.artifact,
            status=result.status,
        )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage],
    ) -> ToolMessage:
        """Intercept tool results and truncate large ones."""
        result = handler(request)
        tool_name = request.tool_call.get("name", "")
        return self._truncate_result(result, tool_name)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],
    ) -> ToolMessage:
        """Intercept tool results and truncate large ones (async)."""
        result = await handler(request)
        tool_name = request.tool_call.get("name", "")
        return self._truncate_result(result, tool_name)
