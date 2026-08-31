"""Thinking-effort middleware.

DSH-style per-conversation knob: the chat frontend passes a reasoning level
through the run's `configurable.llm_reasoning_effort` ("low"/"medium"/"high").
This middleware swaps in the matching model variant for that call. Anything
else (empty, "off", unknown) keeps the default model untouched — including
models built without any reasoning parameter at all.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ResponseT
from langchain_core.language_models import BaseChatModel
from langgraph.typing import ContextT

from app.agents.testcase.model_factory import VALID_EFFORTS, effort_model

logger = logging.getLogger(__name__)


class ThinkingEffortMiddleware(AgentMiddleware):
    """Apply a per-run reasoning effort from configurable.llm_reasoning_effort."""

    def __init__(self, fallback: BaseChatModel | None = None):
        """
        Args:
            fallback: legacy injection hook for tests; production resolves
                variants lazily through the model factory cache.
        """
        self._fallback = fallback

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> Any:
        effort = self._current_effort()
        if effort is None:
            return await handler(request)

        model = effort_model(effort) or self._fallback
        if model is None:
            return await handler(request)

        request = request.override(model=model)
        return await handler(request)

    @staticmethod
    def _current_effort() -> str | None:
        """Read the effort from the LangGraph run config; None when unset."""
        from langgraph.config import get_config

        try:
            config = get_config() or {}
        except Exception:
            return None
        effort = str((config.get("configurable") or {}).get("llm_reasoning_effort", "")).strip().lower()
        return effort if effort in VALID_EFFORTS else None
