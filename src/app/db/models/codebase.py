"""Codebase-graph module (代码图谱) — managed repos and index run history.

A managed repo is a local directory the platform indexes through the
codebase-memory exe. File-type settings are materialized as a managed block
in the repo's .cbmignore before each (re)index; run history records both
manual and scheduled incremental index attempts per repo.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin


class CodebaseRepo(Base, UUIDMixin, TimestampMixin):
    """A repository under platform-managed code-graph indexing."""

    __tablename__ = "codebase_repos"
    __table_args__ = {"comment": "代码图谱：受管仓库"}

    repo_path: Mapped[str] = mapped_column(String(500), unique=True, index=True,
                                           nullable=False, comment="仓库绝对路径（正斜杠）")
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True,
                                                     comment="可选别名")
    # all: 不生成任何规则；include: 仅索引列出的扩展名；exclude: 排除列出的扩展名
    file_type_mode: Mapped[str] = mapped_column(String(16), default="all", nullable=False,
                                                comment="all | include | exclude")
    file_types: Mapped[list] = mapped_column(JSON, default=list, nullable=False,
                                             comment='扩展名列表，如 [".gs", ".lua"]')
    auto_increment: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False,
                                                 comment="是否参与定时增量索引")
    last_index_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                           nullable=True,
                                                           comment="最近一次成功索引时间（缓存字段）")
    last_index_mode: Mapped[str | None] = mapped_column(String(16), nullable=True,
                                                        comment="最近一次索引模式 fast|moderate|full")

    def __repr__(self) -> str:
        return f"<CodebaseRepo(id={self.id}, path={self.repo_path})>"


class CodebaseIndexRun(Base, UUIDMixin, TimestampMixin):
    """One index attempt (manual or scheduled) against one managed repo."""

    __tablename__ = "codebase_index_runs"
    __table_args__ = {"comment": "代码图谱：索引运行历史"}

    repo_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("codebase_repos.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(20), default="manual", nullable=False,
                                         comment="manual | scheduled")
    mode: Mapped[str] = mapped_column(String(16), default="fast", nullable=False,
                                      comment="fast | moderate | full")
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False,
                                        comment="running | success | failed | skipped")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 跳过原因 / 索引统计 / 错误信息等 JSON 快照
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<CodebaseIndexRun(repo_id={self.repo_id}, status={self.status})>"
