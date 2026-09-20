"""Live model reload middleware.

The settings page saves model changes to .env (via SettingsService.sync_env_file).
This middleware stats that file before every model call and, when it changed,
re-reads the model config and overrides the request's model with a freshly
built one — so saved settings take effect on the very next turn, without
restarting the LangGraph agent process.

Must sit ABOVE ThinkingEffortMiddleware and RunModelMiddleware in the
onion: refresh_from_env() mutates the global settings and clears the
effort-variant cache, so the inner middlewares rebuild their variants from
the new values.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ResponseT
from langgraph.typing import ContextT

from src.app.agents.testcase.model_factory import build_chat_model, refresh_from_env

logger = logging.getLogger(__name__)


class LiveModelReloadMiddleware(AgentMiddleware):
    """Re-read .env before each model call; override the model when it changed."""

    def before_agent(self, state: Any, runtime: Any) -> None:  # noqa: ANN001
        self._refresh_early()

    async def abefore_agent(self, state: Any, runtime: Any) -> None:  # noqa: ANN001
        self._refresh_early()

    @staticmethod
    def _refresh_early() -> None:
        """run 开始前也刷一次 .env。

        为什么需要这第二次刷新：``wrap_model_call`` 里那次发生在 **before_agent
        之后**，而记忆中间件在 before_agent 就按 ``settings.memory_enabled`` 算出了
        "这次读哪些文件"——于是刚在页面上关掉总闸的第一轮仍会读到上一轮的值
        （实测现象：关闸后第一轮的 state 里还有 6 份 memory_contents）。本中间件在
        onion 上位于记忆中间件之外，所以这里的 before_agent 先跑，sources 跟着新值走。
        """
        try:
            refresh_from_env()
        except Exception:  # noqa: BLE001 — 刷新失败不该阻断 run
            logger.exception("before_agent 阶段的 .env 刷新失败；沿用当前配置")

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> Any:
        try:
            if refresh_from_env():
                logger.info("model settings changed in .env — rebuilding chat model")
                request = request.override(model=build_chat_model())
        except Exception:  # noqa: BLE001 — reload failure must never kill the run
            logger.exception("live model reload failed; keeping the current model")
        return await handler(request)
