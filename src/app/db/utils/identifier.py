"""Identifier generators for database records.

Generates unique identifiers in PR-xxx, TC-xxx, TR-xxx format.
Uses a SQLite-compatible counter table for sequence generation.
"""

from sqlalchemy import text

from src.app.db.database import async_session_factory


async def generate_identifier(prefix: str, lock_key: str) -> str:
    """Generate unique identifier using a counter table.

    Uses SQLite-compatible approach: reads and increments a counter
    row in the identifier_seq table within a transaction.

    Args:
        prefix: Identifier prefix (e.g. 'PR', 'TC', 'TR').
        lock_key: Counter key string.

    Returns:
        Formatted identifier string, e.g. 'PR-0001'.
    """
    async with async_session_factory() as session:
        # Ensure the counter row exists
        await session.execute(
            text(
                "INSERT OR IGNORE INTO identifier_seq (key, next_val) "
                "VALUES (:k, 1)"
            ),
            {"k": lock_key},
        )
        # Atomically increment and return the new value
        result = await session.execute(
            text(
                "UPDATE identifier_seq SET next_val = next_val + 1 "
                "WHERE key = :k RETURNING next_val"
            ),
            {"k": lock_key},
        )
        seq = result.scalar_one()
        await session.commit()
        return f"{prefix}-{seq:04d}"


def generate_identifier_simple(prefix: str) -> str:
    """Generate simple identifier without database dependency.

    For testing only. NOT concurrency-safe.
    """
    import random
    return f"{prefix}-{random.randint(1000, 9999)}"
