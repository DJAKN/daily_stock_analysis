# -*- coding: utf-8 -*-
"""
Abstract base classes for macro data fetchers.

Two separate ABCs because macro data has two distinct fetch patterns:
- Indicator fetchers: retrieve current values of economic indicators
- Calendar fetchers: retrieve upcoming economic events
"""

import logging
import math
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .types import MacroIndicator, EconEvent

logger = logging.getLogger(__name__)

_TRANSIENT_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)

_REQUEST_TIMEOUT = 10  # seconds


class BaseMacroIndicatorFetcher(ABC):
    """Abstract base for macro indicator fetchers (e.g., FRED).

    Subclasses must define:
        name: str — provider identifier (e.g. "fred")

    And implement:
        get_indicators() -> Dict[str, MacroIndicator]
        is_available() -> bool
    """

    name: str = ""

    @abstractmethod
    def get_indicators(self) -> Dict[str, MacroIndicator]:
        """Fetch current macro indicator readings.

        Returns dict keyed by indicator name (e.g. "fed_funds_rate").
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
            resp = requests.get(
                url, headers=headers, params=params, timeout=timeout, **kwargs
            )
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


class BaseMacroCalendarFetcher(ABC):
    """Abstract base for economic calendar fetchers (e.g., Finnhub).

    Subclasses must define:
        name: str — provider identifier (e.g. "finnhub")

    And implement:
        get_economic_calendar(days_ahead) -> List[EconEvent]
        is_available() -> bool
    """

    name: str = ""

    @abstractmethod
    def get_economic_calendar(self, days_ahead: int = 14) -> List[EconEvent]:
        """Fetch upcoming economic calendar events.

        Args:
            days_ahead: How many days into the future to look.

        Returns list of EconEvent, empty list on failure.
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
        """GET JSON with retry on transient network errors."""
        try:
            timeout = kwargs.pop("timeout", _REQUEST_TIMEOUT)
            headers = kwargs.pop("headers", {})
            params = kwargs.pop("params", None)
            resp = requests.get(
                url, headers=headers, params=params, timeout=timeout, **kwargs
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning("[%s] HTTP %s from %s", self.name, resp.status_code, url)
        except _TRANSIENT_EXCEPTIONS:
            raise  # let tenacity retry
        except Exception as e:
            logger.warning("[%s] Request error for %s: %s", self.name, url, e)
        return None
