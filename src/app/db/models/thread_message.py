"""ThreadMessage model for storing chat messages locally.

Stores individual messages from LangGraph threads in SQLite so that
message history can be retrieved without loading the full thread state
from the LangGraph API (which fails for large 25MB+ threads).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, Integer, String, Text, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base
from src.app.db.models.base import UUIDMixin


class ThreadMessage(Base, UUIDMixin):
    """A single message in a LangGraph thread, stored locally for fast retrieval."""

    __tablename__ = "thread_messages"

    # The LangGraph thread this message belongs to
    thread_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="LangGraph thread ID",
    )

    # The LangGraph message ID (used for deduplication and cursor-based pagination)
    message_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="LangGraph message ID (unique within a thread)",
    )

    # Message type: human, ai, tool, system
    msg_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="Message type: human, ai, tool, system",
    )

    # Message content (JSON string or plain text)
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="Message content (text or JSON-serialized structured content)",
    )

    # Additional kwargs (JSON-serialized)
    additional_kwargs: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Additional kwargs (JSON-serialized)",
    )

    # Tool calls (JSON-serialized list)
    tool_calls: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Tool calls (JSON-serialized list)",
    )

    # Tool name (for tool messages)
    name: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        comment="Tool name (for tool messages)",
    )

    # Sequential index within the thread for ordering
    seq_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Sequential index within thread (for ordering)",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Creation time",
    )

    __table_args__ = (
        UniqueConstraint("thread_id", "message_id", name="uq_thread_messages_thread_message"),
        Index("ix_thread_messages_thread_seq", "thread_id", "seq_index"),
    )
