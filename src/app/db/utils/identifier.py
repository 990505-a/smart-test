"""Identifier generators for database records.

Generates unique identifiers in PR-xxx, TC-xxx, TR-xxx format
using PostgreSQL advisory locks for concurrency safety.
Also provides a simple fallback for non-PostgreSQL testing.
"""

import random

from sqlalchemy import text

from src.app.db.database import async_session_factory


async def generate_identifier(prefix: str, lock_key: str) -> str:
    """Generate unique identifier using PostgreSQL advisory lock.

    Generates identifiers like PR-1234, TC-5678 using a sequence
    and advisory lock for concurrency safety.

    Args:
        prefix: Identifier prefix (e.g. 'PR', 'TC', 'TR').
        lock_key: Unique lock key string for advisory lock.

    Returns:
        Formatted identifier string, e.g. 'PR-0001'.
    """
    async with async_session_factory() as session:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": lock_key},
        )
        # Get next sequence number
        result = await session.execute(
            text("SELECT nextval('identifier_seq')"),
        )
        seq = result.scalar_one()
        return f"{prefix}-{seq:04d}"


def generate_identifier_simple(prefix: str) -> str:
    """Generate simple identifier without database dependency.

    For testing and non-PostgreSQL environments. NOT concurrency-safe.

    Args:
        prefix: Identifier prefix (e.g. 'PR', 'TC', 'TR').

    Returns:
        Formatted identifier string, e.g. 'PR-4821'.
    """
    return f"{prefix}-{random.randint(1000, 9999)}"
