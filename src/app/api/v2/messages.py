"""Paginated messages endpoint for thread conversation history.

Uses a local SQLite message store (thread_messages table) for fast
paginated retrieval of chat history, avoiding the need to load the
full thread state from the LangGraph API (which fails for large threads).

Architecture:
- Messages are saved to SQLite by the frontend after streaming completes
  (POST /api/v2/threads/{thread_id}/messages/save).
- History is loaded from SQLite (this endpoint), which works for any thread size.
- Fallback: if no messages are found in SQLite for a thread, tries get_state()
  from LangGraph API (backward compatibility with existing small threads).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from src.app.core.config import settings
from src.app.db.database import async_session_factory
from src.app.db.models.thread_info import ThreadInfo
from src.app.db.models.thread_message import ThreadMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/threads")


# ---------------------------------------------------------------------------
# Thread CRUD: persist thread metadata in SQLite for survival across restarts
# ---------------------------------------------------------------------------

class ThreadCreateRequest(BaseModel):
    thread_id: str
    title: str = "无标题对话"


class ThreadUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None


@router.get(
    "",
    summary="List all persisted threads",
    description="Returns thread list from SQLite, sorted by updated_at desc. Survives LangGraph restarts.",
)
async def list_threads(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    async with async_session_factory() as session:
        total_stmt = select(func.count()).select_from(ThreadInfo)
        total = (await session.execute(total_stmt)).scalar() or 0

        stmt = (
            select(ThreadInfo)
            .order_by(ThreadInfo.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        threads = result.scalars().all()

        return {
            "threads": [
                {
                    "thread_id": t.thread_id,
                    "title": t.title,
                    "description": t.description,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                }
                for t in threads
            ],
            "total": total,
        }


@router.post(
    "",
    summary="Persist a new thread",
    description="Register a thread in SQLite so it survives LangGraph restarts.",
)
async def create_thread(request: ThreadCreateRequest) -> dict[str, Any]:
    async with async_session_factory() as session:
        existing = await session.execute(
            select(ThreadInfo).where(ThreadInfo.thread_id == request.thread_id)
        )
        if existing.scalar_one_or_none():
            return {"success": True, "thread_id": request.thread_id, "created": False}

        info = ThreadInfo(thread_id=request.thread_id, title=request.title)
        session.add(info)
        await session.commit()
        return {"success": True, "thread_id": request.thread_id, "created": True}


@router.patch(
    "/{thread_id}",
    summary="Update thread metadata",
    description="Update title/description for a persisted thread.",
)
async def update_thread(thread_id: str, request: ThreadUpdateRequest) -> dict[str, Any]:
    async with async_session_factory() as session:
        stmt = select(ThreadInfo).where(ThreadInfo.thread_id == thread_id)
        result = await session.execute(stmt)
        info = result.scalar_one_or_none()
        if not info:
            raise HTTPException(status_code=404, detail="Thread not found")

        if request.title is not None:
            info.title = request.title
        if request.description is not None:
            info.description = request.description
        await session.commit()
        return {"success": True, "thread_id": thread_id}


@router.delete(
    "/{thread_id}",
    summary="Delete a persisted thread and its messages",
    description="Remove thread metadata and all associated messages from SQLite.",
)
async def delete_thread(thread_id: str) -> dict[str, Any]:
    async with async_session_factory() as session:
        # Delete messages first
        msgs = await session.execute(
            select(ThreadMessage).where(ThreadMessage.thread_id == thread_id)
        )
        for msg in msgs.scalars().all():
            await session.delete(msg)

        # Delete thread info
        info_stmt = select(ThreadInfo).where(ThreadInfo.thread_id == thread_id)
        info_result = await session.execute(info_stmt)
        info = info_result.scalar_one_or_none()
        if info:
            await session.delete(info)

        await session.commit()
        return {"success": True, "thread_id": thread_id}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class MessageInput(BaseModel):
    """A single message sent from the frontend for storage."""
    id: str
    type: str  # human, ai, tool, system
    content: Any = ""
    additional_kwargs: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    name: str | None = None


class SaveMessagesRequest(BaseModel):
    """Request body for saving messages after streaming."""
    messages: list[MessageInput]


# ---------------------------------------------------------------------------
# Helper: serialize a ThreadMessage row to a dict matching PaginatedMessage
# ---------------------------------------------------------------------------

def _row_to_dict(row: ThreadMessage) -> dict[str, Any]:
    """Convert a ThreadMessage row to the API response dict."""
    content: Any = row.content
    # Try to parse JSON content (structured content like [{type: text, text: ...}])
    if content and content.startswith("["):
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            pass

    additional_kwargs = None
    if row.additional_kwargs:
        try:
            additional_kwargs = json.loads(row.additional_kwargs)
        except (json.JSONDecodeError, ValueError):
            additional_kwargs = {}

    tool_calls = None
    if row.tool_calls:
        try:
            tool_calls = json.loads(row.tool_calls)
        except (json.JSONDecodeError, ValueError):
            tool_calls = None

    return {
        "id": row.message_id,
        "type": row.msg_type,
        "content": content,
        "additional_kwargs": additional_kwargs or {},
        "tool_calls": tool_calls,
        "name": row.name,
    }


# ---------------------------------------------------------------------------
# Helper: serialize a LangGraph message (for fallback)
# ---------------------------------------------------------------------------

def _serialize_message(msg: Any) -> dict[str, Any]:
    """Serialize a LangGraph message (dict or object) to a JSON-safe dict."""
    if isinstance(msg, dict):
        return {
            "id": msg.get("id"),
            "type": msg.get("type"),
            "content": msg.get("content"),
            "additional_kwargs": msg.get("additional_kwargs", {}),
            "tool_calls": msg.get("tool_calls"),
            "name": msg.get("name"),
        }

    return {
        "id": getattr(msg, "id", None),
        "type": getattr(msg, "type", None),
        "content": getattr(msg, "content", None),
        "additional_kwargs": getattr(msg, "additional_kwargs", {}),
        "tool_calls": getattr(msg, "tool_calls", None),
        "name": getattr(msg, "name", None),
    }


# ---------------------------------------------------------------------------
# Helper: serialize message content for storage
# ---------------------------------------------------------------------------

def _serialize_content(content: Any) -> str:
    """Serialize message content to a string for SQLite storage."""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# POST endpoint: save messages after streaming
# ---------------------------------------------------------------------------

@router.post(
    "/{thread_id}/messages/save",
    summary="Save messages to local store",
    description="Saves completed messages from a streaming session to the local database for fast paginated retrieval.",
)
async def save_thread_messages(
    thread_id: str,
    request: SaveMessagesRequest,
) -> dict[str, Any]:
    """Save messages from the frontend to the local SQLite store.

    Uses UPSERT logic: if a message with the same message_id already exists,
    it is updated (handles re-sends and message edits during streaming).
    """
    saved_count = 0
    updated_count = 0

    async with async_session_factory() as session:
        for msg in request.messages:
            if not msg.id or not msg.type:
                continue

            # Check if message already exists
            stmt = select(ThreadMessage).where(ThreadMessage.message_id == msg.id)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            content_str = _serialize_content(msg.content)
            additional_kwargs_str = (
                json.dumps(msg.additional_kwargs, ensure_ascii=False, default=str)
                if msg.additional_kwargs
                else None
            )
            tool_calls_str = (
                json.dumps(msg.tool_calls, ensure_ascii=False, default=str)
                if msg.tool_calls
                else None
            )

            if existing:
                # Update existing message
                existing.content = content_str
                existing.additional_kwargs = additional_kwargs_str
                existing.tool_calls = tool_calls_str
                existing.name = msg.name
                updated_count += 1
            else:
                # Get next seq_index for this thread
                max_idx_stmt = select(func.max(ThreadMessage.seq_index)).where(
                    ThreadMessage.thread_id == thread_id
                )
                max_idx_result = await session.execute(max_idx_stmt)
                max_idx = max_idx_result.scalar() or 0

                new_msg = ThreadMessage(
                    thread_id=thread_id,
                    message_id=msg.id,
                    msg_type=msg.type,
                    content=content_str,
                    additional_kwargs=additional_kwargs_str,
                    tool_calls=tool_calls_str,
                    name=msg.name,
                    seq_index=max_idx + 1,
                )
                session.add(new_msg)
                saved_count += 1

        await session.commit()

    return {
        "saved": saved_count,
        "updated": updated_count,
        "total": saved_count + updated_count,
    }


# ---------------------------------------------------------------------------
# POST endpoint: sync messages from LangGraph (backfill missing data)
# ---------------------------------------------------------------------------

@router.post(
    "/{thread_id}/messages/sync",
    summary="Sync messages from LangGraph API",
    description="Fetches the latest thread state from LangGraph and backfills any missing messages to the local SQLite store. Called by the frontend when it detects an incomplete conversation after a page refresh.",
)
async def sync_thread_messages(thread_id: str) -> dict[str, Any]:
    """Sync messages from LangGraph API to local SQLite store."""
    from langgraph_sdk import get_client

    try:
        client = get_client(url=settings.langgraph_api_url)
        state = await client.threads.get_state(thread_id)
    except Exception as e:
        logger.warning("Failed to sync thread %s from LangGraph: %s", thread_id, e)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch thread state from LangGraph: {e}",
        ) from e

    state_values = state.get("values", {}) if isinstance(state, dict) else {}
    raw_messages = state_values.get("messages", []) if isinstance(state_values, dict) else []

    if not raw_messages:
        return {"synced": 0, "total": 0}

    serialized = [_serialize_message(m) for m in raw_messages]
    await _backfill_local_store(thread_id, serialized)

    return {"synced": len(serialized), "total": len(serialized)}


# ---------------------------------------------------------------------------
# GET endpoint: paginated messages from local store
# ---------------------------------------------------------------------------

@router.get(
    "/{thread_id}/messages",
    summary="Get paginated thread messages",
    description="Cursor-based pagination over thread conversation history. Reads from local SQLite store first, falls back to LangGraph API.",
)
async def get_thread_messages(
    thread_id: str,
    limit: int = Query(default=20, ge=1, le=100, description="Maximum messages per page"),
    cursor: str | None = Query(default=None, description="Message ID cursor for pagination"),
) -> dict[str, Any]:
    """Get paginated messages for a thread.

    - **No cursor**: Returns the last `limit` messages (most recent).
    - **With cursor**: Returns messages before the cursor (older messages).
    - **next_cursor**: ID of the first message in the returned slice, used
      to fetch the next page of older messages.

    Reads from the local SQLite store first. If no messages are found there,
    falls back to the LangGraph API (for backward compatibility with threads
    that were created before the local store was implemented).
    """
    # --- Try local SQLite store first ---
    async with async_session_factory() as session:
        # Count total messages for this thread
        count_stmt = select(func.count()).select_from(ThreadMessage).where(
            ThreadMessage.thread_id == thread_id
        )
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

    if total > 0:
        return await _get_messages_from_local(thread_id, limit, cursor, total)

    # --- Fallback: try LangGraph API (for existing threads without local data) ---
    return await _get_messages_from_langgraph(thread_id, limit, cursor)


# ---------------------------------------------------------------------------
# Local SQLite store implementation
# ---------------------------------------------------------------------------

async def _get_messages_from_local(
    thread_id: str,
    limit: int,
    cursor: str | None,
    total: int,
) -> dict[str, Any]:
    """Load messages from the local SQLite store with cursor-based pagination."""
    async with async_session_factory() as session:
        if cursor is None:
            # Return the last `limit` messages (most recent)
            # Get the total and calculate offset
            offset = max(0, total - limit)

            stmt = (
                select(ThreadMessage)
                .where(ThreadMessage.thread_id == thread_id)
                .order_by(ThreadMessage.seq_index.asc())
                .offset(offset)
                .limit(limit)
            )
        else:
            # Find the cursor message's seq_index
            cursor_stmt = select(ThreadMessage.seq_index).where(
                ThreadMessage.thread_id == thread_id,
                ThreadMessage.message_id == cursor,
            )
            cursor_result = await session.execute(cursor_stmt)
            cursor_seq = cursor_result.scalar_one_or_none()

            if cursor_seq is None:
                return {
                    "messages": [],
                    "total": total,
                    "has_more": False,
                    "next_cursor": None,
                }

            # Get messages before the cursor
            end_offset = max(0, cursor_seq - 1)
            start_offset = max(0, end_offset - limit)

            stmt = (
                select(ThreadMessage)
                .where(
                    ThreadMessage.thread_id == thread_id,
                    ThreadMessage.seq_index <= cursor_seq - 1,
                )
                .order_by(ThreadMessage.seq_index.asc())
                .offset(start_offset)
                .limit(limit)
            )

        result = await session.execute(stmt)
        rows = result.scalars().all()

        messages = [_row_to_dict(row) for row in rows]

        # Determine has_more and next_cursor
        if cursor is None:
            has_more = total > limit
        else:
            # Check if there are messages before our result set
            if rows:
                first_seq = rows[0].seq_index
                has_more = first_seq > 0
            else:
                has_more = False

        next_cursor = None
        if has_more and messages:
            next_cursor = messages[0]["id"]

        return {
            "messages": messages,
            "total": total,
            "has_more": has_more,
            "next_cursor": next_cursor,
        }


# ---------------------------------------------------------------------------
# LangGraph API fallback (for existing threads without local data)
# ---------------------------------------------------------------------------

async def _get_messages_from_langgraph(
    thread_id: str,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    """Fallback: load messages from LangGraph API via get_state().

    This is only used for threads that were created before the local
    message store was implemented. For large threads, this may fail
    with a 500 error from the LangGraph API.
    """
    from langgraph_sdk import get_client

    try:
        client = get_client(url=settings.langgraph_api_url)
        state = await client.threads.get_state(thread_id)
    except Exception as e:
        logger.error("Failed to fetch thread state for %s: %s", thread_id, e)
        raise HTTPException(
            status_code=404,
            detail=f"Thread not found or LangGraph API unavailable: {thread_id}",
        ) from e

    state_values = state.get("values", {})
    raw_messages = state_values.get("messages", []) if isinstance(state_values, dict) else []
    if not raw_messages:
        return {
            "messages": [],
            "total": 0,
            "has_more": False,
            "next_cursor": None,
        }

    serialized = [_serialize_message(m) for m in raw_messages]
    total = len(serialized)

    # Validate cursor
    if cursor is not None:
        found = any(m.get("id") == cursor for m in serialized)
        if not found:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cursor: message ID '{cursor}' not found in thread",
            )

    sliced, has_more, next_cursor = _slice_messages(serialized, limit, cursor)

    # Also save these messages to local store for future fast access
    await _backfill_local_store(thread_id, serialized)

    return {
        "messages": sliced,
        "total": total,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


# ---------------------------------------------------------------------------
# Helper: slice messages (for LangGraph fallback)
# ---------------------------------------------------------------------------

def _collect_tool_call_ids(msg: dict[str, Any]) -> set[str]:
    """Extract all tool_call IDs from a message."""
    ids: set[str] = set()
    for tc in (msg.get("tool_calls") or []):
        if tc and tc.get("id"):
            ids.add(tc["id"])
    for tc in (msg.get("additional_kwargs", {}).get("tool_calls") or []):
        if tc and tc.get("id"):
            ids.add(tc["id"])
    return ids


def _adjust_start_for_groups(
    messages: list[dict[str, Any]],
    start: int,
) -> int:
    """Adjust start index backwards to include orphaned tool message groups."""
    if start <= 0:
        return start

    msg = messages[start]
    msg_type = msg.get("type", "")

    if msg_type != "tool":
        return start

    needed_ids: set[str] = set()
    idx = start

    while idx >= 0:
        current = messages[idx]
        current_type = current.get("type", "")

        if current_type == "tool":
            tool_call_id = (
                current.get("additional_kwargs", {}).get("tool_call_id")
                or current.get("tool_call_id")
            )
            if tool_call_id:
                needed_ids.add(tool_call_id)

        if current_type == "ai" and needed_ids:
            ai_tool_ids = _collect_tool_call_ids(current)
            if ai_tool_ids & needed_ids:
                needed_ids -= ai_tool_ids
                if not needed_ids:
                    return idx
        idx -= 1

    return start


def _slice_messages(
    messages: list[dict[str, Any]],
    limit: int,
    cursor: str | None,
) -> tuple[list[dict[str, Any]], bool, str | None]:
    """Slice messages with cursor-based pagination and group integrity."""
    total = len(messages)
    if total == 0:
        return [], False, None

    if cursor is None:
        start = max(0, total - limit)
        if start > 0:
            adjusted = _adjust_start_for_groups(messages, start)
            if adjusted < start:
                start = adjusted
        raw_slice = messages[start:total]
        has_more = start > 0
        next_cursor = raw_slice[0]["id"] if has_more and raw_slice else None
        return raw_slice, has_more, next_cursor

    cursor_idx = None
    for i, msg in enumerate(messages):
        if msg.get("id") == cursor:
            cursor_idx = i
            break

    if cursor_idx is None:
        return [], False, None

    end = cursor_idx
    start = max(0, end - limit)
    if start > 0:
        adjusted = _adjust_start_for_groups(messages, start)
        if adjusted < start:
            start = adjusted
    raw_slice = messages[start:end]
    has_more = start > 0
    next_cursor = raw_slice[0]["id"] if has_more and raw_slice else None
    return raw_slice, has_more, next_cursor


# ---------------------------------------------------------------------------
# Helper: backfill local store from LangGraph data
# ---------------------------------------------------------------------------

async def _backfill_local_store(
    thread_id: str,
    messages: list[dict[str, Any]],
) -> None:
    """Save messages loaded from LangGraph API to the local SQLite store.

    This is called after a successful get_state() fallback to ensure
    future requests for this thread can use the fast local store.
    """
    if not messages:
        return

    try:
        async with async_session_factory() as session:
            for i, msg in enumerate(messages):
                msg_id = msg.get("id")
                if not msg_id:
                    continue

                # Check if already exists
                stmt = select(ThreadMessage).where(ThreadMessage.message_id == msg_id)
                result = await session.execute(stmt)
                if result.scalar_one_or_none():
                    continue

                content_str = _serialize_content(msg.get("content", ""))
                additional_kwargs = msg.get("additional_kwargs")
                tool_calls = msg.get("tool_calls")

                new_msg = ThreadMessage(
                    thread_id=thread_id,
                    message_id=msg_id,
                    msg_type=msg.get("type", "unknown"),
                    content=content_str,
                    additional_kwargs=(
                        json.dumps(additional_kwargs, ensure_ascii=False, default=str)
                        if additional_kwargs
                        else None
                    ),
                    tool_calls=(
                        json.dumps(tool_calls, ensure_ascii=False, default=str)
                        if tool_calls
                        else None
                    ),
                    name=msg.get("name"),
                    seq_index=i + 1,
                )
                session.add(new_msg)

            await session.commit()
    except Exception as e:
        logger.warning("Failed to backfill local store for thread %s: %s", thread_id, e)
        # Non-critical: don't fail the request
