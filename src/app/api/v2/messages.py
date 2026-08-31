"""Paginated messages endpoint for thread conversation history.

Uses a local SQLite message store (thread_messages table) for fast
paginated retrieval of chat history, avoiding the need to load the
full thread state from the LangGraph API (which fails for large threads).

Architecture:
- Messages are saved to SQLite by the frontend after streaming completes
  (POST /api/v2/threads/{thread_id}/messages/save). The save endpoint also
  upserts thread metadata (thread_infos) so any thread with saved messages
  is guaranteed to appear in the conversation list.
- Thread metadata is normally registered by the frontend at thread creation
  (POST /api/v2/threads); the upsert on save is a server-side safety net.
- History is loaded from SQLite (this endpoint), which works for any thread size.
- Fallback: if no messages are found in SQLite for a thread, tries get_state()
  from LangGraph API (backward compatibility with existing small threads).
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from datetime import timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
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


def _iso_utc(dt: Any) -> str | None:
    """SQLite CURRENT_TIMESTAMP 存的是 UTC naive 时间；补上时区标记，
    前端 new Date() 才能正确转成本地时间（否则差 8 小时）。"""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).isoformat()


_CURSOR_VERSION = 1


def _encode_cursor(seq_index: int, message_id: str) -> str:
    """Encode the local keyset position without changing the response field."""
    payload = json.dumps(
        {"v": _CURSOR_VERSION, "seq": seq_index, "id": message_id},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[int, str] | None:
    """Decode a versioned keyset cursor; legacy bare IDs are rejected uniformly."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded).decode())
        if value.get("v") != _CURSOR_VERSION:
            return None
        seq_index = value["seq"]
        message_id = value["id"]
        if not isinstance(seq_index, int) or not isinstance(message_id, str) or not message_id:
            return None
        return seq_index, message_id
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, binascii.Error, UnicodeError):
        return None


def _invalid_cursor(cursor: str) -> HTTPException:
    return HTTPException(status_code=400, detail=f"Invalid cursor: '{cursor}'")


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
        # 只返回有消息的会话：零消息的空壳线程（历史预创建遗留、上传文件
        # 后未发送）不出现在列表——会话可见性由内容决定（dsh 原则）。
        # 上传触发的懒创建线程在首条消息保存后自然出现。
        msg_count = (
            select(func.count())
            .select_from(ThreadMessage)
            .where(ThreadMessage.thread_id == ThreadInfo.thread_id)
            .correlate(ThreadInfo)
            .scalar_subquery()
        )
        visible = and_(ThreadInfo.deleted.is_(False), msg_count > 0)

        total_stmt = select(func.count()).select_from(ThreadInfo).where(visible)
        total = (await session.execute(total_stmt)).scalar() or 0

        stmt = (
            select(ThreadInfo)
            .where(visible)
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
                    "created_at": _iso_utc(t.created_at),
                    "updated_at": _iso_utc(t.updated_at),
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
        row = existing.scalar_one_or_none()
        # 已存在（含已删除墓碑）一律不再创建——防止已删除线程被重新注册复活
        if row:
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
        if not info or info.deleted:
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
    description=(
        "Remove thread metadata and all associated messages from SQLite, "
        "and delete the underlying LangGraph thread so the conversation "
        "cannot be resurrected (state, checkpoints, active runs)."
    ),
)
async def delete_thread(thread_id: str) -> dict[str, Any]:
    # 本地墓碑是权威状态：先在一个事务中删除本地消息并提交墓碑，
    # 再 best-effort 删除 LangGraph。这样 LangGraph 删除失败也不会复活会话。
    async with async_session_factory() as session:
        msgs = await session.execute(
            select(ThreadMessage).where(ThreadMessage.thread_id == thread_id)
        )
        for msg in msgs.scalars().all():
            await session.delete(msg)

        info_stmt = select(ThreadInfo).where(ThreadInfo.thread_id == thread_id)
        info_result = await session.execute(info_stmt)
        info = info_result.scalar_one_or_none()
        if info:
            info.deleted = True
        else:
            session.add(ThreadInfo(thread_id=thread_id, title="无标题对话", deleted=True))
        await session.commit()

    langgraph_deleted = False
    try:
        from langgraph_sdk import get_client

        client = get_client(url=settings.langgraph_api_url)
        await client.threads.delete(thread_id)
        langgraph_deleted = True
    except Exception as e:
        logger.warning("Failed to delete LangGraph thread %s: %s", thread_id, e)

    return {"success": True, "thread_id": thread_id, "langgraph_deleted": langgraph_deleted}


