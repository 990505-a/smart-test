"""Tool error handler for Web Agent.

Wraps tool _run/_arun methods so errors become JSON messages instead of
crashes.  This is especially critical for the Web agent because browser
automation tools frequently encounter errors (element not found, timeout,
navigation failure) that should not crash the agent.

Adapted from classroom web_mcp/tool_error_handler.py for project architecture.
"""

from __future__ import annotations

import json
import logging
from functools import wraps
from typing import Any

from langchain_core.tools import BaseTool, ToolException

logger = logging.getLogger(__name__)


def wrap_tool_with_error_handling(tool: BaseTool) -> BaseTool:
    """Wrap a single tool so errors are returned as JSON, not raised.

    Args:
        tool: The original tool instance.

    Returns:
        The same tool instance with _run and _arun wrapped.
    """
    original_run = tool._run
    original_arun = tool._arun

    @wraps(original_run)
    def wrapped_run(*args: Any, **kwargs: Any) -> Any:
        try:
            return original_run(*args, **kwargs)
        except ToolException as e:
            error_msg = f"Tool '{tool.name}' encountered an error: {e}"
            logger.warning(error_msg)
            error_info = {
                "success": False,
                "error": str(e),
                "error_type": "ToolException",
                "message": error_msg,
                "note": (
                    "This error was caught and returned as a message. "
                    "You can analyze the error and try a different approach."
                ),
            }
            error_json = json.dumps(error_info, ensure_ascii=False)
            return (error_json, {"error": True, "tool": tool.name})
        except Exception as e:  # noqa: BLE001
            error_msg = f"Tool '{tool.name}' encountered an unexpected error: {e}"
            logger.error(error_msg, exc_info=True)
            error_info = {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "message": error_msg,
                "note": (
                    "This error was caught and returned as a message. "
                    "You can analyze the error and try a different approach."
                ),
            }
            error_json = json.dumps(error_info, ensure_ascii=False)
            return (error_json, {"error": True, "tool": tool.name})

    @wraps(original_arun)
    async def wrapped_arun(*args: Any, **kwargs: Any) -> Any:
        try:
            return await original_arun(*args, **kwargs)
        except ToolException as e:
            error_msg = f"Tool '{tool.name}' encountered an error: {e}"
            logger.warning(error_msg)
            error_info = {
                "success": False,
                "error": str(e),
                "error_type": "ToolException",
                "message": error_msg,
                "note": (
                    "This error was caught and returned as a message. "
                    "You can analyze the error and try a different approach."
                ),
            }
            error_json = json.dumps(error_info, ensure_ascii=False)
            return (error_json, {"error": True, "tool": tool.name})
        except Exception as e:  # noqa: BLE001
            error_msg = f"Tool '{tool.name}' encountered an unexpected error: {e}"
            logger.error(error_msg, exc_info=True)
            error_info = {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "message": error_msg,
                "note": (
                    "This error was caught and returned as a message. "
                    "You can analyze the error and try a different approach."
                ),
            }
            error_json = json.dumps(error_info, ensure_ascii=False)
            return (error_json, {"error": True, "tool": tool.name})

    tool._run = wrapped_run
    tool._arun = wrapped_arun  # type: ignore[assignment]
    return tool


def wrap_tools_with_error_handling(
    tools: list[BaseTool],
    tool_patterns: list[str] | None = None,
) -> list[BaseTool]:
    """Wrap a list of tools with error handling.

    Args:
        tools: List of tool instances to wrap.
        tool_patterns: Optional list of name substrings to match.
            If None (default), ALL tools are wrapped. For the Web agent
            this is the recommended default since even local tools can
            fail unexpectedly.

    Returns:
        List of wrapped tools (or original if pattern did not match).
    """
    wrapped_tools: list[BaseTool] = []

    for tool in tools:
        should_wrap = False

        if tool_patterns is None:
            should_wrap = True
        else:
            for pattern in tool_patterns:
                if pattern in tool.name:
                    should_wrap = True
                    break

        if should_wrap:
            logger.info("Wrapping tool '%s' with error handling", tool.name)
            wrapped_tools.append(wrap_tool_with_error_handling(tool))
        else:
            wrapped_tools.append(tool)

    return wrapped_tools
