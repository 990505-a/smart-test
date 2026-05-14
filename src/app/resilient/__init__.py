"""Resilient HTTP client with retry and circuit breaker.

Wraps httpx.AsyncClient with:
- Connection pooling (max 100 connections, 20 keepalive)
- Exponential backoff retry on recoverable errors (timeout, 5xx)
- Circuit breaker to prevent cascading failures

Usage:
    from src.app.resilient import ResilientClient

    client = ResilientClient()
    response = await client.get("https://api.example.com/spec.json")
    await client.close()
"""

from __future__ import annotations

import asyncio

import httpx

from src.app.core.config import settings
from src.app.resilient.circuit_breaker import CircuitBreaker

# Re-export CircuitBreaker and related types
from src.app.resilient.circuit_breaker import CircuitOpenError, CircuitState  # noqa: F401


class ResilientClient:
    """Resilient HTTP client with retry and circuit breaker.

    Uses httpx.AsyncClient for connection pooling and async I/O.
    Retries on recoverable errors (ConnectTimeout, ReadTimeout,
    RemoteProtocolError, 5xx HTTPStatusError) with exponential backoff.
    Does NOT retry on 4xx client errors.

    Args:
        breaker: Optional CircuitBreaker instance. If None, creates one
                 from settings (circuit_breaker_fail_max, circuit_breaker_reset_timeout).
    """

    def __init__(self, breaker: CircuitBreaker | None = None) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
            ),
        )
        self._breaker = breaker or CircuitBreaker(
            fail_max=settings.circuit_breaker_fail_max,
            reset_timeout=settings.circuit_breaker_reset_timeout,
        )

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """Send a GET request with retry and circuit breaker protection."""
        return await self._request_with_retry("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """Send a POST request with retry and circuit breaker protection."""
        return await self._request_with_retry("POST", url, **kwargs)

    async def _request_with_retry(
        self, method: str, url: str, **kwargs
    ) -> httpx.Response:
        """Execute an HTTP request with exponential backoff retry.

        Retries up to retry_max_attempts on recoverable errors:
        - httpx.ConnectTimeout
        - httpx.ReadTimeout
        - httpx.RemoteProtocolError
        - httpx.HTTPStatusError with status >= 500

        Does NOT retry on 4xx errors (client errors).

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL.
            **kwargs: Additional arguments passed to httpx.AsyncClient.request.

        Returns:
            httpx.Response on success.

        Raises:
            CircuitOpenError: If circuit breaker is OPEN.
            httpx.HTTPStatusError: On 4xx responses (no retry).
            httpx.TimeoutException: On timeout after all retries exhausted.
        """
        self._breaker.check_state()

        last_exception: Exception | None = None
        for attempt in range(settings.retry_max_attempts):
            try:
                response = await self._client.request(method, url, **kwargs)
                response.raise_for_status()
                self._breaker.record_success()
                return response
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500:
                    self._breaker.record_failure()
                    last_exception = e
                    if attempt < settings.retry_max_attempts - 1:
                        delay = min(
                            settings.retry_initial_delay * (2 ** attempt),
                            settings.retry_max_delay,
                        )
                        await asyncio.sleep(delay)
                    continue
                # 4xx: do not retry, do not affect circuit breaker
                raise
            except (
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.RemoteProtocolError,
            ) as e:
                self._breaker.record_failure()
                last_exception = e
                if attempt < settings.retry_max_attempts - 1:
                    delay = min(
                        settings.retry_initial_delay * (2 ** attempt),
                        settings.retry_max_delay,
                    )
                    await asyncio.sleep(delay)
                continue

        # All retries exhausted
        if last_exception is not None:
            raise last_exception
        msg = "Max retries exceeded"
        raise RuntimeError(msg)

    async def close(self) -> None:
        """Close the underlying httpx.AsyncClient."""
        await self._client.aclose()
