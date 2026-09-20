"""Codebase-graph module (代码图谱) — managed repos and index run history.

A managed repo is a local directory the platform indexes through the
codebase-memory exe. File-type settings are materialized as a managed block
in the repo's .cbmignore before each (re)index; run history records both
manual and scheduled incremental index attempts per repo.

Impact reports record the optional after-index analysis: a headless run of
the codebase agent over the file changes the incremental index picked up.
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
    last_commit: Mapped[str | None] = mapped_column(String(64), nullable=True,
                                                    comment="最近一次成功索引时的 HEAD（非 git 仓库为空）")
    auto_analyze: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False,
                                               comment="是否参与索引后的增量影响分析")

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


class CodebaseImpactReport(Base, UUIDMixin, TimestampMixin):
    """代码图谱：一次「增量影响分析」的产物。

    索引成功后由无头智能体（codebase_agent）分析本轮变更的影响面，正文
    同时落库与落盘（workspace/default/codebase-reports/<project>/）。
    它是**附属产物**：生成失败只记 failed，绝不影响索引本身的成败。
    """

    __tablename__ = "codebase_impact_reports"
    __table_args__ = {"comment": "代码图谱：增量影响分析报告"}

    repo_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("codebase_repos.id", ondelete="CASCADE"), nullable=False, index=True)
    # 关联的索引运行（手动触发分析时可能为空）
    index_run_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("codebase_index_runs.id", ondelete="SET NULL"), nullable=True)
    trigger: Mapped[str] = mapped_column(String(20), default="scheduled", nullable=False,
                                         comment="manual | scheduled")
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False,
                                        comment="running | success | failed | skipped")
    model: Mapped[str | None] = mapped_column(String(120), nullable=True,
                                              comment="生成报告时使用的模型名")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True,
                                                comment="一句话结论（报告首段摘录）")
    content_md: Mapped[str | None] = mapped_column(Text, nullable=True,
                                                   comment="报告正文（Markdown）")
    # 本轮变更集：{mode, added[], modified[], deleted[], truncated, git:{...}}
    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True,
                                                  comment="落盘的 .md 绝对路径")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<CodebaseImpactReport(repo_id={self.repo_id}, status={self.status})>"
