"""Authentication service (用户模块).

PBKDF2-HMAC-SHA256 password hashing (stdlib only) + opaque bearer tokens
persisted in the auth_tokens table.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.config import settings
from src.app.db.models.user import AuthToken, User

_PBKDF2_ITERATIONS = 120_000


def hash_password(password: str, *, salt: str | None = None) -> str:
    """Return 'pbkdf2$iterations$salt_hex$hash_hex'."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, _iter, salt, digest = stored.split("$", 3)
    except ValueError:
        return False
    candidate = hash_password(password, salt=salt).split("$", 3)[3]
    return hmac.compare_digest(candidate, digest)


class AuthService:
    """User registration, login, token lifecycle."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_default_admin(self) -> None:
        """Create the default admin account on first boot."""
        result = await self.db.execute(select(User).limit(1))
        if result.scalars().first() is not None:
            return
        admin = User(
            username=settings.auth_default_admin_username,
            password_hash=hash_password(settings.auth_default_admin_password),
            display_name="管理员",
            role="admin",
            must_change_password=True,
        )
        self.db.add(admin)
        await self.db.flush()

    async def get_by_username(self, username: str) -> User | None:
        result = await self.db.execute(select(User).where(User.username == username))
        return result.scalars().first()

    async def get_user(self, user_id) -> User | None:
        from uuid import UUID

        uid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id
        result = await self.db.execute(select(User).where(User.id == uid))
        return result.scalars().first()

    async def list_users(self) -> list[User]:
        result = await self.db.execute(select(User).order_by(User.created_at))
        return list(result.scalars().all())

    async def create_user(
        self, username: str, password: str, display_name: str | None = None, role: str = "tester"
    ) -> User:
        existing = await self.get_by_username(username)
        if existing is not None:
            raise ValueError(f"用户名已存在: {username}")
        user = User(
            username=username,
            password_hash=hash_password(password),
            display_name=display_name or username,
            role=role,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def login(self, username: str, password: str) -> tuple[User, str]:
        user = await self.get_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            raise ValueError("用户名或密码错误")
        if not user.is_active:
            raise ValueError("账号已停用")
        token = AuthToken(
            token=secrets.token_hex(32),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=settings.auth_token_ttl_hours),
        )
        self.db.add(token)
        await self.db.flush()
        return user, token.token

    async def authenticate_token(self, token: str) -> User | None:
        result = await self.db.execute(
            select(AuthToken).where(AuthToken.token == token, AuthToken.revoked.is_(False))
        )
        record = result.scalars().first()
        if record is None:
            return None
        if record.expires_at is not None:
            expires = record.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires < datetime.now(UTC):
                return None
        user = await self.get_user(record.user_id)
        if user is None or not user.is_active:
            return None
        return user

    async def logout(self, token: str) -> None:
        result = await self.db.execute(select(AuthToken).where(AuthToken.token == token))
        record = result.scalars().first()
        if record is not None:
            record.revoked = True
            await self.db.flush()

    async def change_password(self, user: User, old_password: str, new_password: str) -> None:
        if not verify_password(old_password, user.password_hash):
            raise ValueError("原密码错误")
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        await self.db.flush()

    async def change_username(self, user: User, new_username: str) -> None:
        existing = await self.get_by_username(new_username)
        if existing is not None and existing.id != user.id:
            raise ValueError(f"用户名已存在: {new_username}")
        user.username = new_username
        await self.db.flush()