@router.delete(
    "",
    summary="Delete ALL persisted threads",
    description=(
        "Delete every non-deleted thread: removes all local messages, "
        "tombstones the thread_infos rows, and deletes the underlying "
        "LangGraph threads (best effort)."
    ),
)
async def delete_all_threads() -> dict[str, Any]:
    from langgraph_sdk import get_client

    async with async_session_factory() as session:
        infos = (
            (
                await session.execute(
                    select(ThreadInfo).where(ThreadInfo.deleted.is_(False))
                )
            )
            .scalars()
            .all()
        )
        thread_ids = [t.thread_id for t in infos]
        if thread_ids:
            await session.execute(
                delete(ThreadMessage).where(ThreadMessage.thread_id.in_(thread_ids))
            )
        for info in infos:
            info.deleted = True
        await session.commit()

    langgraph_deleted = 0
    try:
        client = get_client(url=settings.langgraph_api_url)
        for tid in thread_ids:
            try:
                await client.threads.delete(tid)
                langgraph_deleted += 1
            except Exception as e:
                logger.warning("Failed to delete LangGraph thread %s: %s", tid, e)
    except Exception as e:
        logger.warning("Failed to create LangGraph client for bulk delete: %s", e)

    return {
        "success": True,
        "deleted": len(thread_ids),
        "langgraph_deleted": langgraph_deleted,
    }


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
    # tool 消息的关联 id：不存它，历史加载后工具结果无法关联回工具调用，
    # 前端会永远显示「执行中」。落库时并入 additional_kwargs JSON（免加列）。
    tool_call_id: str | None = None


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

    # tool_call_id 落库时并入了 additional_kwargs；取出置顶层，
    # 前端按顶层 tool_call_id 关联工具调用与结果
    tool_call_id = None
    if isinstance(additional_kwargs, dict):
        tool_call_id = additional_kwargs.pop("tool_call_id", None)

    return {
        "id": row.message_id,
        "type": row.msg_type,
        "content": content,
        "additional_kwargs": additional_kwargs or {},
        "tool_calls": tool_calls,
        "name": row.name,
        "tool_call_id": tool_call_id,
    }


# ---------------------------------------------------------------------------
# Helper: serialize a LangGraph message (for fallback)
# ---------------------------------------------------------------------------

