"""Agent memory tools for persistent memory save and search.

Per D-05/D-06: Agent tools write directly to database via SQLAlchemy session.
Uses async_session_factory to bypass FastAPI dependency injection.
"""

from langchain_core.tools import tool
from sqlalchemy import or_, select

from src.app.db.database import async_session_factory
from src.app.db.models.memory import Memory


async def _invalidate_memory_cache() -> None:
    """Invalidate the middleware's memory-catalog cache after a write.

    Imported lazily so this module works in both the agent-server and
    FastAPI processes regardless of which alias is importable there.
    """
    try:
        from src.app.middleware.memory_injection import invalidate_memory_cache
    except ImportError:
        from app.middleware.memory_injection import invalidate_memory_cache
    invalidate_memory_cache()


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
        Dict with success status and memory_id.
    """
    async with async_session_factory() as session:
        try:
            # Check if a memory with same key already exists for default space
            result = await session.execute(
                select(Memory).where(
                    Memory.space_id == "default",
                    Memory.key == key,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing memory (upsert)
                existing.content = content
                if category is not None:
                    existing.category = category
                from sqlalchemy import func
                existing.updated_at = func.now()
                await session.commit()
                await _invalidate_memory_cache()
                return {
                    "success": True,
                    "memory_id": str(existing.id),
                    "key": key,
                    "is_update": True,
                }
            else:
                # Create new memory
                memory = Memory(
                    space_id="default",
                    key=key,
                    content=content,
                    category=category,
                )
                session.add(memory)
                await session.commit()
                await _invalidate_memory_cache()
                return {
                    "success": True,
                    "memory_id": str(memory.id),
                    "key": key,
                    "is_update": False,
                }
        except Exception as e:
            await session.rollback()
            return {"success": False, "error": str(e)}


@tool
async def search_memories(
    query: str,
    limit: int = 10,
) -> dict:
    """Search saved memories by keyword. Use this when you need to recall previously saved information.

    Args:
        query: Search term to find in memory keys or content.
        limit: Maximum number of results to return (default 10).

    Returns:
        Dict with success and memories list.
    """
    async with async_session_factory() as session:
        try:
            result = await session.execute(
                select(Memory)
                .where(
                    Memory.space_id == "default",
                    or_(
                        Memory.key.ilike(f"%{query}%"),
                        Memory.content.ilike(f"%{query}%"),
                    ),
                )
                .order_by(Memory.updated_at.desc())
                .limit(limit)
            )
            memories = result.scalars().all()

            if not memories:
                return {
                    "success": True,
                    "memories": [],
                    "count": 0,
                    "message": f"No memories found matching '{query}'",
                }

            return {
                "success": True,
                "memories": [
                    {
                        "id": str(m.id),
                        "key": m.key,
                        "content": m.content,
                        "category": m.category,
                        "updated_at": str(m.updated_at) if m.updated_at else str(m.created_at),
                    }
                    for m in memories
                ],
                "count": len(memories),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
