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
    """Server unreachable → graceful dict, no exception."""
    import asyncio

    monkeypatch.setattr(lightrag_service.settings, "lightrag_base_url",
                        "http://127.0.0.1:59999")
    result = asyncio.run(lightrag_service.health())
    assert result["success"] is False
    assert "不可达" in result["error"]


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
