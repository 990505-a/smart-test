"""Tool error handler -- wraps tool calls with try/except that returns JSON errors.

Converts tool exceptions into structured error messages instead of letting them
propagate and crash the agent. Returns tuple format (content, artifact) for
response_format='content_and_artifact' compatibility.
"""

from __future__ import annotations

import json
import logging
from functools import wraps
from typing import Any

from langchain_core.tools import BaseTool, ToolException

logger = logging.getLogger(__name__)


def wrap_tool_with_error_handling(tool: BaseTool) -> BaseTool:
    """Wrap a single tool so errors become JSON messages instead of exceptions.

    Args:
        tool: The original LangChain tool to wrap.

    Returns:
        The same tool instance with _run and _arun replaced by wrapped versions.
    """
    original_run = tool._run
    original_arun = tool._arun

    @wraps(original_run)
    def wrapped_run(*args: Any, **kwargs: Any) -> Any:
        try:
            return original_run(*args, **kwargs)
        except ToolException as e:
            error_msg = f"Tool '{tool.name}' encountered an error: {str(e)}"
            logger.warning(error_msg)
            error_info = {
                "success": False,
                "error": str(e),
                "error_type": "ToolException",
                "message": error_msg,
                "note": "This error was caught and returned as a message. "
                "You can analyze the error and try a different approach.",
            }
            error_json = json.dumps(error_info, ensure_ascii=False)
            return (error_json, {"error": True, "tool": tool.name})
        except Exception as e:
            error_msg = f"Tool '{tool.name}' encountered an unexpected error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            error_info = {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "message": error_msg,
                "note": "This error was caught and returned as a message. "
                "You can analyze the error and try a different approach.",
            }
            error_json = json.dumps(error_info, ensure_ascii=False)
            return (error_json, {"error": True, "tool": tool.name})

    @wraps(original_arun)
    async def wrapped_arun(*args: Any, **kwargs: Any) -> Any:
        try:
            return await original_arun(*args, **kwargs)
        except ToolException as e:
            error_msg = f"Tool '{tool.name}' encountered an error: {str(e)}"
            logger.warning(error_msg)
            error_info = {
                "success": False,
                "error": str(e),
                "error_type": "ToolException",
                "message": error_msg,
                "note": "This error was caught and returned as a message. "
                "You can analyze the error and try a different approach.",
            }
            error_json = json.dumps(error_info, ensure_ascii=False)
            return (error_json, {"error": True, "tool": tool.name})
        except Exception as e:
            error_msg = f"Tool '{tool.name}' encountered an unexpected error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            error_info = {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "message": error_msg,
                "note": "This error was caught and returned as a message. "
                "You can analyze the error and try a different approach.",
            }
            error_json = json.dumps(error_info, ensure_ascii=False)
            return (error_json, {"error": True, "tool": tool.name})

    # Replace tool run methods with wrapped versions
    tool._run = wrapped_run  # type: ignore[assignment]
    tool._arun = wrapped_arun  # type: ignore[assignment]

    return tool


def wrap_tools_with_error_handling(
    tools: list[BaseTool],
    tool_patterns: list[str] | None = None,
) -> list[BaseTool]:
    """Wrap a list of tools with error handling.

    Args:
        tools: List of LangChain tools to wrap.
        tool_patterns: Optional list of name patterns to match (e.g. ["browser_", "playwright-test/"]).
            If None, all tools are wrapped.

    Returns:
        List of tools with error handling applied.
    """
    wrapped_tools = []

    for tool in tools:
        should_wrap = False

        if tool_patterns is None:
            # Wrap all tools
            should_wrap = True
        else:
            # Check if tool name matches any pattern
            for pattern in tool_patterns:
                if pattern in tool.name:
                    should_wrap = True
                    break

        if should_wrap:
            logger.info(f"Wrapping tool '{tool.name}' with error handling")
            wrapped_tools.append(wrap_tool_with_error_handling(tool))
        else:
            wrapped_tools.append(tool)

    return wrapped_tools
