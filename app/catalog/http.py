"""Shared HTTP plumbing: retries, backoff, rate limiting."""

from __future__ import annotations

import random
import threading
import time
from typing import Any

import httpx

from app.errors import UpstreamError
from app.logging_setup import get_logger

log = get_logger("http")

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class RateLimiter:
    """Simple thread-safe minimum-interval limiter."""

    def __init__(self, rate_per_second: float) -> None:
        self._min_interval = 1.0 / rate_per_second if rate_per_second > 0 else 0.0
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = self._next_allowed - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._next_allowed = now + self._min_interval


def backoff_delay(attempt: int, *, base: float = 1.0, cap: float = 30.0) -> float:
    """Exponential backoff with full jitter."""
    return random.uniform(0, min(cap, base * (2**attempt)))


def request_with_retries(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    max_retries: int,
    limiter: RateLimiter | None = None,
    error_cls: type[UpstreamError] = UpstreamError,
    retry_on_status: set[int] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    retry_on_status = retry_on_status or RETRYABLE_STATUS
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        if limiter is not None:
            limiter.acquire()
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            last_error = exc
            log.warning("http.timeout", url=url, attempt=attempt)
        except httpx.HTTPError as exc:
            last_error = exc
            log.warning("http.error", url=url, attempt=attempt, error=str(exc))
        else:
            if response.status_code in retry_on_status and attempt < max_retries:
                retry_after = _retry_after_seconds(response)
                delay = retry_after if retry_after is not None else backoff_delay(attempt)
                log.warning(
                    "http.retryable_status",
                    url=url,
                    status=response.status_code,
                    attempt=attempt,
                    sleep=round(delay, 2),
                )
                time.sleep(delay)
                continue
            return response

        if attempt < max_retries:
            time.sleep(backoff_delay(attempt))

    raise error_cls(f"{method} {url} failed after {max_retries + 1} attempts: {last_error}")


def _retry_after_seconds(response: httpx.Response) -> float | None:
    header = response.headers.get("retry-after")
    if not header:
        return None
    try:
        return float(header)
    except ValueError:
        return None


__all__ = ["RETRYABLE_STATUS", "RateLimiter", "backoff_delay", "request_with_retries"]
