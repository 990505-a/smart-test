"""Agent 记忆注入中间件（harness 风格 Markdown 记忆）。

每次模型调用前，把**启用中的记忆模块**拼成一段块追加到 system prompt 末尾：

    AGENTS.md    工作区指令（必须遵守）
    MEMORY.md    长期记忆
    USER.md      用户画像
    failures.md  失败教训
    PROJECT.md   项目上下文
    DECISIONS.md 决策记录
    （+ 用户自建模块）

装载与裁剪逻辑在 ``services/memory_service.py``（文件是唯一事实源，模块可开关、
可在平台「Agent 记忆」页直接编辑）。这里只负责"把块贴到 system prompt 上"。

块内容对同一份文件是**字节稳定**的（模块列表按 order 排序、只在文件变化后重算），
这样提供方的 prefix 缓存才不会被每次对话打散。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from src.app.core.workspace import get_space_id
from src.app.services.memory_service import build_context_block, invalidate_cache

logger = logging.getLogger(__name__)

__all__ = ["MemoryInjectionMiddleware", "build_memory_catalog", "invalidate_memory_cache"]


def build_memory_catalog(space_id: str | None = None) -> str:
    """当前 space 下启用模块拼出的注入块（空串 = 没有可用记忆）。"""
    return build_context_block(space_id or get_space_id())


def invalidate_memory_cache() -> None:
    """记忆文件变化后由写入方调用（页面保存、agent 写入都会调）。"""
    invalidate_cache()


class MemoryInjectionMiddleware(AgentMiddleware):
    """Append the enabled memory modules to the system prompt on each LLM call."""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> Any:
        try:
            block = build_memory_catalog()
        except Exception as exc:  # noqa: BLE001 — 记忆读不到不该拦住对话
            logger.warning("[MemoryInjectionMiddleware] 记忆加载失败: %s", exc)
            return await handler(request)

        if not block:
            return await handler(request)

        if isinstance(request.system_message.content, list):
            request.system_message.content = [
                *request.system_message.content,
                {"type": "text", "text": block},
            ]
        else:
            request.system_message.content = request.system_message.content + block

        return await handler(request)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> Any:
        """同步路径（子 agent / 摘要调用可能走这里）。"""
        try:
            block = build_memory_catalog()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[MemoryInjectionMiddleware] 记忆加载失败: %s", exc)
            return handler(request)
        if not block:
            return handler(request)
        if isinstance(request.system_message.content, list):
            request.system_message.content = [
                *request.system_message.content, {"type": "text", "text": block},
            ]
        else:
            request.system_message.content = request.system_message.content + block
        return handler(request)
