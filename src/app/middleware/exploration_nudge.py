"""探索打转提醒：纯探测没有结论时，要求**先截图看一眼**，别硬找。

用户口径（2026-09-23）："模型遇到问题的纯探索没有结论的情况下 要进行截图判断 不要硬找"。
写进技能文档不等于模型会照做 —— 实测里模型会连着十几次探 Lua 字段/组件、越探越深，
而界面上到底长什么样、是不是根本没那个面板，一张图就能说清。这条中间件在**每次模型
调用前**看一眼最近的工具调用序列：自上次截图以来，这一轮的探测类工具已经调了 N 次
（`settings.agent_explore_nudge_after`，默认 8，0 = 关）就补一条系统提醒。

几个刻意的选择：

* **只在整数倍处提醒**（8、16、24…）：不用记状态，也不会每轮都唠叨;模型照做之后
  计数自然归零（截图会把计数清零）。
* **看的是"工具调用序列"而不是模型的自述**：模型说"我再确认一下"没有意义，
  `unity_console`/`unity_exec_csharp`/`unity_hierarchy` 这些**探测**才算。
* **范围只覆盖 Unity 系工具**（`unity_` 前缀）：这条规则来自 Unity 自动化的实战，
  别的领域（写代码、查图谱）本来就有各自的证据形式，不该被它打断。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage

from src.app.core.config import settings

#: 探测类工具的前缀与"算看过画面"的那个工具名。
_PROBE_PREFIX = "unity_"
_VISUAL_TOOL = "unity_screenshot"


def exploration_pressure(messages: list[Any], *,
                         prefix: str = _PROBE_PREFIX,
                         visual_tool: str = _VISUAL_TOOL) -> int:
    """自上次截图以来，这一轮里探测类工具调用了多少次（纯函数，方便测）。

    - 只看**最后一条 human 消息之后**的调用（新的一轮重新计数）；
    - 数的是"探测"调用：前缀匹配、且不是截图工具本身；
    - 遇到截图调用就归零（"已经看过了"）。
    """
    pressure = 0
    for msg in messages:
        kind = str(getattr(msg, "type", "") or "").lower()
        if kind in ("human", "user"):
            pressure = 0
            continue
        calls: list[Any] = []
        if kind in ("ai", "assistant"):
            calls = list(getattr(msg, "tool_calls", None) or [])
        elif kind == "tool":
            calls = [{"name": getattr(msg, "name", "")}]
        for call in calls:
            name = ""
            if isinstance(call, dict):
                name = str(call.get("name") or "")
            else:
                name = str(getattr(call, "name", "") or "")
            if not name.startswith(prefix):
                continue
            if name == visual_tool:
                pressure = 0
            else:
                pressure += 1
    return pressure


def nudge_message(pressure: int) -> str:
    """达到阈值时补进上下文的那段话（人话、可执行、给出两条路）。"""
    return (
        f"[平台提醒] 你已经连续做了 {pressure} 次探测（查组件 / 读数据 / 跑 C#），"
        "却没有看一眼画面 —— 典型的「越探越深但没结论」。**先截图再继续**：\n"
        "① 调 `unity_screenshot`（游戏要在 Play 里跑着）。能读图就直接看："
        "界面上到底有没有那个入口/按钮、面板是不是真的打开了、有没有被别的层挡住 —— "
        "这些问题读数据回答不了，图一眼就能回答；\n"
        "② 如果你的模型读不了图（平台会给你「图片未发送」的说明），"
        "就把截图路径**原样贴给用户**请他确认，并明说「我看不了图」；\n"
        "③ 有了图再决定下一步：图里没有 → 别再猜对象名/字段名，问用户或换一条路；"
        "图里有 → 按图上的位置与文字继续。\n"
        "只有确实与画面无关的活儿（纯数据核对、跑用例脚本）才可以跳过这一步。"
    )


class ExplorationNudgeMiddleware(AgentMiddleware):
    """纯探测打转时，往上下文补一条"先截图"的提醒。"""

    def _nudged(self, request: Any) -> Any:
        limit = int(getattr(settings, "agent_explore_nudge_after", 0) or 0)
        if limit <= 0:
            return request
        messages = list(getattr(request, "messages", None) or [])
        pressure = exploration_pressure(messages)
        if pressure < limit or pressure % limit != 0:
            return request
        return request.override(messages=[*messages, SystemMessage(content=nudge_message(pressure))])

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        return await handler(self._nudged(request))

    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        return handler(self._nudged(request))
