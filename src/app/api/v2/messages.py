"""Paginated messages endpoint for thread conversation history.

Provides cursor-based pagination over LangGraph thread messages,
ensuring conversation groups (AI message + tool results) are never
split across pages.

This endpoint reads thread state server-side via langgraph_sdk and
returns sliced messages, avoiding the need to send the entire 25MB+
thread state to the browser.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/threads")


def _serialize_message(msg: Any) -> dict[str, Any]:
    """Serialize a LangGraph message (dict or object) to a JSON-safe dict.

    Handles both dict-style messages (from ThreadState.values) and
    object-style LangChain message objects.
    """
    if isinstance(msg, dict):
        return {
            "id": msg.get("id"),
            "type": msg.get("type"),
            "content": msg.get("content"),
            "additional_kwargs": msg.get("additional_kwargs", {}),
            "tool_calls": msg.get("tool_calls"),
            "name": msg.get("name"),
        }

    # Object-style LangChain message
    return {
        "id": getattr(msg, "id", None),
        "type": getattr(msg, "type", None),
        "content": getattr(msg, "content", None),
        "additional_kwargs": getattr(msg, "additional_kwargs", {}),
        "tool_calls": getattr(msg, "tool_calls", None),
        "name": getattr(msg, "name", None),
    }


def _collect_tool_call_ids(msg: dict[str, Any]) -> set[str]:
    """Extract all tool_call IDs from a message (both tool_calls and additional_kwargs)."""
    ids: set[str] = set()

    # From tool_calls list
    for tc in (msg.get("tool_calls") or []):
        if tc and tc.get("id"):
            ids.add(tc["id"])

    # From additional_kwargs.tool_calls (older format)
    for tc in (msg.get("additional_kwargs", {}).get("tool_calls") or []):
        if tc and tc.get("id"):
            ids.add(tc["id"])

    return ids


def _find_group_boundary(
    messages: list[dict[str, Any]],
    end_index: int,
) -> int:
    """Scan backwards from end_index to ensure conversation group integrity.

    If the message at end_index is a tool message, scan backwards to include
    the AI message that spawned it (and any sibling tool messages). Returns
    the adjusted start index so the group is never split.

    Args:
        messages: Full list of serialized messages in chronological order.
        end_index: The intended cut point (inclusive).

    Returns:
        Adjusted start index that includes the complete conversation group.
    """
    # Collect tool_call_ids that need their parent AI message included
    needed_tool_call_ids: set[str] = set()
    scan = end_index

    while scan >= 0:
        msg = messages[scan]
        msg_type = msg.get("type", "")

        if msg_type == "tool":
            # This tool message belongs to an AI message via tool_call_id
            tool_call_id = msg.get("additional_kwargs", {}).get("tool_call_id") or msg.get("tool_call_id")
            if tool_call_id:
                needed_tool_call_ids.add(tool_call_id)
            scan -= 1
            continue

        if msg_type == "ai" and needed_tool_call_ids:
            # Check if this AI message spawned any of the needed tool calls
            ai_tool_ids = _collect_tool_call_ids(msg)
            if ai_tool_ids & needed_tool_call_ids:
                # Found the parent AI message; clear needed IDs (group complete)
                needed_tool_call_ids -= ai_tool_ids
                if not needed_tool_call_ids:
                    # All groups resolved
                    return scan
            scan -= 1
            continue

        # Non-tool, non-AI message — no group concern
        break

    return max(0, scan)


def _slice_messages(
    messages: list[dict[str, Any]],
    limit: int,
    cursor: str | None,
) -> tuple[list[dict[str, Any]], bool, str | None]:
    """Slice messages with cursor-based pagination and group integrity.

    Args:
        messages: Full list of serialized messages in chronological order.
        limit: Maximum number of messages to return.
        cursor: Message ID to start before (for fetching older messages).
            None means return the most recent messages.

    Returns:
        Tuple of (sliced_messages, has_more, next_cursor).
    """
    total = len(messages)
    if total == 0:
        return [], False, None

    if cursor is None:
        # Return the last `limit` messages (most recent)
        start = max(0, total - limit)
        raw_slice = messages[start:total]
        has_more = start > 0

        # Ensure conversation group integrity at the start boundary
        if start > 0:
            adjusted_start = _find_group_boundary(messages, start + len(raw_slice) - 1)
            # We need to check if extending backwards is needed
            # Actually, _find_group_boundary scans backwards from end_index.
            # For the first page, the cut is at `start`. We need to ensure
            # the message at `start` doesn't orphan tool messages.
            # Check if start has a tool message that needs its AI parent
            if start > 0:
                adjusted = _adjust_start_for_groups(messages, start)
                if adjusted < start:
                    raw_slice = messages[adjusted:total]
                    has_more = adjusted > 0

        next_cursor = raw_slice[0]["id"] if has_more and raw_slice else None
        return raw_slice, has_more, next_cursor

    # Cursor-based: find the cursor message, return messages before it
    cursor_idx = None
    for i, msg in enumerate(messages):
        if msg.get("id") == cursor:
            cursor_idx = i
            break

    if cursor_idx is None:
        return [], False, None  # Invalid cursor, return empty

    # Messages before cursor_idx
    end = cursor_idx
    start = max(0, end - limit)
    raw_slice = messages[start:end]
    has_more = start > 0

    # Ensure conversation group integrity at the start boundary
    if start > 0:
        adjusted = _adjust_start_for_groups(messages, start)
        if adjusted < start:
            raw_slice = messages[adjusted:end]
            has_more = adjusted > 0

    next_cursor = raw_slice[0]["id"] if has_more and raw_slice else None
    return raw_slice, has_more, next_cursor


def _adjust_start_for_groups(
    messages: list[dict[str, Any]],
    start: int,
) -> int:
    """Adjust start index backwards to include any orphaned tool message groups.

    If the message at `start` is a tool message, we need to scan backwards
    to find its parent AI message so the group is not split.
    """
    if start <= 0:
        return start

    msg = messages[start]
    msg_type = msg.get("type", "")

    if msg_type != "tool":
        return start

    # This is a tool message — find the AI parent
    needed_ids: set[str] = set()
    idx = start

    while idx >= 0:
        current = messages[idx]
        current_type = current.get("type", "")

        if current_type == "tool":
            tool_call_id = current.get("additional_kwargs", {}).get("tool_call_id") or current.get("tool_call_id")
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


@router.get(
    "/{thread_id}/messages",
    summary="Get paginated thread messages",
    description="Cursor-based pagination over thread conversation history with conversation group integrity",
)
async def get_thread_messages(
    thread_id: str,
    limit: int = Query(default=20, ge=1, le=100, description="Maximum messages per page"),
    cursor: str | None = Query(default=None, description="Message ID cursor for pagination"),
) -> dict[str, Any]:
    """Get paginated messages for a thread.

    - **No cursor**: Returns the last `limit` messages (most recent).
    - **With cursor**: Returns messages before the cursor (older messages).
    - Conversation groups (AI message + tool results) are never split.
    - **next_cursor**: ID of the first message in the returned slice, used
      to fetch the next page of older messages.
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

    raw_messages = state.values.get("messages", [])
    if not raw_messages:
        return {
            "messages": [],
            "total": 0,
            "has_more": False,
            "next_cursor": None,
        }

    # Serialize all messages
    serialized = [_serialize_message(m) for m in raw_messages]

    total = len(serialized)

    # Validate cursor if provided
    if cursor is not None:
        found = any(m.get("id") == cursor for m in serialized)
        if not found:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cursor: message ID '{cursor}' not found in thread",
            )

    sliced, has_more, next_cursor = _slice_messages(serialized, limit, cursor)

    return {
        "messages": sliced,
        "total": total,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }
