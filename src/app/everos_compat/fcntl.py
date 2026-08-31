"""fcntl shim for EverOS on Windows.

EverOS (everos/core/persistence/locking.py) uses POSIX ``fcntl.flock`` for
cross-process exclusion on its memory-root; ``fcntl`` does not exist on
Windows and upstream explicitly lists Windows as out of scope. This shim
provides the tiny API surface EverOS touches — ``flock(fd, op)`` plus the
LOCK_* constants — backed by ``msvcrt.locking`` byte-range locks, which DO
give real cross-process exclusion on the same machine.

Semantics mapped:
- LOCK_EX|LOCK_NB → msvcrt.LK_NBLCK on 1 byte at offset 0; a held lock
  raises OSError(EACCES), re-raised as BlockingIOError — exactly the
  exception EverOS's poll loop catches.
- LOCK_UN → msvcrt.LK_UNLCK on the same byte (position is still 0 because
  EverOS never reads/writes the anchor file).

This module is only importable on Windows (real fcntl wins on POSIX: the
shim directory is prepended to PYTHONPATH only when launching EverOS from
our service layer on win32).
"""

from __future__ import annotations

import errno
import os
import sys

if sys.platform != "win32":  # pragma: no cover - never imported on POSIX
    raise ImportError("use the real fcntl on POSIX")

import msvcrt  # noqa: E402  (Windows-only import guarded above)

LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8

_LOCK_BYTE = 1


def flock(fd: int, operation: int) -> None:
    """Byte-range lock the first byte of ``fd`` honoring ``operation``."""
    mode = os.lseek(fd, 0, os.SEEK_SET)
    del mode  # position normalization only; EverOS never moves it itself
    try:
        if operation & LOCK_UN:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, _LOCK_BYTE)
        elif operation & LOCK_NB:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, _LOCK_BYTE)
            except OSError as exc:
                # Held by another process — surface as BlockingIOError,
                # the exact exception EverOS's poll loop handles.
                raise BlockingIOError(
                    errno.EACCES, "lock held by another process"
                ) from exc
        else:
            # EverOS never requests blocking flock (always LOCK_NB), but keep
            # a bounded retry loop for API completeness.
            msvcrt.locking(fd, msvcrt.LK_LOCK, _LOCK_BYTE)
    except OSError as exc:
        if isinstance(exc, BlockingIOError):
            raise
        raise OSError(errno.EIO, f"flock shim failed: {exc}") from exc
