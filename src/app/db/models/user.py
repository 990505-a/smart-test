"""User and auth token models (用户模块).

Simple credential auth: PBKDF2 password hashes + opaque bearer tokens
stored server-side. No external dependencies required.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String, Text, Uuid, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin):
    """Platform user account."""

    __tablename__ = "users"
    __table_args__ = {"comment": "Platform users"}

    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="tester", nullable=False,
                                      comment="admin | tester | viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username})>"


class AuthToken(Base, UUIDMixin, TimestampMixin):
    """Opaque bearer token for API authentication."""

    __tablename__ = "auth_tokens"
    __table_args__ = {"comment": "API bearer tokens"}

    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<AuthToken(user_id={self.user_id}, revoked={self.revoked})>"
