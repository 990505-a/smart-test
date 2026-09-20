"""无头智能体调用测试（services/agent_runner）。

它给定时任务用，最重要的性质是**永不抛异常**：一次 LLM 故障不能把整轮
索引带崩。这里用假的 httpx 客户端覆盖成功、HTTP 失败、连接异常、空输出
四条路径。
"""

from __future__ import annotations

import pytest

from src.app.services import agent_runner


class _FakeResponse:
    def __init__(self, status_code: int = 200, lines: list[str] | None = None,
                 body: bytes = b""):
        self.status_code = status_code
        self._lines = lines or []
        self._body = body

    async def aread(self) -> bytes:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 300:
            raise RuntimeError(f"HTTP {self.status_code}")

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeClient:
    """替身 AsyncClient：post 建线程，stream 回放预先编排好的 SSE。"""

    def __init__(self, *, stream_response: _FakeResponse | None = None,
                 post_error: Exception | None = None):
        self._stream_response = stream_response or _FakeResponse()
        self._post_error = post_error
        self.calls: list[tuple[str, str]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url: str, json=None):
        self.calls.append(("POST", url))
        if self._post_error:
            raise self._post_error
        return _FakeResponse(200)

    def stream(self, method: str, url: str, json=None):
        self.calls.append((method, url))
        return self._stream_response


def _install(monkeypatch, client: _FakeClient) -> _FakeClient:
    monkeypatch.setattr(agent_runner.httpx, "AsyncClient", lambda **kw: client)
    return client


_AI_EVENT = [
    "event: updates",
    'data: {"agent": {"messages": [{"type": "ai", "content": "这是报告正文"}]}}',
    "",
]


@pytest.mark.asyncio
async def test_success_returns_last_assistant_text(monkeypatch):
    client = _install(monkeypatch, _FakeClient(stream_response=_FakeResponse(200, _AI_EVENT)))

    result = await agent_runner.run_agent_once(
        "分析这些变更", assistant_id="codebase_agent",
        configurable={"permission_mode": "full_access"}, thread_id="t-1")

    assert result["success"] is True
    assert result["output"] == "这是报告正文"
    assert result["thread_id"] == "t-1"
    # 线程复用给定 id，run 挂在同一个线程上
    assert ("POST", f"{agent_runner.settings.langgraph_api_url}/threads") in client.calls


@pytest.mark.asyncio
async def test_http_error_on_run_start_is_reported(monkeypatch):
    _install(monkeypatch, _FakeClient(
        stream_response=_FakeResponse(500, body=b"internal error")))

    result = await agent_runner.run_agent_once("x", assistant_id="codebase_agent")

    assert result["success"] is False
    assert "HTTP 500" in result["error"]


@pytest.mark.asyncio
async def test_connection_failure_does_not_raise(monkeypatch):
    _install(monkeypatch, _FakeClient(post_error=ConnectionError("连不上")))

    result = await agent_runner.run_agent_once("x", assistant_id="codebase_agent")

    assert result["success"] is False
    assert "ConnectionError" in result["error"]


@pytest.mark.asyncio
async def test_empty_output_is_a_failure(monkeypatch):
    """图未注册或 run 停在审批上时不会有正文——必须算失败，不能落一份空报告。"""
    _install(monkeypatch, _FakeClient(stream_response=_FakeResponse(200, [])))

    result = await agent_runner.run_agent_once("x", assistant_id="codebase_agent")

    assert result["success"] is False
    assert result["output"] == ""
    assert "未产生输出" in result["error"]


@pytest.mark.asyncio
async def test_stream_error_event_is_surfaced(monkeypatch):
    lines = ["event: error", 'data: {"error": "boom from server"}', ""]
    _install(monkeypatch, _FakeClient(stream_response=_FakeResponse(200, lines)))

    result = await agent_runner.run_agent_once("x", assistant_id="codebase_agent")

    assert result["success"] is False
    assert "boom from server" in result["error"]


@pytest.mark.asyncio
async def test_generates_a_uuid_thread_id_when_not_given(monkeypatch):
    """线程 id 必须是合法 UUID：服务端会校验并回 422
    `Invalid thread ID: must be a UUID`——这条以前踩过。"""
    import uuid as uuid_mod

    _install(monkeypatch, _FakeClient(stream_response=_FakeResponse(200, _AI_EVENT)))

    result = await agent_runner.run_agent_once("x", assistant_id="codebase_agent")

    assert result["success"] is True
    uuid_mod.UUID(result["thread_id"])  # 不合法会抛 ValueError
