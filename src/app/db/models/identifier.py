"""Identifier sequence counter（PR-0001 / TC-0001 / … 的计数器）。

``db/utils/identifier.py`` 用**裸 SQL** 读写这张表（``INSERT OR IGNORE`` +
``UPDATE … RETURNING``，SQLite 上做原子自增最省事），但表本身必须有 declarative
模型：``init_db()`` 是按 ``Base.metadata`` 建表的，只存在于裸 SQL 里的表**永远
不会被创建**——于是 ``POST /api/v2/projects`` 必然在"no such table"上 500。

这是一张纯计数表：没有外键、没有时间戳、没有 UUID 主键。
``key`` = 计数器名字（如 ``project_identifier_seq``），``next_val`` = 下一个待发的值。
"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base


class IdentifierSeq(Base):
    """Named counter row, atomically incremented per identifier handed out."""

    __tablename__ = "identifier_seq"
    __table_args__ = {"comment": "Named counters for human-readable identifiers (PR-/TC-/TR-)"}

    key: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        comment="Counter name, e.g. project_identifier_seq",
    )
    next_val: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Next value to hand out",
    )

    def __repr__(self) -> str:
        return f"<IdentifierSeq {self.key}={self.next_val}>"
