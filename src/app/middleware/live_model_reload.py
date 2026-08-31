"""Live model reload middleware.

The settings page saves model changes to .env (via SettingsService.sync_env_file).
This middleware stats that file before every model call and, when it changed,
re-reads the model config and overrides the request's model with a freshly
built one — so saved settings take effect on the very next turn, without
restarting the LangGraph agent process.

Must sit ABOVE ThinkingEffortMiddleware and DynamicModelSelection in the
onion: refresh_from_env() mutates the global settings and clears the
effort-variant cache, so the inner middlewares rebuild their variants from
the new values. DynamicModelSelection receives a factory callable for the
same reason.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ResponseT
from langgraph.typing import ContextT

from app.agents.testcase.model_factory import build_chat_model, refresh_from_env

logger = logging.getLogger(__name__)


class LiveModelReloadMiddleware(AgentMiddleware):
    """Re-read .env before each model call; override the model when it changed."""

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> Any:
        try:
            if refresh_from_env():
                logger.info("model settings changed in .env — rebuilding chat model")
                request = request.override(model=build_chat_model())
        except Exception:  # noqa: BLE001 — reload failure must never kill the run
            logger.exception("live model reload failed; keeping the current model")
        return await handler(request)
