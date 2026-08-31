"""Unit tests for ThinkingEffortMiddleware (per-run reasoning effort)."""
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import SystemMessage

import src.app.middleware.thinking_effort as te
from src.app.middleware.thinking_effort import ThinkingEffortMiddleware
from tests.conftest import MockModelRequest


@pytest.fixture
def mock_handler():
    async def _handler(request):
        return request
    return AsyncMock(side_effect=_handler)


@pytest.fixture
def fallback_model():
    class _SentinelModel:
        pass

    return _SentinelModel()


def _request() -> MockModelRequest:
    return MockModelRequest(
        messages=[],
        system_message=SystemMessage(content="System"),
    )


class TestPassthrough:
    @pytest.mark.asyncio
    async def test_no_langgraph_context_passes_through(self, mock_handler, fallback_model):
        """Outside a run (get_config raises) the request is untouched."""
        middleware = ThinkingEffortMiddleware(fallback=fallback_model)
        req = _request()

        await middleware.awrap_model_call(req, mock_handler)

        assert mock_handler.call_args[0][0] is req

    @pytest.mark.asyncio
    async def test_empty_effort_passes_through(self, mock_handler, fallback_model, monkeypatch):
        monkeypatch.setattr(
            "langgraph.config.get_config",
            lambda: {"configurable": {"llm_reasoning_effort": ""}},
        )
        middleware = ThinkingEffortMiddleware(fallback=fallback_model)
        req = _request()

        await middleware.awrap_model_call(req, mock_handler)

        assert mock_handler.call_args[0][0] is req

    @pytest.mark.asyncio
    async def test_invalid_effort_passes_through(self, mock_handler, fallback_model, monkeypatch):
        monkeypatch.setattr(
            "langgraph.config.get_config",
            lambda: {"configurable": {"llm_reasoning_effort": "turbo"}},
        )
        middleware = ThinkingEffortMiddleware(fallback=fallback_model)
        req = _request()

        await middleware.awrap_model_call(req, mock_handler)

        assert mock_handler.call_args[0][0] is req


class TestOverride:
    @pytest.mark.asyncio
    async def test_valid_effort_overrides_model(self, mock_handler, fallback_model, monkeypatch):
        monkeypatch.setattr(
            "langgraph.config.get_config",
            lambda: {"configurable": {"llm_reasoning_effort": "HIGH"}},
        )
        middleware = ThinkingEffortMiddleware(fallback=fallback_model)
        req = _request()

        with patch.object(te, "effort_model", return_value=fallback_model) as em:
            await middleware.awrap_model_call(req, mock_handler)

        em.assert_called_once_with("high")
        called_req = mock_handler.call_args[0][0]
        assert called_req is not req
        assert called_req.model is fallback_model

    @pytest.mark.asyncio
    async def test_uses_fallback_when_factory_returns_none(
        self, mock_handler, fallback_model, monkeypatch
    ):
        monkeypatch.setattr(
            "langgraph.config.get_config",
            lambda: {"configurable": {"llm_reasoning_effort": "low"}},
        )
        middleware = ThinkingEffortMiddleware(fallback=fallback_model)
        req = _request()

        with patch.object(te, "effort_model", return_value=None):
            await middleware.awrap_model_call(req, mock_handler)

        assert mock_handler.call_args[0][0].model is fallback_model
