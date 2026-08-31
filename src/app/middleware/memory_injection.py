"""Memory injection middleware — catalog-style progressive disclosure.

扫 EverOS 记忆根目录下的 Markdown 文件（episode / 原子事实 / 技能），把
最近的主题行做成紧凑目录注入 system prompt——agent 知道"记得什么"，完整
内容按需通过 search_memories 工具（EverOS 语义/关键词检索）获取。

设计约束（与旧版 DB 目录一致）：
- 注入块在记忆未变时**字节级稳定**，保住 DeepSeek/GLM 端的前缀缓存；
- 目录条目数、单条长度、总块大小全部有界（MAX_ENTRIES/PREVIEW_CHARS/
  MAX_BLOCK_CHARS）；
- 块缓存 TTL 秒级过期即可——记忆写入发生在独立的 EverOS 进程里，
  本进程无法收到失效通知，TTL 是唯一的最终一致窗口。

记忆文件格式（EverOS 生成）：YAML frontmatter + `### Subject` 小节。
解析只认 Subject 行与 `## ` 标题，格式变化时降级为空目录，不抛错。
"""

from __future__ import annotations

import logging
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

_cached_block: str | None = None
_cached_at: float = 0.0


def invalidate_memory_cache() -> None:
    """Drop the cached memory catalog immediately.

    Kept for callers (e.g. REST layer) that want instant visibility after a
    manual file edit; cross-process edits still rely on the TTL bound.
    """
    global _cached_block, _cached_at
    _cached_block = None
    _cached_at = 0.0


def _parse_subjects(text: str, limit: int) -> list[str]:
    """提取 episode 文件里的 Subject 行；兼容画像/技能的 `## ` 标题。

    EverOS 生成的 episode 正文自带 `## ep_2026…` 内部 ID 标题——那是定位
    标记不是主题，过滤掉（atomic fact 的 `## af_…` 同理）。
    """
    import re

    _id_heading = re.compile(r"^(ep|af|mc)_\d+", re.IGNORECASE)
    subjects: list[str] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "### Subject":
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if nxt:
                subjects.append(nxt)
        elif stripped.startswith("## ") and not _id_heading.match(stripped[3:].strip()):
            subjects.append(stripped[3:].strip())
        if len(subjects) >= limit:
            break
    return subjects


def _collect_catalog_entries() -> list[tuple[str, str]]:
    """扫记忆根目录，返回 [(日期或track标签, subject), ...]（最新优先）。

    只收 episodes/*.md 与 user.md 画像：原子事实文件的标题是内部 ID，
    对目录没有可读价值；完整内容检索交给 search_memories。
    """
    import re

    from src.app.core.config import settings
    from src.app.services.everos_service import memory_root

    if not settings.everos_enabled:
        return []
    root = memory_root()
    if not root.is_dir():
        return []

    md_files = [
        p for p in root.rglob("*.md")
        if p.is_file() and ("episodes" in p.parts or p.name == "user.md")
    ]
    md_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    entries: list[tuple[str, str]] = []
    for path in md_files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", path.stem)
        date = m.group(0) if m else ("画像" if path.name == "user.md" else path.parent.name)
        for subject in _parse_subjects(text, MAX_ENTRIES):
            entries.append((date, subject))
        if len(entries) >= MAX_ENTRIES:
            break
    return entries[:MAX_ENTRIES]


def build_memory_catalog() -> str:
    """构建（或复用缓存）目录块。无记忆时返回空串。"""
    global _cached_block, _cached_at

    now = time.monotonic()
    if _cached_block is not None and now - _cached_at < CACHE_TTL_SECONDS:
        return _cached_block

    try:
        entries = _collect_catalog_entries()
    except Exception as exc:  # noqa: BLE001 — 目录解析失败不阻断对话
        logger.warning("[MemoryInjectionMiddleware] 扫描记忆目录失败: %s", exc)
        entries = []

    if not entries:
        _cached_block, _cached_at = "", now
        return ""

    lines = []
    for date, subject in entries:
        preview = subject.replace("\n", " ").strip()
        if len(preview) > PREVIEW_CHARS:
            preview = preview[:PREVIEW_CHARS] + "…"
        lines.append(f"- [{date}] {preview}")

    memory_text = "\n".join(lines)
    if len(memory_text) > MAX_BLOCK_CHARS:
        memory_text = memory_text[:MAX_BLOCK_CHARS] + "\n…（已截断，更多记忆用 search_memories 查询）"

    block = (
        "\n\n"
        "<agent_memories>\n"
        "以下是你长期记忆的目录（EverOS 持久化，仅主题摘要）。需要完整内容时用 search_memories 工具按关键词查询：\n"
        f"{memory_text}\n"
        "</agent_memories>"
    )
    _cached_block, _cached_at = block, now
    return block


class MemoryInjectionMiddleware(AgentMiddleware):
    """Append a compact memory catalog to the system prompt on each LLM call.

    The block is identical across calls until the memory files change,
    keeping the prompt prefix stable for provider-side context caching.
    """

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> Any:
        """Load the memory catalog and inject it into the system prompt."""
        try:
            memory_block = build_memory_catalog()
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
