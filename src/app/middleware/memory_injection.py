"""Memory injection middleware.

Automatically loads recent agent memories from the database and appends
them to the system prompt so the agent has access to persistent context
across conversations.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ResponseT
from langgraph.typing import ContextT

logger = logging.getLogger(__name__)


class MemoryInjectionMiddleware(AgentMiddleware):
    """Middleware that auto-loads memories and injects them into the system prompt.

    On each LLM call, queries the memories table for the most recent 20 entries
    and formats them as a block appended to the system message. If no memories
    exist or the DB query fails, passes through without modification.
    """

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> Any:
        """Load memories and inject into system prompt before LLM call."""
        try:
            memory_block = await self._load_memories()
        except Exception as e:
            logger.warning("[MemoryInjectionMiddleware] Failed to load memories: %s", e)
            return await handler(request)

        if not memory_block:
            return await handler(request)

        # Append memory block to system message
        if isinstance(request.system_message.content, list):
            request.system_message.content = [
                *request.system_message.content,
                {"type": "text", "text": memory_block},
            ]
        else:
            request.system_message.content = request.system_message.content + memory_block

        return await handler(request)

    @staticmethod
    async def _load_memories() -> str:
        """Load recent memories from database and format as injection block.

        Returns:
            Formatted memory block string, or empty string if no memories.
        """
        from sqlalchemy import select

        from src.app.db.database import async_session_factory
        from src.app.db.models.memory import Memory

        async with async_session_factory() as session:
            result = await session.execute(
                select(Memory)
                .where(Memory.space_id == "default")
                .order_by(Memory.updated_at.desc())
                .limit(20)
            )
            memories = result.scalars().all()

        if not memories:
            return ""

        lines = []
        for m in memories:
            category_label = m.category or "未分类"
            lines.append(f"- [{category_label}] {m.key}: {m.content}")

        memory_text = "\n".join(lines)
        return (
            "\n\n"
            "<agent_memories>\n"
            "以下是你之前保存的记忆，请参考这些信息回答用户问题：\n"
            f"{memory_text}\n"
            "</agent_memories>"
        )
