"""单轮 run 的资源上限（直接用官方中间件，不自己写）。

**默认关闭（阈值为 0 = 不挂任何守卫）**。2026-09-23 的取舍：这两个闸当初是为"一个 run
跑了 35 分钟、前端收不到任何事件、还占着 worker"加的，但它们**按次数一刀切**，真实
使用里误伤得太狠 —— 一次长探索（反射 Lua、逐个探对象）轻松过 120 次模型调用，于是
一轮做到一半被硬收尾，界面上只留一句英文的 "Model call limits exceeded: run limit
(120/120)"，看着像报错。

原来要防的那件事改用**看得见**的做法兜（比计数闸更准，也不会误伤）：聊天页运行中显示
"已 X 分钟 · 第 N 步"，静默超过 90s 就给提示并高亮「停止」按钮 —— 人随时知道它活着、
卡住了、以及怎么停。要重新打开这两个闸就把阈值设成正整数（``.env`` 的
``AGENT_RUN_MODEL_CALL_LIMIT`` / ``AGENT_RUN_TOOL_CALL_LIMIT``，改完重启 langgraph）。

官方 ``langchain.agents.middleware`` 的两个守卫（打开时用）：

* ``ModelCallLimitMiddleware(run_limit=N, exit_behavior="end")``
  —— 一轮 run 里模型调用超过 N 次就**优雅结束**这一轮（不是抛错）。
* ``ToolCallLimitMiddleware(run_limit=N, exit_behavior="continue")``
  —— 工具调用超过 N 次后**拦住后续工具调用**，让模型带着已有结果收尾。

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
