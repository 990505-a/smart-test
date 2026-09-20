"""快速失败（熔断）单测。

测的是 core/breaker.py 的语义边界，以及它真的接进了 service（不是摆着不用的字段）。
"""

from __future__ import annotations

import pytest

from src.app.core import breaker
from src.app.core.config import settings


class FakeClock:
    """可推进的假时钟，避免测试真的 sleep。"""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def guard(clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> breaker.Guard:
    monkeypatch.setattr(settings, "circuit_breaker_fail_max", 3)
    monkeypatch.setattr(settings, "circuit_breaker_reset_timeout", 30)
    return breaker.Guard("测试依赖", clock=clock)


def test_below_threshold_still_allows(guard: breaker.Guard) -> None:
    """失败但没到阈值：照常放行（偶发失败不该被拦）。"""
    guard.fail()
    guard.fail()
    assert guard.blocked() is None


def test_opens_after_threshold(guard: breaker.Guard) -> None:
    for _ in range(3):
        guard.fail()
    reason = guard.blocked()
    assert reason is not None
    assert "测试依赖" in reason and "连续失败 3 次" in reason
    assert "30 秒内不再尝试" in reason


def test_half_open_probe_after_cooldown(guard: breaker.Guard, clock: FakeClock) -> None:
    """冷却过后放行一次探针；探针失败立刻重新打开，不用再攒够阈值。"""
    for _ in range(3):
        guard.fail()
    clock.advance(31)
    assert guard.blocked() is None  # 半开：允许试探

    guard.fail()  # 探针也失败
    assert guard.blocked() is not None  # 立刻重新打开


def test_success_clears_everything(guard: breaker.Guard) -> None:
    """成功一次就清零：服务恢复后不该还欠着历史失败。"""
    guard.fail()
    guard.fail()
    guard.ok()
    guard.fail()
    guard.fail()
    assert guard.blocked() is None  # 计数从 0 重新开始


def test_zero_limit_disables_breaker(guard: breaker.Guard, monkeypatch: pytest.MonkeyPatch) -> None:
    """fail_max=0 = 关闭熔断，退化成"每次都试"。"""
    monkeypatch.setattr(settings, "circuit_breaker_fail_max", 0)
    for _ in range(50):
        guard.fail()
    assert guard.blocked() is None


def test_guards_are_independent(clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    """一个依赖挂了不该连坐另一个。"""
    monkeypatch.setattr(settings, "circuit_breaker_fail_max", 2)
    a = breaker.Guard("A", clock=clock)
    b = breaker.Guard("B", clock=clock)
    a.fail()
    a.fail()
    assert a.blocked() is not None
    assert b.blocked() is None


# ---------------------------------------------------------------------------
# 接入验证：熔断打开时不再走网络（不然"快速失败"只是句口号）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lightrag_skips_network_when_open(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.app.services import lightrag_service

    monkeypatch.setattr(settings, "circuit_breaker_fail_max", 1)
    monkeypatch.setattr(settings, "circuit_breaker_reset_timeout", 60)

    # 任何真实请求都会踩到这里：一旦被调用就说明没走快速失败
    def boom(*_a, **_kw) -> None:
        raise AssertionError("熔断打开时不应该再发请求")

    guard = breaker.Guard("LightRAG")
    monkeypatch.setattr(lightrag_service, "_client", boom)
    # 熔断按**知识库**分别计数（一个库没起不该把其它库也判成不可用），
    # 所以这里替换默认库那把开关。
    monkeypatch.setitem(lightrag_service._guards, "default", guard)

    guard.fail()  # 制造一次失败，阈值=1 于是直接打开
    result = await lightrag_service.health()

    assert result["success"] is False
    assert "熔断中" in result["error"]


@pytest.mark.asyncio
async def test_lightrag_counts_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """打不通才算不可用：连续传输层失败会把熔断打开。"""
    import httpx

    from src.app.services import lightrag_service

    monkeypatch.setattr(settings, "circuit_breaker_fail_max", 2)
    monkeypatch.setattr(settings, "circuit_breaker_reset_timeout", 60)

    class BrokenClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def request(self, *a, **kw):
            raise httpx.ConnectError("connection refused")

    guard = breaker.Guard("LightRAG")
    monkeypatch.setattr(lightrag_service, "_client", lambda *a, **kw: BrokenClient())
    monkeypatch.setitem(lightrag_service._guards, "default", guard)

    first = await lightrag_service.health()
    assert "不可达" in first["error"]
    assert guard.blocked() is None  # 第一次还不开

    await lightrag_service.health()
    assert guard.blocked() is not None  # 第二次到阈值


@pytest.mark.asyncio
async def test_codebase_index_exempt_from_breaker(monkeypatch: pytest.MonkeyPatch) -> None:
    """长任务（全量索引）不受熔断影响：失败一次不代表 exe 不可用。"""
    from src.app.services import codebase_service

    monkeypatch.setattr(settings, "circuit_breaker_fail_max", 1)
    monkeypatch.setattr(codebase_service, "_cbm_guard", breaker.Guard("代码图谱 exe"))
    codebase_service._cbm_guard.fail()  # 熔断已打开

    called: list[str] = []

    def fake_sync(tool_name: str, args: dict, timeout: float, on_log) -> dict:
        called.append(tool_name)
        return {"success": True, "data": {}}

    monkeypatch.setattr(codebase_service, "cbm_cli_sync", fake_sync)

    # 默认（短查询）会被拦
    blocked = await codebase_service.cbm_cli("list_projects", {})
    assert blocked["success"] is False and "熔断中" in blocked["error"]
    assert called == []

    # 显式豁免后照常调用
    allowed = await codebase_service.cbm_cli("index_repository", {}, use_breaker=False)
    assert allowed["success"] is True
    assert called == ["index_repository"]
