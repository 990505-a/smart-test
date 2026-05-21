"""Web Agent middleware: context injection and tool error handling."""

from src.app.agents.web.middleware.context_injection import WebContextInjectionMiddleware
from src.app.agents.web.middleware.tool_error_handler import (
    wrap_tool_with_error_handling,
    wrap_tools_with_error_handling,
)

__all__ = [
    "WebContextInjectionMiddleware",
    "wrap_tool_with_error_handling",
    "wrap_tools_with_error_handling",
]
