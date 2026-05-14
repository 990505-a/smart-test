"""SQLAlchemy base model definitions.

Provides the Base declarative class, UUIDMixin, and TimestampMixin
shared by all database models.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDMixin:
    """UUID primary key mixin."""

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        comment="Primary key ID",
    )


class TimestampMixin:
    """Timestamp mixin with created_at and updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Creation time",
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
        comment="Update time",
    )
