from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.app.api.v2 import messages as messages_api
from src.app.db.database import Base
import src.app.db.database as db_module
from src.app.db.models.thread_info import ThreadInfo
from src.app.db.models.thread_message import ThreadMessage


@pytest_asyncio.fixture
async def db_factory(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", factory)
    monkeypatch.setattr(messages_api, "async_session_factory", factory)
    yield factory
    await engine.dispose()


async def _add_message(factory, thread_id: str, message_id: str, seq: int) -> None:
    async with factory() as session:
        session.add(ThreadMessage(
            thread_id=thread_id, message_id=message_id, msg_type="human",
            content=message_id, seq_index=seq,
        ))
        await session.commit()


@pytest.mark.asyncio
async def test_get_messages_route_targets_history_handler():
    """The GET history route must not expose the tombstone helper."""
    route = next(
        route for route in messages_api.router.routes
        if getattr(route, "path", "") == "/threads/{thread_id}/messages"
        and "GET" in (getattr(route, "methods", None) or set())
    )
    assert route.endpoint is messages_api.get_thread_messages


@pytest.mark.asyncio
async def test_local_cursor_is_composite_keyset_and_invalid_is_400(db_factory):
    tid = "thread-" + uuid.uuid4().hex
    await _add_message(db_factory, tid, "b", 1)
    await _add_message(db_factory, tid, "a", 1)
    await _add_message(db_factory, tid, "c", 2)

    first = await messages_api._get_messages_from_local(tid, 2, None, 3)
    assert [m["id"] for m in first["messages"]] == ["b", "c"]
    assert first["has_more"] is True
    assert messages_api._decode_cursor(first["next_cursor"]) == (1, "b")

    older = await messages_api._get_messages_from_local(
        tid, 2, first["next_cursor"], 3
    )
    assert [m["id"] for m in older["messages"]] == ["a"]
    assert older["has_more"] is False

    with pytest.raises(messages_api.HTTPException) as exc:
        await messages_api._get_messages_from_local(tid, 2, "legacy-id", 3)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_backfill_deduplicates_ids_before_assigning_sequence(db_factory):
    tid = "thread-" + uuid.uuid4().hex
    counts = await messages_api._backfill_local_store(tid, [
        {"id": "same", "type": "human", "content": "old"},
        {"id": "same", "type": "human", "content": "new"},
        {"id": "last", "type": "ai", "content": "done"},
    ])
    assert counts["inserted"] == 2
    async with db_factory() as session:
        rows = (await session.execute(
            select(ThreadMessage).where(ThreadMessage.thread_id == tid)
            .order_by(ThreadMessage.seq_index)
        )).scalars().all()
    assert [(row.message_id, row.seq_index, row.content) for row in rows] == [
        ("same", 1, "new"), ("last", 2, "done")
    ]


@pytest.mark.asyncio
async def test_delete_commits_local_tombstone_before_best_effort_langgraph(db_factory):
    tid = "thread-" + uuid.uuid4().hex
    async with db_factory() as session:
        session.add(ThreadInfo(thread_id=tid, title="thread"))
        session.add(ThreadMessage(
            thread_id=tid, message_id="message", msg_type="human",
            content="hello", seq_index=1,
        ))
        await session.commit()

    client = AsyncMock()
    client.threads.delete.side_effect = RuntimeError("LangGraph unavailable")
    with patch("langgraph_sdk.get_client", return_value=client):
        result = await messages_api.delete_thread(tid)
    assert result["langgraph_deleted"] is False

    async with db_factory() as session:
        info = (await session.execute(
            select(ThreadInfo).where(ThreadInfo.thread_id == tid)
        )).scalar_one()
        messages = (await session.execute(
            select(ThreadMessage).where(ThreadMessage.thread_id == tid)
        )).scalars().all()
    assert info.deleted is True
    assert messages == []

    # A late stream finalizer cannot write through the tombstone.
    ignored = await messages_api.save_thread_messages(
        tid,
        messages_api.SaveMessagesRequest(messages=[
            messages_api.MessageInput(id="late", type="ai", content="late")
        ]),
    )
    assert ignored["ignored"] is True
    assert (await messages_api.get_thread_messages(tid, 20, None))["messages"] == []


@pytest.mark.asyncio
async def test_sync_with_empty_authoritative_state_does_not_prune(db_factory, monkeypatch):
    """权威源为空时**不许** prune —— 那多半是 agent 服务重启丢了内存态。

    实测踩过（2026-09-19）：重启一次 agent 服务（inmem 运行时，检查点重启即空），
    前端重连结束时照例 `messages/sync?prune=true`，把整段对话从平台库里删掉了 ——
    用户看到的是"聊天记录凭空消失"。
    """
    import langgraph_sdk

    tid = "thread-" + uuid.uuid4().hex
    await _add_message(db_factory, tid, "a", 1)
    await _add_message(db_factory, tid, "b", 2)

    class _FakeThreads:
        async def get_state(self, thread_id):
            return {"values": {}}          # 空状态

    class _FakeClient:
        threads = _FakeThreads()

    monkeypatch.setattr(langgraph_sdk, "get_client", lambda **kw: _FakeClient())

    out = await messages_api.sync_thread_messages(tid, prune=True)

    assert out["pruned"] == 0 and out["skipped_prune"] is True
    async with db_factory() as session:
        left = (await session.execute(
            select(ThreadMessage).where(ThreadMessage.thread_id == tid)
        )).scalars().all()
    assert len(left) == 2, "本地历史不能被空状态删掉"


@pytest.mark.asyncio
async def test_sync_with_real_state_still_prunes(db_factory, monkeypatch):
    """权威源非空时 prune 照旧：留下 state 里有的，删掉 state 里没有的。"""
    import langgraph_sdk

    tid = "thread-" + uuid.uuid4().hex
    await _add_message(db_factory, tid, "a", 1)
    await _add_message(db_factory, tid, "leaked", 2)

    class _FakeThreads:
        async def get_state(self, thread_id):
            return {"values": {"messages": [
                {"id": "a", "type": "human", "content": "a"}]}}

    class _FakeClient:
        threads = _FakeThreads()

    monkeypatch.setattr(langgraph_sdk, "get_client", lambda **kw: _FakeClient())

    out = await messages_api.sync_thread_messages(tid, prune=True)

    assert out["pruned"] == 1
    assert (await messages_api.get_thread_messages(tid, 20, None))["messages"][-1]["id"] == "a"
