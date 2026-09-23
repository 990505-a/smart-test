"""工具调用失败 → 错误消息回给模型（失败即反馈）。

LangGraph 的默认工具错误处理器（``prebuilt/tool_node.py`` 的
``_default_handle_tool_errors``）**只把 ToolInvocationError 转成 ToolMessage，
其余异常直接 re-raise 炸掉整个 run**。真实踩到过：模型调 unity_mcp_call，
工具签名不匹配抛 TypeError —— run 当场中断，前端只看到一个空的 error 事件
（``Stream error event: {}``），用户拿不到任何可诊断信息，模型也没有自愈机会。

dsh / Claude Code 这类 harness 的做法是"工具失败就是一条错误结果"：模型
看得见、可以改参数重试或向用户解释。这里在中间件层兜底，把任何工具执行异常
转成 ``ToolMessage(status="error")``。

**必须原样上抛的控制流异常**：LangGraph 的 ``GraphBubbleUp`` 家族
（``GraphInterrupt`` 等）——审批 interrupt 就是从 wrap_tool_call 链里抛出的，
吞掉它等于把审批流程变成"工具报错"。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage


def _pass_through_types() -> tuple[type[BaseException], ...]:
    """控制流异常：不是"工具失败"，必须原样冒泡给 LangGraph。"""
    try:
        from langgraph.errors import GraphBubbleUp

        return (GraphBubbleUp,)
    except Exception:  # noqa: BLE001 — 版本差异：至少别把 interrupt 吞了
        return ()


_PASS_THROUGH = _pass_through_types()


def _error_message(request: Any, exc: BaseException) -> ToolMessage:
    tool_call = getattr(request, "tool_call", None) or {}
    return ToolMessage(
        content=(
            f"Error: 工具执行失败（{type(exc).__name__}）: {exc}\n"
            "请检查参数是否符合工具 schema 后重试；若反复失败，向用户说明并换一条路径。"
        ),
        name=str(tool_call.get("name") or ""),
        tool_call_id=str(tool_call.get("id") or ""),
        status="error",
    )


class ToolErrorFeedbackMiddleware(AgentMiddleware):
    """任何工具异常都变成一条错误 ToolMessage，不炸 run（审批 interrupt 除外）。"""

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        try:
            return await handler(request)
        except BaseException as exc:  # noqa: BLE001 — 见模块说明：失败即反馈
            if _PASS_THROUGH and isinstance(exc, _PASS_THROUGH):
                raise
            if not isinstance(exc, Exception):  # CancelledError 等控制流信号
                raise
            return _error_message(request, exc)

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        try:
            return handler(request)
        except BaseException as exc:  # noqa: BLE001
            if _PASS_THROUGH and isinstance(exc, _PASS_THROUGH):
                raise
            if not isinstance(exc, Exception):
                raise
            return _error_message(request, exc)
