"""Memory injection middleware — catalog-style progressive disclosure.

Injects a compact catalog of saved memories (category + key + content preview)
into the system prompt so the agent knows WHAT it remembers, while full
contents stay retrievable on demand via the search_memories tool. The
formatted block is cached (TTL-bounded) and invalidated whenever memories are
written in-process (agent save_memory tool or REST service layer), so the
per-call read path adds no DB round-trip and the system prompt stays
byte-stable across turns — provider-side prompt caches stay valid and
prefill cost does not grow with memory count.

The LangGraph agent server and FastAPI run as separate processes: REST edits
reach the agent process through the TTL bound (worst case one TTL window).
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ResponseT
from langgraph.typing import ContextT

logger = logging.getLogger(__name__)

# Catalog shape: entry count, per-entry preview length, and total block size
# are all bounded so the injected prefix has a fixed memory footprint.
MAX_ENTRIES = 15
PREVIEW_CHARS = 80
MAX_BLOCK_CHARS = 2_000
CACHE_TTL_SECONDS = 60.0

# Module aliases this file may be imported under ("app." vs "src.app.") —
# invalidation must clear every loaded copy so cache globals can't diverge.
_MODULE_ALIASES = (
    "app.middleware.memory_injection",
    "src.app.middleware.memory_injection",
)

_cached_block: str | None = None
_cached_at: float = 0.0


def invalidate_memory_cache() -> None:
    """Drop the cached memory catalog under every loaded module alias.

    Call after any memory write (agent tool or REST service layer).
    """
    for name in _MODULE_ALIASES:
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "_cached_block", None) is not None:
            mod._cached_block = None
            mod._cached_at = 0.0


class MemoryInjectionMiddleware(AgentMiddleware):
    """Append a compact memory catalog to the system prompt on each LLM call.

    The block is identical across calls until memories change, keeping the
    prompt prefix stable for provider-side context caching.
    """

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> Any:
        """Load the memory catalog and inject it into the system prompt."""
        try:
            memory_block = await self._load_memory_catalog()
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
    async def _load_memory_catalog() -> str:
        """Build (or reuse) the cached catalog block. Empty string when no memories."""
        global _cached_block, _cached_at

        now = time.monotonic()
        if _cached_block is not None and now - _cached_at < CACHE_TTL_SECONDS:
            return _cached_block

        from sqlalchemy import select

        from src.app.db.database import async_session_factory
        from src.app.db.models.memory import Memory

        async with async_session_factory() as session:
            result = await session.execute(
                select(Memory)
                .where(Memory.space_id == "default")
                .order_by(Memory.updated_at.desc())
                .limit(MAX_ENTRIES)
            )
            memories = result.scalars().all()

        if not memories:
            _cached_block, _cached_at = "", now
            return ""

        lines = []
        for m in memories:
            category_label = m.category or "未分类"
            preview = (m.content or "").strip().replace("\n", " ")
            if len(preview) > PREVIEW_CHARS:
                preview = preview[:PREVIEW_CHARS] + "…"
            lines.append(f"- [{category_label}] {m.key}: {preview}")

        memory_text = "\n".join(lines)
        if len(memory_text) > MAX_BLOCK_CHARS:
            memory_text = memory_text[:MAX_BLOCK_CHARS] + "\n…（已截断，更多记忆用 search_memories 查询）"

        block = (
            "\n\n"
            "<agent_memories>\n"
            "以下是你之前保存的记忆目录（仅摘要）。需要完整内容时用 search_memories 工具按关键词查询：\n"
            f"{memory_text}\n"
            "</agent_memories>"
        )
        _cached_block, _cached_at = block, now
        return block
