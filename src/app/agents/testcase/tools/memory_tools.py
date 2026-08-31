"""Agent memory tools backed by EverOS (记忆模块).

save_memory: 单条显式记忆 → EverOS add + flush 立即蒸馏固化（一次 LLM
边界检测 + 一次蒸馏调用，保存是低频操作，成本可接受）。
search_memories: EverOS 检索（有 embedding key 时 hybrid，否则 jieba
关键词），返回主题+摘要，比旧版 ILIKE 命中率高。

服务不可用/未配置时返回 success=False 让 LLM 自行决定如何提示用户，
不抛异常打断对话流。
"""

import logging

from langchain_core.tools import tool

from src.app.services import everos_service
from src.app.services.everos_service import EverosError

logger = logging.getLogger(__name__)


@tool
async def save_memory(
    key: str,
    content: str,
    category: str | None = None,
) -> dict:
    """Save a piece of information to persistent memory. Use this when the user explicitly asks you to remember something, or when they share important context that should persist across conversations (e.g. preferences, domain knowledge, project-specific rules).

    Args:
        key: Short identifier for this memory (e.g. "user_preference_language", "project_name_mapping").
        content: The actual content to remember. Be specific and detailed.
        category: Optional category for grouping (e.g. "preference", "domain_knowledge", "project_context", "convention").

    Returns:
        Dict with success status.
    """
    try:
        result = await everos_service.save_fact(key, content, category)
        return {
            "success": True,
            "key": key,
            "category": category,
            "flush_status": (result.get("flush") or {}).get("status"),
        }
    except EverosError as e:
        logger.warning("[save_memory] EverOS 不可用: %s", e)
        return {"success": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        logger.exception("[save_memory] 保存失败")
        return {"success": False, "error": str(e)}


@tool
async def search_memories(
    query: str,
    limit: int = 8,
) -> dict:
    """Search saved memories. Use this when you need to recall previously saved information (domain rules, user preferences, past lessons about a game module).

    Args:
        query: Search keywords, Chinese preferred (e.g. "联赛 结算 边界").
        limit: Maximum number of results to return (default 8).

    Returns:
        Dict with success and memories list (subject + summary each).
    """
    try:
        hits = await everos_service.search_memory(query, top_k=limit)
        if not hits:
            return {
                "success": True,
                "memories": [],
                "count": 0,
                "message": f"No memories found matching '{query}'",
            }
        return {"success": True, "memories": hits, "count": len(hits)}
    except EverosError as e:
        logger.warning("[search_memories] EverOS 不可用: %s", e)
        return {"success": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        logger.exception("[search_memories] 检索失败")
        return {"success": False, "error": str(e)}
