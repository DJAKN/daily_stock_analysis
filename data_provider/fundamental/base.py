# -*- coding: utf-8 -*-
"""
Abstract base class for fundamental data fetchers.

Each provider implements this interface, allowing FundamentalManager
to iterate providers by priority with automatic failover.
"""

import logging
import math
from abc import ABC, abstractmethod
from typing import Optional

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .types import UnifiedFundamentalData

logger = logging.getLogger(__name__)

_TRANSIENT_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)

_REQUEST_TIMEOUT = 10  # seconds


class BaseFundamentalFetcher(ABC):
    """Abstract base class for fundamental data fetchers.

    Subclasses must define:
        name: str       — provider identifier (e.g. "fmp", "finnhub")
        priority: int   — lower number = higher priority

    And implement:
        get_fundamentals(stock_code) -> Optional[UnifiedFundamentalData]
        is_available() -> bool
    """

    name: str = ""
    priority: int = 999

    @abstractmethod
    def get_fundamentals(self, stock_code: str) -> Optional[UnifiedFundamentalData]:
        """Fetch fundamental data for a US stock ticker.

        Returns UnifiedFundamentalData on success, None on failure.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider is configured and ready to use."""

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type(_TRANSIENT_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _get_json(self, url: str, **kwargs) -> Optional[dict]:
        """GET JSON with retry on transient network errors.

        Returns parsed JSON on success, None on any error.
        """
        try:
            timeout = kwargs.pop("timeout", _REQUEST_TIMEOUT)
            headers = kwargs.pop("headers", {})
            params = kwargs.pop("params", None)
            resp = requests.get(url, headers=headers, params=params, timeout=timeout, **kwargs)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("[%s] HTTP %s from %s", self.name, resp.status_code, url)
        except _TRANSIENT_EXCEPTIONS:
            raise  # let tenacity retry
        except Exception as e:
            logger.warning("[%s] Request error for %s: %s", self.name, url, e)
        return None

    @staticmethod
    def _safe(val) -> Optional[float]:
        """Convert value to float, returning None for None/NaN/Inf/invalid."""
        if val is None:
            return None
        try:
            f = float(val)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        except (TypeError, ValueError):
            return None
