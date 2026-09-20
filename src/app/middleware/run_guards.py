"""单轮 run 的资源上限（直接用官方中间件，不自己写）。

起因是一次实测：一个 run 跑了 35 分钟才结束，期间前端收不到任何事件，界面只能提示
"疑似卡死"。根因是多重的（模型请求没有超时、流量走了系统代理），但**没有任何上限**
这件事是共同的放大器：跑飞或卡住的 run 会一直占着 LangGraph 的 4 个 worker 之一，
直到进程重启。

官方 ``langchain.agents.middleware`` 已经提供了两个现成的守卫，不需要自己写：

* ``ModelCallLimitMiddleware(run_limit=N, exit_behavior="end")``
  —— 一轮 run 里模型调用超过 N 次就**优雅结束**这一轮（不是抛错）。
* ``ToolCallLimitMiddleware(run_limit=N, exit_behavior="continue")``
  —— 工具调用超过 N 次后**拦住后续工具调用**，让模型带着已有结果收尾。

阈值由 ``settings.agent_run_*_limit`` 给（0 = 不限制）。取的是"远高于正常用量"的
数字：正常生成一轮用例大约 30-60 次模型调用，120 是"明显不对劲"的界线——宁可晚一点
拦住，也不要误伤正常的长任务。

**没有加 ``ToolRetryMiddleware``**：它只在工具**抛异常**时重试，而平台的工具普遍设了
``handle_tool_error=True``（异常被转成 ToolMessage），所以它基本不会触发；而一旦触发，
被重试的可能是 ``approve_case_document`` 这类有副作用的工具，重放语义不明确。收益小、
风险实在，先不加。
"""

from __future__ import annotations

from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware

from src.app.core.config import settings

__all__ = ["build_run_guards"]


def build_run_guards() -> list:
    """按平台配置构造单轮 run 的调用上限中间件（不限制时返回空列表）。"""
    guards: list = []
    if settings.agent_run_model_call_limit > 0:
        guards.append(
            ModelCallLimitMiddleware(
                run_limit=settings.agent_run_model_call_limit,
                exit_behavior="end",
            )
        )
    if settings.agent_run_tool_call_limit > 0:
        guards.append(
            ToolCallLimitMiddleware(
                run_limit=settings.agent_run_tool_call_limit,
                exit_behavior="continue",
            )
        )
    return guards
