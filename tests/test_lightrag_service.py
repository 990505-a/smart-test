"""LightRAG service degradation tests.

The service must never raise — every failure path returns a dict with
success=False so the agent pipeline is never blocked by a stopped
lightrag-server.
"""

from __future__ import annotations

import pytest

from src.app.services import lightrag_service


def test_query_rejects_invalid_mode():
    """Invalid mode is rejected before any HTTP call is attempted."""
    import asyncio

    result = asyncio.run(lightrag_service.query("测试问题", mode="bogus"))
    assert result["success"] is False
    assert "bogus" in result["error"]


def test_ingest_file_missing_path():
    import asyncio

    result = asyncio.run(lightrag_service.ingest_file("Z:/no/such/file.md"))
    assert result["success"] is False
    assert "不存在" in result["error"]


def test_health_degrades_when_server_down(monkeypatch):
    """Server unreachable → graceful dict, no exception.

    刻意**不**用"连一个没人监听的端口"来制造不可达：本机上系统代理（Clash 之类）
    会劫持该连接并回 502，于是走的是 ``HTTPStatusError`` 分支、报 "HTTP 502"，
    断言 "不可达" 就红了——但那与代码无关，是环境噪声（PLATFORM.md §6 记过这条）。
    直接让客户端抛 ``ConnectError``，才是确定性地测"连不上"这条降级分支。
    """
    import asyncio

    import httpx

    class _DownClient:
        """只实现 _call 用到的两个接口；request 一律抛连接错误。"""

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def request(self, *args, **kwargs):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(lightrag_service, "_client", lambda *a, **kw: _DownClient())
    result = asyncio.run(lightrag_service.health())
    assert result["success"] is False
    assert "不可达" in result["error"]


def test_unknown_kb_is_reported_with_the_available_keys():
    """库里挑错了：要报"没有这个知识库"并列出有哪些，而不是去连一个不存在的地址。"""
    import asyncio

    result = asyncio.run(lightrag_service.query("随便问问", kb_key="没这个库"))
    assert result["success"] is False
    assert "没有这个知识库" in result["error"]
    assert "default" in result["error"]


def test_breaker_is_per_kb(monkeypatch):
    """熔断按库分别计数：一个库连不上，不该把其它库也一起判成不可用。"""
    from src.app.core.config import settings
    from src.app.services.rag_kbs import KB

    monkeypatch.setattr(settings, "circuit_breaker_fail_max", 1)
    monkeypatch.setattr(settings, "circuit_breaker_reset_timeout", 60)

    default_guard = lightrag_service._guard(lightrag_service.resolve(""))
    other_guard = lightrag_service._guard(KB(key="other", label="另一个库", port=5099))
    try:
        default_guard.fail()
        assert default_guard.blocked() is not None
        assert other_guard.blocked() is None
    finally:
        default_guard.ok()
        lightrag_service._guards.pop("other", None)


def test_query_maps_http_error_to_degraded_dict(monkeypatch):
    import asyncio

    class _Resp:
        status_code = 500
        text = "boom"

        def raise_for_status(self):
            import httpx
            raise httpx.HTTPStatusError("err", request=None, response=self)

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def request(self, method, path, **kw):
            return _Resp()

    monkeypatch.setattr(lightrag_service.httpx, "AsyncClient", lambda **kw: _Client())
    result = asyncio.run(lightrag_service.query("登录功能测试要点"))
    assert result["success"] is False
    assert "500" in result["error"]


def test_query_modes_constant():
    assert "hybrid" in lightrag_service.QUERY_MODES
    assert "mix" in lightrag_service.QUERY_MODES
