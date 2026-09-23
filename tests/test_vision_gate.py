"""Unit tests for VisionGateMiddleware（剥图 + 自动降级）。

三个层面：
1. 开关关闭时（LLM_SUPPORTS_VISION=false）：永远剥图（原有行为）。
2. 开关开启但端点报"不支持图片"类 400：当场剥图重试，本次调用成功；
   且该线程被记进已知名单——后续调用不再先发一次注定失败的请求。
3. 其他 400（key 错等）与无图请求：原样抛出/原样透传，不降级。

针对 2026-09-22 实测事故：glm-5.3 coding 端在设置开着「支持读图」时
发图即 400「Model only supports text input」，run 挂死且会话永久卡图。
"""

from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

import src.app.middleware.vision_gate as vg
from src.app.middleware.vision_gate import VisionGateMiddleware
from tests.conftest import MockModelRequest

pytestmark = pytest.mark.asyncio


class _TextOnlyError(Exception):
    """模拟 openai.BadRequestError 的网关文案（bigmodel 实测原文）。"""


def _req_with_image() -> MockModelRequest:
    return MockModelRequest(
        messages=[
            HumanMessage(
                content=[
                    {"type": "text", "text": "看这张图"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,xxx"}},
                ]
            )
        ]
    )


def _req_text_only() -> MockModelRequest:
    return MockModelRequest(messages=[HumanMessage(content="纯文本")])


def _stripped_count(request: MockModelRequest) -> int:
    """剥图后的请求里占位文本块的个数（每个被剥的图片块对应一个）。"""
    content = request.messages[0].content
    return sum(
        1
        for b in content
        if isinstance(b, dict) and "图片未发送" in str(b.get("text", ""))
    )


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """每个用例独立：清空线程级"端点不支持图片"名单。"""
    monkeypatch.setattr(vg.settings, "llm_supports_vision", True)
    vg._VISION_UNSUPPORTED_THREADS.clear()
    yield
    vg._VISION_UNSUPPORTED_THREADS.clear()


def _thread(monkeypatch, thread_id: str = "t-1"):
    # 中间件顶层 from langgraph.config import get_config 持有直接引用，
    # patch langgraph.config 模块属性对它不生效，必须 patch 模块内引用
    monkeypatch.setattr(
        vg, "get_config", lambda: {"configurable": {"thread_id": thread_id}}
    )


class TestSwitchOff:
    async def test_switch_off_always_strips(self, monkeypatch):
        """开关关闭：不管名单，直接剥图放行。"""
        monkeypatch.setattr(vg.settings, "llm_supports_vision", False)
        handler = AsyncMock(return_value="ok")
        req = _req_with_image()

        await VisionGateMiddleware().awrap_model_call(req, handler)

        assert handler.await_count == 1
        assert _stripped_count(handler.await_args[0][0]) == 1


class TestAutoFallback:
    async def test_text_only_400_strips_and_retries(self, monkeypatch):
        """开着开关 + 端点报不支持图片：第一次失败，剥图重试成功。"""
        _thread(monkeypatch)
        calls: list = []

        async def _handler(request):
            calls.append(request)
            if len(calls) == 1:
                raise _TextOnlyError(
                    "400 - Model only supports text input; received "
                    "unsupported content type 'image_url'."
                )
            return "ok"

        result = await VisionGateMiddleware().awrap_model_call(_req_with_image(), AsyncMock(side_effect=_handler))

        assert result == "ok"
        assert len(calls) == 2
        assert _stripped_count(calls[1]) == 1
        # 线程已进名单
        assert "t-1" in vg._VISION_UNSUPPORTED_THREADS

    async def test_remembered_thread_strips_without_failed_call(self, monkeypatch):
        """名单里的线程：不再先发注定失败的请求，直接剥图。"""
        _thread(monkeypatch)
        vg._remember_unsupported("t-1")
        handler = AsyncMock(return_value="ok")

        await VisionGateMiddleware().awrap_model_call(_req_with_image(), handler)

        assert handler.await_count == 1
        assert _stripped_count(handler.await_args[0][0]) == 1

    async def test_other_errors_not_swallowed(self, monkeypatch):
        """非"不支持图片"的失败（如 key 错误）必须原样抛出，不能静默降级。"""
        _thread(monkeypatch)
        handler = AsyncMock(side_effect=RuntimeError("401 - invalid api key"))

        with pytest.raises(RuntimeError):
            await VisionGateMiddleware().awrap_model_call(_req_with_image(), handler)

        assert handler.await_count == 1
        assert "t-1" not in vg._VISION_UNSUPPORTED_THREADS

    async def test_error_on_text_only_request_not_treated_as_vision(self, monkeypatch):
        """请求里根本没有图片块时，即使报错文案像也不降级（避免误吞其他 400）。"""
        _thread(monkeypatch)
        handler = AsyncMock(side_effect=_TextOnlyError("only supports text input"))

        with pytest.raises(_TextOnlyError):
            await VisionGateMiddleware().awrap_model_call(_req_text_only(), handler)

    async def test_unrelated_thread_unaffected(self, monkeypatch):
        """名单按线程隔离：别的线程仍然先正常发图。"""
        vg._remember_unsupported("other-thread")
        _thread(monkeypatch, "t-2")
        handler = AsyncMock(return_value="ok")
        req = _req_with_image()

        await VisionGateMiddleware().awrap_model_call(req, handler)

        assert handler.await_args[0][0] is req


class TestHealthyVision:
    async def test_vision_ok_passthrough(self, monkeypatch):
        """开关开启、端点正常：图片原样透传。"""
        _thread(monkeypatch)
        handler = AsyncMock(return_value="ok")
        req = _req_with_image()

        await VisionGateMiddleware().awrap_model_call(req, handler)

        assert handler.await_args[0][0] is req
        assert "t-1" not in vg._VISION_UNSUPPORTED_THREADS
