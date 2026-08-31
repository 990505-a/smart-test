"""Safe async subprocess execution helpers.

The asyncio subprocess APIs do not terminate a child when ``communicate`` is
cancelled or times out.  This module centralizes the terminate/kill-and-reap
sequence so callers cannot accidentally leave orphaned test processes behind.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from os import PathLike
from typing import Any


_CLEANUP_TIMEOUT = 5.0


async def _cleanup_process(
    process: asyncio.subprocess.Process,
    *,
    timeout: float = _CLEANUP_TIMEOUT,
) -> None:
    """Terminate a process, escalate to kill, and drain its stdio pipes."""
    if process.returncode is not None:
        return

    process.terminate()
    try:
        await asyncio.wait_for(process.communicate(), timeout=timeout)
        return
    except (asyncio.TimeoutError, ProcessLookupError):
        pass

    if process.returncode is None:
        process.kill()
    try:
        await asyncio.wait_for(process.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, ProcessLookupError):
        # There is no useful recovery left; the caller's timeout/cancellation
        # should retain precedence over a best-effort cleanup failure.
        pass


async def run_subprocess(
    *args: str | bytes | PathLike[str] | PathLike[bytes],
    timeout: float | None = None,
    cleanup_timeout: float = _CLEANUP_TIMEOUT,
    **kwargs: Any,
) -> tuple[bytes, bytes, int]:
    """Run an async subprocess and clean it up on timeout or cancellation.

    Returns ``(stdout, stderr, returncode)``.  ``TimeoutError`` is propagated
    after the child is reaped, while ``CancelledError`` is propagated after
    cleanup as well.  All regular ``create_subprocess_exec`` keyword
    arguments (including ``cwd`` and ``env``) are accepted.
    """
    process = await asyncio.create_subprocess_exec(*args, **kwargs)
    try:
        communicate = process.communicate()
        if timeout is None:
            stdout, stderr = await communicate
        else:
            stdout, stderr = await asyncio.wait_for(communicate, timeout=timeout)
    except asyncio.TimeoutError:
        await _cleanup_process(process, timeout=cleanup_timeout)
        raise
    except asyncio.CancelledError:
        # Shield cleanup so task cancellation cannot interrupt the reap.
        await asyncio.shield(_cleanup_process(process, timeout=cleanup_timeout))
        raise
    return stdout or b"", stderr or b"", process.returncode or 0


__all__ = ["run_subprocess"]