def _serialize_message(msg: Any) -> dict[str, Any]:
    """Serialize a LangGraph message (dict or object) to a JSON-safe dict."""
    if isinstance(msg, dict):
        additional_kwargs = dict(msg.get("additional_kwargs") or {})
        tool_call_id = msg.get("tool_call_id")
    else:
        additional_kwargs = dict(getattr(msg, "additional_kwargs", {}) or {})
        tool_call_id = getattr(msg, "tool_call_id", None)
    if tool_call_id:
        additional_kwargs["tool_call_id"] = tool_call_id

    if isinstance(msg, dict):
        return {
            "id": msg.get("id"),
            "type": msg.get("type"),
            "content": msg.get("content"),
            "additional_kwargs": additional_kwargs,
            "tool_calls": msg.get("tool_calls"),
            "name": msg.get("name"),
        }

    return {
        "id": getattr(msg, "id", None),
        "type": getattr(msg, "type", None),
        "content": getattr(msg, "content", None),
        "additional_kwargs": additional_kwargs,
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
# Helper: derive thread title from the first human message
# ---------------------------------------------------------------------------

# Titles that may be replaced by one derived from message content
_PLACEHOLDER_TITLES = {"无标题对话", "新对话", ""}


def _extract_display_text(content: Any) -> str | None:
    """Extract plain text from message content (string or content blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return " ".join(p for p in parts if p) or None
    return None


def _derive_thread_title(messages: list[MessageInput]) -> str | None:
    """Derive a display title from the first human message in a batch.

    会话标题应显示用户的输入而非中间件注入的上下文。流式保存的人类消息
    常带 [代码分析上下文 ...] / 仓库路径: 前缀（agent 中间件注入），与前端
    ChatMessage.stripInternalContent 用同一套剥离规则。
    """
    for msg in messages:
        if msg.type != "human":
            continue
        text = _extract_display_text(msg.content)
        if text and text.strip():
            text = re.sub(r"\[代码分析上下文[^\]]*\]\s*", "", text)
            text = re.sub(r"^\s*仓库路径:.*$", "", text, flags=re.MULTILINE)
            text = text.strip()
            if text:
                return text[:50] + ("..." if len(text) > 50 else "")
    return None


async def _upsert_thread_info(session: Any, thread_id: str, messages: list[MessageInput]) -> bool:
    """Ensure a live ThreadInfo row exists; return False for a tombstone.

    Defense in depth: the conversation list (GET /threads) only reads
    thread_infos, so any thread with saved messages must be registered here
    even if the frontend registration call was missed or failed. Also bumps
    updated_at so the list ordering reflects recent activity.

    已删除的线程（墓碑）不复活：删除后残留的后台流 finalize 再保存时，
    这里必须直接跳过，否则对话会「死而复生」。
    """
    result = await session.execute(
        select(ThreadInfo).where(ThreadInfo.thread_id == thread_id)
    )
    info = result.scalar_one_or_none()
    if info is not None and info.deleted:
        return False
    title = _derive_thread_title(messages)

    if info is None:
        # 并发注册竞态（前端注册与首次消息保存同时建行，或两个标签页同时
        # 保存）：先查后插会撞 UNIQUE 约束，500 导致整个保存事务回滚、
        # 消息一起丢、线程因零消息被列表可见性过滤隐藏。INSERT OR IGNORE
        # 让后到者静默跳过，再回读走统一更新分支。
        stmt = (
            sqlite_insert(ThreadInfo)
            .values(thread_id=thread_id, title=title or "无标题对话")
            .on_conflict_do_nothing(index_elements=["thread_id"])
        )
        await session.execute(stmt)
        info = (
            await session.execute(
                select(ThreadInfo).where(ThreadInfo.thread_id == thread_id)
            )
        ).scalar_one_or_none()
        if info is None or info.deleted:
            return False

    # 存量自愈：旧版本把注入前缀当标题存了（"[代码分析上下文 ..."），
    # 后续保存推导出干净标题时允许替换
    healable = info.title in _PLACEHOLDER_TITLES or info.title.startswith(
        "[代码分析上下文"
    )
    if title is not None and healable:
        info.title = title
    info.updated_at = func.now()
    return True


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
        if not await _upsert_thread_info(session, thread_id, request.messages):
            await session.rollback()
            return {"saved": 0, "updated": 0, "total": 0, "ignored": True}

        # De-duplicate a batch by message id; the last snapshot is authoritative.
        unique_messages: dict[str, MessageInput] = {}
        for msg in request.messages:
            if msg.id and msg.type:
                unique_messages[msg.id] = msg

        for msg in unique_messages.values():
            content_str = _serialize_content(msg.content)
            additional_kwargs = dict(msg.additional_kwargs) if msg.additional_kwargs else {}
            if msg.tool_call_id:
                additional_kwargs["tool_call_id"] = msg.tool_call_id
            additional_kwargs_str = (
                json.dumps(additional_kwargs, ensure_ascii=False, default=str)
                if additional_kwargs
                else None
            )
            tool_calls_str = (
                json.dumps(msg.tool_calls, ensure_ascii=False, default=str)
                if msg.tool_calls
                else None
            )

            # Allocate an ordering slot for a new message.  The sequence index
            # is intentionally not unique; concurrent requests may share a
            # slot, while (thread_id, message_id) remains the idempotency key.
            max_idx_stmt = select(func.max(ThreadMessage.seq_index)).where(
                ThreadMessage.thread_id == thread_id
            )
            max_idx_result = await session.execute(max_idx_stmt)
            max_idx = max_idx_result.scalar() or 0
            values = {
                "thread_id": thread_id,
                "message_id": msg.id,
                "msg_type": msg.type,
                "content": content_str,
                "additional_kwargs": additional_kwargs_str,
                "tool_calls": tool_calls_str,
                "name": msg.name,
                "seq_index": max_idx + 1,
            }
            # Do not perform a separate existence check: reconnects and
            # incremental/final saves can arrive concurrently.  SQLite's
            # conflict target makes the operation idempotent in one statement.
            stmt = sqlite_insert(ThreadMessage).values(**values).on_conflict_do_update(
                index_elements=["thread_id", "message_id"],
                set_={
                    "msg_type": values["msg_type"],
                    "content": values["content"],
                    "additional_kwargs": values["additional_kwargs"],
                    "tool_calls": values["tool_calls"],
                    "name": values["name"],
                },
            )
            result = await session.execute(stmt)
            if result.rowcount == 1:
                # SQLite does not expose insert-vs-update portably here; the
                # endpoint's total remains accurate and counters are advisory.
                saved_count += 1
            else:
                updated_count += 1


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
    description="Fetches the latest thread state from LangGraph and backfills any missing messages to the local SQLite store. With prune=true, also removes local messages that are NOT in the authoritative state (e.g. sub-agent internals that leaked into the store via a subgraphs-blind reconnect).",
)
async def sync_thread_messages(
    thread_id: str,
    prune: bool = Query(default=False),
) -> dict[str, Any]:
    """Sync messages from LangGraph API to local SQLite store."""
    from langgraph_sdk import get_client

    if await _thread_is_deleted(thread_id):
        return {"synced": 0, "total": 0, "pruned": 0, "ignored": True}

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
        if prune:
            async with async_session_factory() as session:
                result = await session.execute(
                    delete(ThreadMessage).where(ThreadMessage.thread_id == thread_id)
                )
                pruned = result.rowcount or 0
                await session.commit()
            return {"synced": 0, "total": 0, "pruned": pruned}
        return {"synced": 0, "total": 0, "pruned": 0}

    serialized = [_serialize_message(m) for m in raw_messages]
    counts = await _backfill_local_store(thread_id, serialized, prune=prune)

    return {
        "synced": counts["inserted"] + counts["updated"],
        "total": len(serialized),
        "pruned": counts["deleted"],
    }


# ---------------------------------------------------------------------------
# GET endpoint: paginated messages from local store
# ---------------------------------------------------------------------------

async def _thread_is_deleted(thread_id: str) -> bool:
    """Return whether the local tombstone is authoritative for this thread."""
    async with async_session_factory() as session:
        info = (
            await session.execute(
                select(ThreadInfo.deleted).where(ThreadInfo.thread_id == thread_id)
            )
        ).scalar_one_or_none()
    return bool(info)


def _empty_messages_response() -> dict[str, Any]:
    return {
        "messages": [],
        "total": 0,
        "has_more": False,
        "next_cursor": None,
    }


@router.get(
    "/{thread_id}/messages",
    summary="Get paginated thread messages",
    description="Cursor-based pagination over thread conversation history. Reads from local SQLite store first, falls back to LangGraph API.",
)
async def get_thread_messages(
    thread_id: str,
    limit: int = Query(default=20, ge=1, le=100, description="Maximum messages per page"),
    cursor: str | None = Query(default=None, description="Composite (seq_index,message_id) cursor for pagination"),
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
    # Local tombstones are authoritative and must never fall back to LangGraph.
    if await _thread_is_deleted(thread_id):
        return _empty_messages_response()

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
    """Load messages using a stable ``(seq_index, message_id)`` keyset."""
    async with async_session_factory() as session:
        if cursor is None:
            # Descending fetch avoids OFFSET and gives the newest page; restore
            # ascending order for compatibility with the existing response.
            stmt = (
                select(ThreadMessage)
                .where(ThreadMessage.thread_id == thread_id)
                .order_by(ThreadMessage.seq_index.desc(), ThreadMessage.message_id.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = list(reversed(result.scalars().all()))
            has_more = total > len(rows)
        else:
            decoded = _decode_cursor(cursor)
            if decoded is None:
                raise _invalid_cursor(cursor)
            cursor_seq, cursor_id = decoded

            # The cursor identifies the first row in the previous (newer) page.
            # Reject missing/stale cursors rather than silently returning data.
            cursor_stmt = select(ThreadMessage).where(
                ThreadMessage.thread_id == thread_id,
                ThreadMessage.seq_index == cursor_seq,
                ThreadMessage.message_id == cursor_id,
            )
            cursor_row = (await session.execute(cursor_stmt)).scalar_one_or_none()
            if cursor_row is None:
                raise _invalid_cursor(cursor)

            stmt = (
                select(ThreadMessage)
                .where(
                    ThreadMessage.thread_id == thread_id,
                    (ThreadMessage.seq_index < cursor_seq)
                    | (
                        (ThreadMessage.seq_index == cursor_seq)
                        & (ThreadMessage.message_id < cursor_id)
                    ),
                )
                .order_by(ThreadMessage.seq_index.desc(), ThreadMessage.message_id.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = list(reversed(result.scalars().all()))
            has_more = bool(rows) and (
                rows[0].seq_index > 0
                or rows[0].message_id > ""
            )
            if rows:
                before_stmt = select(func.count()).select_from(ThreadMessage).where(
                    ThreadMessage.thread_id == thread_id,
                    (ThreadMessage.seq_index < rows[0].seq_index)
                    | (
                        (ThreadMessage.seq_index == rows[0].seq_index)
                        & (ThreadMessage.message_id < rows[0].message_id)
                    ),
                )
                has_more = (await session.execute(before_stmt)).scalar() > 0

        messages = [_row_to_dict(row) for row in rows]
        next_cursor = _encode_cursor(rows[0].seq_index, rows[0].message_id) if has_more and rows else None
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
        if cursor is not None:
            raise _invalid_cursor(cursor)
        return _empty_messages_response()

    serialized = [_serialize_message(m) for m in raw_messages]
    # Backfill first so subsequent requests are local-authority reads. The
    # response keeps the legacy shape but emits a composite keyset cursor.
    counts = await _backfill_local_store(thread_id, serialized)
    if counts.get("error"):
        logger.warning("Could not backfill thread %s before serving fallback", thread_id)

    # Use the authoritative snapshot's order for this compatibility request.
    unique_serialized = _dedupe_messages(serialized)
    total = len(unique_serialized)
    cursor_position = None
    if cursor is not None:
        cursor_position = _decode_cursor(cursor)
        if cursor_position is None:
            raise _invalid_cursor(cursor)
        if not any(
            _message_key(msg, i) == cursor_position
            for i, msg in enumerate(unique_serialized, start=1)
        ):
            raise _invalid_cursor(cursor)

    sliced, has_more, next_cursor = _slice_messages(
        unique_serialized, limit, cursor_position
    )

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


def _dedupe_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the last snapshot for each ID while preserving its final order."""
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for msg in reversed(messages):
        msg_id = msg.get("id")
        if not msg_id or msg_id in seen:
            continue
        seen.add(msg_id)
        result.append(msg)
    result.reverse()
    return result


def _message_key(msg: dict[str, Any], index: int) -> tuple[int, str]:
    return index, str(msg.get("id") or "")


def _slice_messages(
    messages: list[dict[str, Any]],
    limit: int,
    cursor: tuple[int, str] | None,
) -> tuple[list[dict[str, Any]], bool, str | None]:
    """Slice fallback messages with the same composite cursor as local reads."""
    total = len(messages)
    if total == 0:
        return [], False, None

    if cursor is None:
        end = total
    else:
        end = next(
            (
                i
                for i, msg in enumerate(messages)
                if _message_key(msg, i + 1) == cursor
            ),
            -1,
        )
        if end < 0:
            return [], False, None

    start = max(0, end - limit)
    if start > 0:
        adjusted = _adjust_start_for_groups(messages, start)
        if adjusted < start:
            start = adjusted
    raw_slice = messages[start:end]
    has_more = start > 0
    next_cursor = None
    if has_more and raw_slice:
        next_cursor = _encode_cursor(start + 1, str(raw_slice[0].get("id") or ""))
    return raw_slice, has_more, next_cursor


# ---------------------------------------------------------------------------
# Helper: backfill local store from LangGraph data
# ---------------------------------------------------------------------------

async def _backfill_local_store(
    thread_id: str,
    messages: list[dict[str, Any]],
    *,
    prune: bool = False,
) -> dict[str, int | bool]:
    """Reconcile local messages with LangGraph unless a tombstone forbids it."""
    if await _thread_is_deleted(thread_id):
        return {"inserted": 0, "updated": 0, "deleted": 0, "error": False}

    try:
        async with async_session_factory() as session:
            inserted = 0
            updated = 0
            await session.execute(
                ThreadMessage.__table__.update()
                .where(ThreadMessage.thread_id == thread_id)
                .values(seq_index=ThreadMessage.seq_index + 1_000_000)
            )
            await session.flush()

            authority = _dedupe_messages(messages)
            authority_ids = {str(msg["id"]) for msg in authority}
            for index, msg in enumerate(authority, start=1):
                msg_id = str(msg["id"])
                existing = (
                    await session.execute(
                        select(ThreadMessage).where(
                            ThreadMessage.thread_id == thread_id,
                            ThreadMessage.message_id == msg_id,
                        )
                    )
                ).scalar_one_or_none()
                additional_kwargs = dict(msg.get("additional_kwargs") or {})
                if msg.get("tool_call_id"):
                    additional_kwargs["tool_call_id"] = msg["tool_call_id"]
                values = {
                    "msg_type": msg.get("type", "unknown"),
                    "content": _serialize_content(msg.get("content", "")),
                    "additional_kwargs": (
                        json.dumps(additional_kwargs, ensure_ascii=False, default=str)
                        if additional_kwargs else None
                    ),
                    "tool_calls": (
                        json.dumps(msg.get("tool_calls"), ensure_ascii=False, default=str)
                        if msg.get("tool_calls") else None
                    ),
                    "name": msg.get("name"),
                    "seq_index": index,
                }
                if existing:
                    for field, value in values.items():
                        setattr(existing, field, value)
                    updated += 1
                else:
                    session.add(ThreadMessage(
                        thread_id=thread_id,
                        message_id=msg_id,
                        **values,
                    ))
                    inserted += 1
                await session.flush()

            local_rows = (
                await session.execute(
                    select(ThreadMessage).where(ThreadMessage.thread_id == thread_id)
                )
            ).scalars().all()
            next_index = len(authority) + 1
            for row in sorted(local_rows, key=lambda item: item.message_id):
                if row.message_id not in authority_ids:
                    row.seq_index = next_index
                    next_index += 1

            deleted = 0
            if prune:
                delete_stmt = delete(ThreadMessage).where(
                    ThreadMessage.thread_id == thread_id
                )
                if authority_ids:
                    delete_stmt = delete_stmt.where(
                        ThreadMessage.message_id.not_in(authority_ids)
                    )
                result = await session.execute(delete_stmt)
                deleted = result.rowcount or 0

            await session.commit()
            return {"inserted": inserted, "updated": updated, "deleted": deleted, "error": False}
    except Exception as e:
        logger.warning("Failed to backfill local store for thread %s: %s", thread_id, e)
        return {"inserted": 0, "updated": 0, "deleted": 0, "error": True}
