"""ThreadInfo model for persisting thread metadata.

Stores thread metadata (ID, title, timestamps) in SQLite so that
the thread list survives LangGraph inmem server restarts.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base


class ThreadInfo(Base):
    """Thread metadata persisted locally for survival across LangGraph restarts."""

    __tablename__ = "thread_infos"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # The LangGraph thread ID (the real identifier used by the frontend)
    thread_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="LangGraph thread ID",
    )

    # Thread title (derived from first human message)
    title: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        default="无标题对话",
        comment="Thread display title",
    )

    # Thread description (first AI message preview)
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="Thread description preview",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # 删除墓碑：置 1 后不再出现在会话列表，且消息保存/线程注册都不会复活它
    # （行保留是为了挡住 upsert——按 thread_id 唯一键直接 insert 会复活）
    deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
