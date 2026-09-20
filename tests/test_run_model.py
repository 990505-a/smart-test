"""Unit tests for RunModelMiddleware (per-conversation model presets).

The middleware resolves ``configurable.model_preset`` (a name saved on the
settings page) into a real chat model and overrides the request with it. DB
access and model construction are patched here — the point under test is the
resolution/override/fallback logic, not SQLite or provider clients.
"""
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import SystemMessage

import src.app.middleware.run_model as rm
from src.app.middleware.run_model import RunModelMiddleware
from tests.conftest import MockModelRequest


@pytest.fixture
def mock_handler():
    async def _handler(request):
        return request
    return AsyncMock(side_effect=_handler)


@pytest.fixture
def preset_model():
    class _SentinelModel:
        pass

    return _SentinelModel()


def _request() -> MockModelRequest:
    return MockModelRequest(
        messages=[],
        system_message=SystemMessage(content="System"),
    )


def _config(monkeypatch, preset: str = "", effort: str = "") -> None:
    configurable: dict = {}
    if preset:
        configurable["model_preset"] = preset
    if effort:
        configurable["llm_reasoning_effort"] = effort
    monkeypatch.setattr("langgraph.config.get_config", lambda: {"configurable": configurable})


def _preset(monkeypatch, values: dict | None, calls: list | None = None):
    async def _fake(name: str):
        if calls is not None:
            calls.append(name)
        return values
    monkeypatch.setattr(RunModelMiddleware, "_preset_values", staticmethod(_fake))


class TestPassthrough:
    @pytest.mark.asyncio
    async def test_no_preset_keeps_default_model(self, mock_handler, monkeypatch):
        """没有选模型（未设置 configurable.model_preset）时不碰 request。"""
        _config(monkeypatch)
        middleware = RunModelMiddleware()
        req = _request()

        await middleware.awrap_model_call(req, mock_handler)

        assert mock_handler.call_args[0][0] is req

    @pytest.mark.asyncio
    async def test_unknown_preset_keeps_default_model(self, mock_handler, monkeypatch):
        """预设被删掉了：返回 None，沿用默认模型，绝不抛。"""
        _config(monkeypatch, preset="已删除的预设")
        _preset(monkeypatch, None)
        middleware = RunModelMiddleware()
        req = _request()

        await middleware.awrap_model_call(req, mock_handler)

        assert mock_handler.call_args[0][0] is req

    @pytest.mark.asyncio
    async def test_outside_run_context_passes_through(self, mock_handler):
        """图上下文之外 get_config() 抛异常，同样不动 request。"""
        middleware = RunModelMiddleware()
        req = _request()

        await middleware.awrap_model_call(req, mock_handler)

        assert mock_handler.call_args[0][0] is req


class TestOverride:
    @pytest.mark.asyncio
    async def test_preset_overrides_model(self, mock_handler, monkeypatch, preset_model):
        _config(monkeypatch, preset="glm-5.3-flash", effort="high")
        _preset(monkeypatch, {"llm_model": "glm-5.3-flash", "llm_api_key": "sk-x"})
        seen: dict = {}

        def _fake_build(values, effort="", **kwargs):
            seen["values"] = values
            seen["effort"] = effort
            return preset_model

        monkeypatch.setattr(rm, "build_model_from_values", _fake_build)
        middleware = RunModelMiddleware()
        req = _request()

        await middleware.awrap_model_call(req, mock_handler)
        called_req = mock_handler.call_args[0][0]

        assert called_req is not req
        assert called_req.model is preset_model
        # 预设的值原样进工厂，且把本轮的 effort 一起带上（外层 effort 中间件的
        # override 会被这里盖掉，所以必须由本中间件负责）
        assert seen["values"]["llm_model"] == "glm-5.3-flash"
        assert seen["effort"] == "high"

    @pytest.mark.asyncio
    async def test_build_failure_keeps_default_model(self, mock_handler, monkeypatch):
        """预设坏了（比如 Key 丢了）不该让整个 run 挂掉。"""
        _config(monkeypatch, preset="坏预设")
        _preset(monkeypatch, {"llm_base_url": "https://x.example/v1"})

        def _boom(*args, **kwargs):
            raise ValueError("模型缺少 API Key（LLM_API_KEY）")

        monkeypatch.setattr(rm, "build_model_from_values", _boom)
        middleware = RunModelMiddleware()
        req = _request()

        await middleware.awrap_model_call(req, mock_handler)

        assert mock_handler.call_args[0][0] is req

class TestModelValues:
    def test_keeps_only_model_keys(self):
        """预设里可能留着旧键（例如已废弃的 vision_*），只把 MODEL_KEYS 里的交给工厂。"""
        values = rm.model_values({
            "name": "旧的预设",
            "values": {
                "llm_model": "m1",
                "llm_api_key": "sk-x",
                "vision_model": "gpt-4o",
                "vision_api_key": "sk-stale",
            },
        })

        assert values == {"llm_model": "m1", "llm_api_key": "sk-x"}

    def test_missing_values_key(self):
        assert rm.model_values({"name": "空的"}) == {}


class TestCache:
    @pytest.mark.asyncio
    async def test_preset_is_read_once_within_ttl(self, mock_handler, monkeypatch, preset_model):
        _config(monkeypatch, preset="glm-5.3-flash")
        calls: list = []
        _preset(monkeypatch, {"llm_model": "glm-5.3-flash"}, calls)
        monkeypatch.setattr(rm, "build_model_from_values", lambda values, **kw: preset_model)
        middleware = RunModelMiddleware()

        await middleware.awrap_model_call(_request(), mock_handler)
        await middleware.awrap_model_call(_request(), mock_handler)

        assert calls == ["glm-5.3-flash"]  # 第二次命中缓存，没有再去读 DB

    @pytest.mark.asyncio
    async def test_expired_cache_reads_again(self, mock_handler, monkeypatch, preset_model):
        _config(monkeypatch, preset="glm-5.3-flash")
        calls: list = []
        _preset(monkeypatch, {"llm_model": "glm-5.3-flash"}, calls)
        monkeypatch.setattr(rm, "build_model_from_values", lambda values, **kw: preset_model)
        middleware = RunModelMiddleware(cache_ttl=0.0)

        await middleware.awrap_model_call(_request(), mock_handler)
        await middleware.awrap_model_call(_request(), mock_handler)

        assert calls == ["glm-5.3-flash", "glm-5.3-flash"]


class TestOnionOrder:
    def test_run_model_sits_inside_thinking_effort(self):
        """顺序是硬约束：两个中间件都会 override 模型，谁更靠内谁最后写、谁生效。

        本中间件必须更靠内，否则"选了预设但思考强度把它盖回默认模型"。
        """
        from src.app.agents.harness import build_middleware
        from src.app.middleware.thinking_effort import ThinkingEffortMiddleware

        order = [type(m) for m in build_middleware()]
        assert RunModelMiddleware in order, "按会话选模型的中间件不在洋葱里"
        assert ThinkingEffortMiddleware in order
        assert order.index(ThinkingEffortMiddleware) < order.index(RunModelMiddleware), (
            "RunModelMiddleware 必须排在 ThinkingEffortMiddleware 之内（更靠后）")
