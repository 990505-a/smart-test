"""Imported API docs from Feishu (接口自动化模块)."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin


class ApiDocImport(Base, UUIDMixin, TimestampMixin):
    """A Feishu API doc fetched via lark-cli, with LLM-extracted endpoints."""

    __tablename__ = "api_doc_imports"
    __table_args__ = {"comment": "Feishu API doc imports"}

    doc_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="原始文档内容")
    endpoints: Mapped[str | None] = mapped_column(Text, nullable=True,
                                                  comment="JSON: LLM 提取的接口清单")
    endpoint_count: Mapped[str] = mapped_column(String(10), default="0", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="imported", nullable=False,
                                        comment="imported | parsed | failed")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ApiDocImport(title={self.title}, status={self.status})>"
