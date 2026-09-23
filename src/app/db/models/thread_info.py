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
    # 这个会话用哪个智能体（LangGraph assistant id，如 testcase_agent）。
    # 会话列表拿它显示"这条对话是哪个模式的"，点开历史会话时也靠它把模式切回去
    # （dsh 的会话记着自己的 agent，不靠 URL 上的 ?agent=）。
    agent: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        server_default="",
        comment="LangGraph assistant id this thread was created with",
    )

    # 会话级前端设置（JSON 字符串）：权限档位 / 思考强度 / 模型预设 / 智能体 /
    # 代码图谱仓库。这些选择以前只活在 URL 参数里，重启或从别的页面回来就回落
    # 默认值（2026-09-22 修复）。键名与 run configurable 对齐：
    # permission_mode / llm_reasoning_effort / model_preset / agent_id / repo_id
    config: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="Per-thread UI settings as JSON (permission/effort/model/agent/repo)",
    )

    # 删除墓碑：置 1 后不再出现在会话列表，且消息保存/线程注册都不会复活它
    # （行保留是为了挡住 upsert——按 thread_id 唯一键直接 insert 会复活）
    deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
