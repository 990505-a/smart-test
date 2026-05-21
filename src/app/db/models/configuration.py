"""Configuration model definition.

Stores OS/browser/device configuration combos for test execution.
Follows BrowserStack API pattern with integer primary key.
"""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin


class Configuration(Base, TimestampMixin):
    """Configuration table - stores OS/browser/device combinations for test runs."""

    __tablename__ = "configurations"
    __table_args__ = {"comment": "Test execution configurations"}

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    os: Mapped[str | None] = mapped_column(String(100), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    device: Mapped[str | None] = mapped_column(String(200), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(100), nullable=True)
    browser_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Configuration(id={self.id}, name={self.name})>"
