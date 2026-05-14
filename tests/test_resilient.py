"""Tests for ResilientClient and CircuitBreaker."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest


# =============================================================================
# CircuitBreaker tests
# =============================================================================


def test_circuit_breaker_initial_closed():
    """CircuitBreaker starts in CLOSED state."""
    from src.app.resilient.circuit_breaker import CircuitBreaker, CircuitState

    breaker = CircuitBreaker(fail_max=5, reset_timeout=30)
    assert breaker.state == CircuitState.CLOSED


def test_circuit_breaker_opens_after_failures():
    """CircuitBreaker opens after 5 consecutive record_failure() calls."""
    from src.app.resilient.circuit_breaker import CircuitBreaker, CircuitState

    breaker = CircuitBreaker(fail_max=5, reset_timeout=30)
    for _ in range(5):
        breaker.record_failure()
    assert breaker.state == CircuitState.OPEN


def test_circuit_breaker_half_open_after_timeout():
    """CircuitBreaker transitions to HALF_OPEN after reset_timeout."""
    from src.app.resilient.circuit_breaker import CircuitBreaker, CircuitState

    breaker = CircuitBreaker(fail_max=5, reset_timeout=1)
    # Trip to OPEN
    for _ in range(5):
        breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    # Wait for reset timeout
    time.sleep(1.1)

    # check_state should transition to HALF_OPEN
    breaker.check_state()  # Should NOT raise
    assert breaker.state == CircuitState.HALF_OPEN


def test_circuit_breaker_check_state_raises_when_open():
    """CircuitBreaker check_state() raises CircuitOpenError when OPEN."""
    from src.app.resilient.circuit_breaker import CircuitBreaker, CircuitOpenError

    breaker = CircuitBreaker(fail_max=3, reset_timeout=300)
    for _ in range(3):
        breaker.record_failure()

    with pytest.raises(CircuitOpenError):
        breaker.check_state()


def test_circuit_breaker_success_resets():
    """record_success() resets failure counter and transitions to CLOSED."""
    from src.app.resilient.circuit_breaker import CircuitBreaker, CircuitState

    breaker = CircuitBreaker(fail_max=3, reset_timeout=30)
    # Partially fail
    for _ in range(2):
        breaker.record_failure()
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED

    # Should need 3 more failures to open (counter was reset)
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state == CircuitState.OPEN


# =============================================================================
# ResilientClient tests
# =============================================================================


def _make_response(status_code: int, text: str = "OK", url: str = "http://example.com") -> httpx.Response:
    """Create an httpx.Response with a proper request object set."""
    request = httpx.Request("GET", url)
    response = httpx.Response(status_code, text=text, request=request)
    return response


@pytest.mark.asyncio
async def test_retry_on_timeout():
    """ResilientClient retries on httpx.ConnectTimeout, succeeds on second attempt."""
    from src.app.resilient import ResilientClient

    client = ResilientClient()

    mock_response = _make_response(200, "OK")

    call_count = 0

    async def mock_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectTimeout("Connection timed out")
        return mock_response

    with patch.object(client._client, "request", side_effect=mock_request):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            response = await client.get("http://example.com/api")

    assert response.status_code == 200
    assert call_count == 2
    await client.close()


@pytest.mark.asyncio
async def test_no_retry_on_4xx():
    """ResilientClient does NOT retry on 4xx HTTP errors."""
    from src.app.resilient import ResilientClient

    client = ResilientClient()

    call_count = 0

    async def mock_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        response = _make_response(400, "Bad Request", url)
        raise httpx.HTTPStatusError(
            "Bad Request",
            request=httpx.Request("GET", url),
            response=response,
        )

    with patch.object(client._client, "request", side_effect=mock_request):
        with pytest.raises(httpx.HTTPStatusError):
            await client.get("http://example.com/api")

    assert call_count == 1  # No retry
    await client.close()
