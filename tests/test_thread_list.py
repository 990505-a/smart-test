"""会话列表可见性测试（懒创建改造的后端侧）。

前端已改为懒创建：点「新对话」不再预建空壳线程，线程在首条消息发送或
首次文件上传时才创建。GET /api/v2/threads 只返回有消息的会话——
会话可见性由内容决定（dsh 原则），历史遗留的零消息「无标题对话」
也由该过滤一并隐藏。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import src.app.db.database as db_module
from src.app.api.v2 import messages as messages_api
from src.app.db.database import Base
from src.app.db.models.thread_info import ThreadInfo
from src.app.db.models.thread_message import ThreadMessage


@pytest_asyncio.fixture
async def db_factory(monkeypatch):
    """In-memory SQLite shared across sessions (StaticPool) + patched factory."""
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", factory)
    # list_threads 通过模块级名字引用 factory，两条路径都要替换
    monkeypatch.setattr(messages_api, "async_session_factory", factory)
    yield factory
    await engine.dispose()


async def _thread(factory, title: str = "无标题对话", deleted: bool = False) -> str:
    tid = str(uuid.uuid4())
    async with factory() as s:
        s.add(ThreadInfo(thread_id=tid, title=title, deleted=deleted))
        await s.commit()
    return tid


async def _msg(factory, tid: str, seq: int = 1) -> None:
    async with factory() as s:
        s.add(ThreadMessage(
            thread_id=tid, message_id=str(uuid.uuid4()),
            msg_type="human", content="你好", seq_index=seq,
        ))
        await s.commit()


async def _list():
    """直连路由函数需显式传参——FastAPI Query 默认值只在 HTTP 层生效。"""
    return await messages_api.list_threads(limit=20, offset=0)


class TestListThreadsVisibility:
    @pytest.mark.asyncio
    async def test_empty_thread_hidden(self, db_factory):
        """零消息空壳（点新对话未发送的产物）不出现在列表。"""
        await _thread(db_factory)
        res = await _list()
        assert res["threads"] == []
        assert res["total"] == 0

    @pytest.mark.asyncio
    async def test_thread_with_message_visible(self, db_factory):
        """有消息的会话正常出现且标题保留。"""
        tid = await _thread(db_factory, title="你好")
        await _msg(db_factory, tid)
        res = await _list()
        assert res["total"] == 1
        assert res["threads"][0]["thread_id"] == tid
        assert res["threads"][0]["title"] == "你好"

    @pytest.mark.asyncio
    async def test_mixed_only_content_threads_listed(self, db_factory):
        """混合场景：空壳隐藏，只有有内容的会话列出。"""
        await _thread(db_factory, title="幽灵1")
        t2 = await _thread(db_factory, title="真会话2")
        await _msg(db_factory, t2)
        await _thread(db_factory, title="幽灵3")
        t4 = await _thread(db_factory, title="真会话4")
        await _msg(db_factory, t4)
        res = await _list()
        assert res["total"] == 2
        titles = {t["title"] for t in res["threads"]}
        assert titles == {"真会话2", "真会话4"}

    @pytest.mark.asyncio
    async def test_deleted_tombstone_with_messages_still_hidden(self, db_factory):
        """墓碑（deleted=True）即使残留消息也不出现——删除语义优先。"""
        tid = await _thread(db_factory, title="已删", deleted=True)
        await _msg(db_factory, tid)
        res = await _list()
        assert res["total"] == 0

    @pytest.mark.asyncio
    async def test_first_message_save_makes_thread_visible(self, db_factory):
        """懒创建时序：先建 ThreadInfo（无消息）不可见；保存首条消息后可见。

        对应 _upsert_thread_info 的兜底路径——即使前端注册了 ThreadInfo，
        列表也要等到有内容才显示。
        """
        tid = await _thread(db_factory)  # 模拟上传触发的 ensureThreadId 后未发送
        res = await _list()
        assert res["total"] == 0

        await _msg(db_factory, tid)  # 首条消息保存
        res = await _list()
        assert res["total"] == 1


class TestTitleDerivation:
    """标题应显示用户输入，而非中间件注入的上下文前缀。"""

    def _msg(self, content):
        from src.app.api.v2.messages import MessageInput

        return MessageInput(id=str(uuid.uuid4()), type="human", content=content)

    def test_plain_text_title(self):
        from src.app.api.v2.messages import _derive_thread_title

        assert _derive_thread_title([self._msg("你好")]) == "你好"

    def test_injected_context_prefix_stripped(self):
        """流式保存的人类消息带 [代码分析上下文]/仓库路径 注入——剥离后取用户文本。"""
        from src.app.api.v2.messages import _derive_thread_title

        content = (
            "[代码分析上下文 - 可在任何阶段使用此信息辅助分析] 仓库路径: E:/repo\n"
            "测试懒创建会话"
        )
        assert _derive_thread_title([self._msg(content)]) == "测试懒创建会话"

    def test_long_title_truncated(self):
        from src.app.api.v2.messages import _derive_thread_title

        title = _derive_thread_title([self._msg("字" * 60)])
        assert title == "字" * 50 + "..."

    @pytest.mark.asyncio
    async def test_legacy_prefix_title_self_heals(self, db_factory):
        """存量"[代码分析上下文 ..."标题在后续保存推导出干净标题时被替换。"""
        from src.app.api.v2.messages import MessageInput, _upsert_thread_info

        tid = await _thread(db_factory, title="[代码分析上下文 - xxx] 仓库路径: E:/repo")
        await _msg(db_factory, tid)  # 有内容才可见（可见性过滤）
        async with db_factory() as s:
            await _upsert_thread_info(s, tid, [
                MessageInput(id=str(uuid.uuid4()), type="human", content="真正的用户问题"),
            ])
            await s.commit()
        res = await _list()
        titles = [t["title"] for t in res["threads"] if t["thread_id"] == tid]
        assert titles == ["真正的用户问题"]

    @pytest.mark.asyncio
    async def test_concurrent_insert_conflict_ignored(self, db_factory):
        """并发注册竞态回归（2026-08-28 事故）：同一 thread_id 的并发
        INSERT 曾撞 UNIQUE 约束 → 保存 500 → 事务回滚丢消息 → 线程零消息
        被可见性过滤隐藏。on_conflict_do_nothing 后二次插入静默跳过。
        """
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        tid = "race-thread-" + uuid.uuid4().hex[:8]
        stmt = (
            sqlite_insert(ThreadInfo)
            .values(thread_id=tid, title="并发赢家")
            .on_conflict_do_nothing(index_elements=["thread_id"])
        )
        async with db_factory() as s:
            await s.execute(stmt)  # 先到者
            await s.execute(stmt)  # 后到者——修复前这里抛 UNIQUE 约束异常
            await s.commit()
            row = (await s.execute(
                select(ThreadInfo).where(ThreadInfo.thread_id == tid)
            )).scalar_one()
            assert row.title == "并发赢家"  # 先到者胜出，行唯一
