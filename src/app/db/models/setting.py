"""Key-value settings store (设置模块).

Model/provider and platform integration settings editable from the UI.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin


class SettingKV(Base, UUIDMixin, TimestampMixin):
    """Namespaced key-value setting, e.g. ('model', 'deepseek_model')."""

    __tablename__ = "settings_kv"
    __table_args__ = {"comment": "Platform key-value settings"}

    namespace: Mapped[str] = mapped_column(String(100), nullable=False, index=True,
                                           comment="model | platform | user")
    key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_secret: Mapped[str] = mapped_column(String(10), default="false", nullable=False,
                                           comment="'true' when value holds a secret")

    def __repr__(self) -> str:
        return f"<SettingKV({self.namespace}.{self.key})>"
