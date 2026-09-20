"""Per-conversation model selection (RunModelMiddleware).

对话页可以按会话挑一个**模型预设**（设置页里存的那套：模型名 + 端点 + Key），
前端把它放进 run 的 ``configurable.model_preset``；本中间件在模型调用前把它解析成
真实的模型对象，并 ``request.override(model=...)``。

为什么必须在这一层做：模型是图编译期由 ``harness.build_agent`` 固定的，运行期唯一
能换模型的入口就是 ``wrap_model_call`` 的 override —— 与 live_model_reload /
thinking_effort 是同一个机制。

洋葱位置是硬约束：必须排在 ``ThinkingEffortMiddleware`` **内侧**（更靠后）。
两个中间件都会 override 模型，谁更靠内谁最后写、谁生效。本中间件最后写，并且自己
把本轮的 ``llm_reasoning_effort`` 一起带上（外层的 effort override 会被这里盖掉，
所以不能指望它）——这样「选中的预设」与「本轮的思考强度」两者都生效。

预设值只在**本进程**读取（agent 进程与 FastAPI 共用一个 SQLite 文件，只读一行
``settings_kv``），不写回 ``.env``，所以选模型是**按会话**的，不会改掉别人的默认模型。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ResponseT
from langchain_core.language_models import BaseChatModel
from langgraph.typing import ContextT

from src.app.agents.testcase.model_factory import build_model_from_values
from src.app.middleware.thinking_effort import configurable_value, current_effort

logger = logging.getLogger(__name__)

#: 预设名+effort -> (过期时刻, 模型)。预设很少改，缓存一会儿可以省掉每次模型调用
#: 的一次 DB 读；代价是设置页改完预设后，最多这个秒数之后新的会话才用上新值。
_DEFAULT_TTL = 30.0


def model_values(preset: dict) -> dict:
    """预设条目 -> 交给模型工厂的配置。

    只保留 ``MODEL_KEYS`` 里的键：预设是整体存下来的 JSON，老预设里可能还留着
    平台已经不再使用的键（例如已下线的视觉模型三项），不能原样喂给工厂。
    """
    from src.app.services.settings_service import MODEL_KEYS

    return {
        k: v for k, v in (preset.get("values") or {}).items() if k in MODEL_KEYS
    }


class RunModelMiddleware(AgentMiddleware):
    """Use the model preset a run asked for instead of the global model."""

    def __init__(self, cache_ttl: float = _DEFAULT_TTL) -> None:
        self._ttl = cache_ttl
        self._cache: dict[str, tuple[float, BaseChatModel]] = {}

    # -- hooks ---------------------------------------------------------------

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> Any:
        model = await self._selected_model()
        if model is None:
            return await handler(request)
        return await handler(request.override(model=model))

    def wrap_model_call(self, request, handler):  # noqa: ANN001 — sync twin
        """同步路径：只认 ``abefore_agent`` 预热好的缓存。

        平台全程走 astream/ainvoke（异步），所以同步分支正常不会命中；真有哪条路
        走到这里时也**不能**再读 DB（此处不能 await），于是沿用默认模型。
        """
        model = self._cached(self._cache_key())
        if model is None:
            return handler(request)
        return handler(request.override(model=model))

    async def abefore_agent(self, state: Any, runtime: Any) -> None:  # noqa: ANN001
        """预热缓存：让同步分支也有机会拿到本轮选中的模型。"""
        await self._selected_model()

    # -- resolution ----------------------------------------------------------

    def _cache_key(self) -> str:
        return f"{configurable_value('model_preset')}|{current_effort() or ''}"

    def _cached(self, key: str) -> BaseChatModel | None:
        hit = self._cache.get(key)
        if hit is None or hit[0] <= time.monotonic():
            return None
        return hit[1]

    async def _selected_model(self) -> BaseChatModel | None:
        """本轮选中的模型；没选、找不到预设或构建失败都返回 None（沿用默认）。"""
        name = configurable_value("model_preset")
        if not name:
            return None

        key = self._cache_key()
        cached = self._cached(key)
        if cached is not None:
            return cached

        values = await self._preset_values(name)
        if values is None:
            return None
        try:
            model = build_model_from_values(values, effort=current_effort() or "")
        except Exception:  # noqa: BLE001 — 预设坏了不该让整个 run 挂掉
            logger.exception("模型预设 %r 构建失败；本轮沿用默认模型", name)
            return None

        self._cache[key] = (time.monotonic() + self._ttl, model)
        return model

    @staticmethod
    async def _preset_values(name: str) -> dict | None:
        from src.app.db.database import async_session_factory
        from src.app.services.settings_service import MODEL_KEYS, SettingsService

        try:
            async with async_session_factory() as session:
                preset = await SettingsService(session).get_preset(name)
        except Exception:  # noqa: BLE001 — DB 读失败不该让整个 run 挂掉
            logger.exception("读取模型预设 %r 失败；本轮沿用默认模型", name)
            return None

        if not preset:
            logger.warning("模型预设 %r 不存在（可能已在设置页删除）；本轮沿用默认模型", name)
            return None
        return model_values(preset)
