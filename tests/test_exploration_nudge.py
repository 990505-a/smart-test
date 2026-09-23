"""探索打转提醒的回归（middleware/exploration_nudge.py）。

用户口径："模型遇到问题的纯探索没有结论的情况下 要进行截图判断 不要硬找"。
这条中间件就是把它变成机制：连探 N 次没看图 → 往上下文补一条"先截图"。

两个必测点：
1. 计数口径（只看本轮、截图清零、别的工具不干扰）；
2. 到阈值才插话，且只在整数倍插（8/16/24…）—— 不能每轮都唠叨。
"""

from __future__ import annotations

from src.app.core.config import settings
from src.app.middleware.exploration_nudge import (
    ExplorationNudgeMiddleware,
    exploration_pressure,
    nudge_message,
)


class _Msg:
    def __init__(self, type: str, *, name: str = "", tool_calls: list | None = None) -> None:
        self.type = type
        self.name = name
        self.tool_calls = tool_calls or []


def _probe(name: str = "unity_exec_csharp") -> _Msg:
    return _Msg("tool", name=name)


def _shot() -> _Msg:
    return _Msg("tool", name="unity_screenshot")


class _Req:
    """够用的假 request：只带 messages；override 返回**换了消息**的新 request。"""

    def __init__(self, messages: list) -> None:
        self.messages = messages

    def override(self, **kwargs):  # noqa: ANN003
        return _Req(kwargs.get("messages", self.messages))


def test_pressure_counts_only_probes_since_last_screenshot():
    messages = [
        _Msg("human"),
        _probe("unity_hierarchy"),
        _probe("unity_console"),
        _Msg("tool", name="read_file"),      # 非 unity 工具不数
        _shot(),
        _probe("unity_exec_csharp"),
    ]

    assert exploration_pressure(messages) == 1


def test_pressure_resets_on_new_human_message():
    messages = [
        _Msg("human"),
        _probe(), _probe(), _probe(),
        _Msg("human"),                        # 新的一轮重新计数
        _probe(),
    ]

    assert exploration_pressure(messages) == 1


def test_pressure_counts_ai_tool_calls_too():
    """模型"发起的调用"在 ai 消息里也有 —— 只数 tool 消息会漏掉正在飞的那一次。"""
    messages = [
        _Msg("human"),
        _Msg("ai", tool_calls=[{"name": "unity_object"}, {"name": "unity_console"}]),
    ]

    assert exploration_pressure(messages) == 2


def _nudged_count(messages: list) -> int:
    """跑一次中间件，看它有没有往上下文里补那条提醒。"""
    middleware = ExplorationNudgeMiddleware()
    request = _Req(messages)
    seen: dict = {}

    def handler(req):  # noqa: ANN001
        seen["messages"] = req.messages
        return "ok"

    middleware.wrap_model_call(request, handler)
    return sum(1 for m in seen["messages"] if "[平台提醒]" in str(getattr(m, "content", "")))


def test_nudge_fires_at_threshold_only():
    original = settings.agent_explore_nudge_after
    try:
        settings.agent_explore_nudge_after = 3

        assert _nudged_count([_Msg("human"), _probe(), _probe()]) == 0        # 2 次：不插话
        assert _nudged_count([_Msg("human"), _probe(), _probe(), _probe()]) == 1   # 3 次：插一条
        assert _nudged_count([_Msg("human")] + [_probe()] * 4) == 0           # 4 次：不是整数倍
        assert _nudged_count([_Msg("human")] + [_probe()] * 6) == 1           # 6 次：再插一条
    finally:
        settings.agent_explore_nudge_after = original


def test_nudge_silent_when_disabled_or_after_screenshot():
    original = settings.agent_explore_nudge_after
    try:
        settings.agent_explore_nudge_after = 0
        assert _nudged_count([_Msg("human")] + [_probe()] * 12) == 0

        settings.agent_explore_nudge_after = 2
        assert _nudged_count([_Msg("human"), _probe(), _shot(), _probe()]) == 0
    finally:
        settings.agent_explore_nudge_after = original


def test_nudge_text_is_actionable():
    text = nudge_message(8)

    assert "unity_screenshot" in text            # 指明用哪个工具
    assert "Play" in text                        # 说清前提
    assert "贴给用户" in text                    # 读不了图时的出路
    assert "别再猜" in text                      # 明确"别硬找"
