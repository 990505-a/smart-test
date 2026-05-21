"""API Agent context injection middleware.

Injects runtime context (project_identifier, folder_id) into the system prompt
so the agent knows which project to work with without asking the user.
"""

from __future__ import annotations

from typing import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse


class APIContextInjectionMiddleware(AgentMiddleware):
    """Context injection middleware -- appends runtime parameters to system prompt."""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        # Safely access context attributes
        ctx = getattr(request.runtime, "context", None)
        if ctx is None:
            return await handler(request)

        project_identifier = getattr(ctx, "project_identifier", "") or ""
        folder_id = getattr(ctx, "folder_id", "") or ""

        if not project_identifier and not folder_id:
            return await handler(request)

        context_info = (
            "\n\n---\n## Runtime Context\n"
            f"- project_identifier: `{project_identifier}`\n"
            f"- folder_id: `{folder_id}`\n\n"
            "**Important:** These parameters are injected automatically. "
            "Do not ask the user for them.\n---"
        )

        if isinstance(request.system_message.content, list):
            request.system_message.content = request.system_message.content + [
                {"type": "text", "text": context_info}
            ]
        else:
            request.system_message.content = request.system_message.content + context_info

        return await handler(request)
