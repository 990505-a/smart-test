"""CircuitBreaker state machine for resilient HTTP calls.

Implements the classic circuit breaker pattern:
- CLOSED: Normal operation. Requests flow through. Failures are counted.
- OPEN: Too many failures. Requests are blocked (raises CircuitOpenError).
- HALF_OPEN: Recovery test. One request is allowed to probe the service.

Transitions:
    CLOSED -> OPEN: After fail_max consecutive failures.
    OPEN -> HALF_OPEN: After reset_timeout seconds have elapsed.
    HALF_OPEN -> CLOSED: On first successful request.
    HALF_OPEN -> OPEN: On any failure during probe.

Uses time.monotonic() for timing (no asyncio dependency).
"""

from __future__ import annotations

import enum
import time


class CircuitState(enum.Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is OPEN and blocking requests."""


class CircuitBreaker:
    """Thread-safe circuit breaker with configurable thresholds.

    Args:
        fail_max: Number of consecutive failures before opening (default: 5).
        reset_timeout: Seconds to wait before transitioning OPEN -> HALF_OPEN (default: 30).
    """

    def __init__(self, fail_max: int = 5, reset_timeout: int = 30) -> None:
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> CircuitState:
        """Current circuit breaker state."""
        return self._state

    def record_success(self) -> None:
        """Record a successful operation. Resets failure counter, transitions to CLOSED."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed operation. Increments counter, trips to OPEN when threshold reached."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.fail_max:
            self._state = CircuitState.OPEN

    def check_state(self) -> None:
        """Check whether a request is allowed.

        Raises:
            CircuitOpenError: If the breaker is OPEN and reset_timeout has not elapsed.
        """
        if self._state == CircuitState.CLOSED:
            return

        if self._state == CircuitState.HALF_OPEN:
            return

        # State is OPEN -- check if reset_timeout has elapsed
        elapsed = time.monotonic() - self._last_failure_time
        if elapsed >= self.reset_timeout:
            self._state = CircuitState.HALF_OPEN
            return

        raise CircuitOpenError(
            f"Circuit breaker is OPEN. "
            f"Failures: {self._failure_count}/{self.fail_max}. "
            f"Retry after {self.reset_timeout - elapsed:.1f}s."
        )
