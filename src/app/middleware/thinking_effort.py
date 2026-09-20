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

from src.app.agents.testcase.model_factory import VALID_EFFORTS, effort_model

logger = logging.getLogger(__name__)


def configurable_value(key: str, default: str = "") -> str:
    """Read a string out of the run config's ``configurable``; "" when unset.

    ``get_config()`` raises outside a graph context (unit tests, plain calls),
    which must not break the caller — an absent value simply means "no per-run
    override", i.e. keep whatever the platform is configured with.
    """
    from langgraph.config import get_config

    try:
        config = get_config() or {}
    except Exception:
        return default
    return str((config.get("configurable") or {}).get(key, default) or "").strip()


def current_effort() -> str | None:
    """Per-run reasoning effort from configurable.llm_reasoning_effort."""
    effort = configurable_value("llm_reasoning_effort").lower()
    return effort if effort in VALID_EFFORTS else None


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
        return current_effort()
