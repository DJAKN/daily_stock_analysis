# -*- coding: utf-8 -*-
"""
Token-bucket rate limiter shared across data provider managers.

Multiple managers that share a provider (e.g. FundamentalManager +
NewsManager both using FMP) go through the same limiter instance.
"""

import threading
import time
from dataclasses import dataclass
from typing import Dict

_PERIOD_MAP = {
    "second": 1,
    "minute": 60,
    "day": 86400,
}


@dataclass
class RateLimit:
    """Declarative rate limit: max_calls within a period."""

    max_calls: int
    period: str  # "second" | "minute" | "day"

    @property
    def period_seconds(self) -> int:
        if self.period not in _PERIOD_MAP:
            raise ValueError(
                f"Unsupported period '{self.period}'; "
                f"valid values: {list(_PERIOD_MAP.keys())}"
            )
        return _PERIOD_MAP[self.period]


class _Bucket:
    """Internal token bucket for a single provider."""

    __slots__ = ("limit", "tokens", "last_refill", "lock")

    def __init__(self, limit: RateLimit) -> None:
        self.limit = limit
        self.tokens = limit.max_calls
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        period_s = self.limit.period_seconds
        if elapsed >= period_s:
            # Full refill — how many periods have passed
            periods = int(elapsed / period_s)
            self.tokens = min(
                self.limit.max_calls,
                self.tokens + periods * self.limit.max_calls,
            )
            self.last_refill += periods * period_s

    def acquire(self) -> bool:
        with self.lock:
            self._refill()
            if self.tokens > 0:
                self.tokens -= 1
                return True
            return False

    def remaining(self) -> int:
        with self.lock:
            self._refill()
            return self.tokens


class SharedRateLimiter:
    """Thread-safe rate limiter shared across data provider managers.

    Usage::

        limiter = SharedRateLimiter()
        limiter.configure("fmp", RateLimit(max_calls=300, period="minute"))

        if limiter.acquire("fmp"):
            # proceed with API call
            ...
    """

    def __init__(self) -> None:
        self._buckets: Dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def configure(self, provider: str, limit: RateLimit) -> None:
        """Register or update the rate limit for a provider."""
        with self._lock:
            self._buckets[provider] = _Bucket(limit)

    def acquire(self, provider: str) -> bool:
        """Consume one token for *provider*. Returns True if allowed.

        Unconfigured providers always return True.
        """
        with self._lock:
            bucket = self._buckets.get(provider)
        if bucket is None:
            return True
        return bucket.acquire()

    def remaining(self, provider: str) -> int:
        """Return remaining tokens for *provider*.

        Unconfigured providers return ``float('inf')``.
        """
        with self._lock:
            bucket = self._buckets.get(provider)
        if bucket is None:
            return float("inf")
        return bucket.remaining()
