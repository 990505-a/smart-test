"""Database engine, session factory, and initialization.

Provides the SQLAlchemy async engine, session factory, Base declarative class,
and helper functions for database access used by both FastAPI endpoints
and Agent tools.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
)


def sqlite_enable_foreign_keys(dbapi_connection, connection_record):
    """SQLite 默认不启用外键约束，不开的话所有 ondelete=CASCADE/SET NULL 全部失效。

    挂在 sync_engine 的 connect 事件上对每个新连接生效；aiosqlite 适配的
    cursor 在连接池建连上下文内可同步执行。
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


event.listen(engine.sync_engine, "connect", sqlite_enable_foreign_keys)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base class."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a session, commits on success, rollbacks on error.

    Usage in FastAPI routes::

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables from SQLAlchemy metadata (dev mode).

    For production, use Alembic migrations instead.
    """
    from sqlalchemy import text

    async with engine.begin() as conn:
        # 「UI 自动化」改名「Unity 自动化」：把旧库的表就地改名，避免
        # create_all 另建新表、旧脚本记录变孤儿。改名必须在 create_all
        # 之前——表已存在时 RENAME 是唯一正确的迁移，create_all 只补缺失表。
        for old, new in (("ui_scripts", "unity_scripts"),
                         ("ui_script_runs", "unity_script_runs")):
            has_old = (await conn.execute(text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"
            ), {"n": old})).first()
            has_new = (await conn.execute(text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"
            ), {"n": new})).first()
            if has_old is not None and has_new is None:
                await conn.execute(text(f'ALTER TABLE "{old}" RENAME TO "{new}"'))

        await conn.run_sync(Base.metadata.create_all)

        # SQLite cannot drop a single-column UNIQUE constraint in place. Older
        # databases declared thread_messages.message_id globally unique, while
        # message IDs are only unique within a LangGraph thread. Rebuild this
        # one table once so existing installations match the model constraint.
        index_rows = (
            await conn.execute(text("PRAGMA index_list('thread_messages')"))
        ).mappings().all()
        global_message_unique = False
        for row in index_rows:
            if not row.get("unique"):
                continue
            columns = (
                await conn.execute(text(f"PRAGMA index_info('{row['name']}')"))
            ).mappings().all()
            if [column.get("name") for column in columns] == ["message_id"]:
                global_message_unique = True
                break
        if global_message_unique:
            await conn.execute(text("DROP INDEX IF EXISTS ix_thread_messages_thread_id"))
            await conn.execute(text("DROP INDEX IF EXISTS ix_thread_messages_thread_seq"))
            await conn.execute(text("""
                CREATE TABLE thread_messages_new (
                    thread_id VARCHAR(64) NOT NULL,
                    message_id VARCHAR(128) NOT NULL,
                    msg_type VARCHAR(16) NOT NULL,
                    content TEXT NOT NULL,
                    additional_kwargs TEXT,
                    tool_calls TEXT,
                    name VARCHAR(256),
                    seq_index INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    id CHAR(32) NOT NULL PRIMARY KEY,
                    CONSTRAINT uq_thread_messages_thread_message
                        UNIQUE (thread_id, message_id)
                )
            """))
            await conn.execute(text("""
                INSERT INTO thread_messages_new
                    (thread_id, message_id, msg_type, content,
                     additional_kwargs, tool_calls, name, seq_index,
                     created_at, id)
                SELECT thread_id, message_id, msg_type, content,
                       additional_kwargs, tool_calls, name, seq_index,
                       created_at, id
                FROM thread_messages
            """))
            await conn.execute(text("DROP TABLE thread_messages"))
            await conn.execute(text("ALTER TABLE thread_messages_new RENAME TO thread_messages"))
            await conn.execute(text(
                "CREATE INDEX ix_thread_messages_thread_id ON thread_messages (thread_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX ix_thread_messages_thread_seq "
                "ON thread_messages (thread_id, seq_index)"
            ))

        # create_all 只建缺失的表，不会给已有表加列。新列在此做轻量迁移：
        # ALTER 失败（列已存在）直接忽略——SQLite 报 duplicate column name。
        for stmt in (
            "ALTER TABLE thread_infos ADD COLUMN deleted BOOLEAN NOT NULL DEFAULT 0",
            "ALTER TABLE thread_infos ADD COLUMN agent VARCHAR(64) NOT NULL DEFAULT ''",
            # 会话级前端设置（权限/思考强度/模型预设/智能体/仓库）持久化
            "ALTER TABLE thread_infos ADD COLUMN config TEXT NOT NULL DEFAULT ''",
            # 代码图谱：增量影响分析（commit 基线 + 每仓库参与开关）
            "ALTER TABLE codebase_repos ADD COLUMN last_commit VARCHAR(64)",
            "ALTER TABLE codebase_repos ADD COLUMN auto_analyze BOOLEAN NOT NULL DEFAULT 0",
            # Unity 执行记录：运行目录（执行中读实时产物与步骤轨迹用）
            "ALTER TABLE unity_script_runs ADD COLUMN workdir TEXT",
            # 对话消息：每条 AI 回复的 token 用量（对话页展示用）
            "ALTER TABLE thread_messages ADD COLUMN usage_metadata TEXT",
        ):
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass

        # 「工作区」模块已整体删除（选目录 UI + workspaces CRUD + 表）。
        # 表留在库里只会让后来者以为还有东西在用，直接清掉。
        try:
            await conn.execute(text("DROP TABLE IF EXISTS workspaces"))
        except Exception:
            pass
