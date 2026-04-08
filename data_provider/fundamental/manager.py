# -*- coding: utf-8 -*-
"""
FundamentalManager — orchestrates fundamental data fetchers with
priority-based failover and optional cache / circuit-breaker integration.
"""

import logging
from typing import List, Optional

from .base import BaseFundamentalFetcher
from .types import UnifiedFundamentalData

logger = logging.getLogger(__name__)


class FundamentalManager:
    """Orchestrates fundamental data fetchers with priority-based failover.

    Parameters
    ----------
    fetchers : list[BaseFundamentalFetcher] or None
        Provider fetchers ordered (or to be sorted) by ``priority``.
    cache : ProviderCache or None
        Optional persistent cache for storing / recovering results.
    circuit_breaker : CircuitBreaker or None
        Optional circuit breaker for skipping repeatedly failing providers.
    """

    def __init__(self, fetchers=None, cache=None, circuit_breaker=None):
        self._fetchers: List[BaseFundamentalFetcher] = sorted(
            fetchers or [], key=lambda f: f.priority
        )
        self._cache = cache
        self._cb = circuit_breaker

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls) -> "FundamentalManager":
        """Create with all configured fetchers, cache, and circuit breaker."""
        from .fmp_fetcher import FMPFundamentalFetcher
        from .finnhub_fetcher import FinnhubFundamentalFetcher
        from .alpha_vantage_fetcher import AlphaVantageFundamentalFetcher
        from .edgar_fetcher import EDGARFundamentalFetcher
        from data_provider.shared.cache import ProviderCache
        from data_provider.realtime_types import CircuitBreaker

        fetchers: List[BaseFundamentalFetcher] = [
            FMPFundamentalFetcher(),
            FinnhubFundamentalFetcher(),
            AlphaVantageFundamentalFetcher(),
            EDGARFundamentalFetcher(),
        ]
        cache = ProviderCache()
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=300.0)
        return cls(fetchers=fetchers, cache=cache, circuit_breaker=cb)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_fundamentals(self, stock_code: str) -> Optional[UnifiedFundamentalData]:
        """Fetch fundamental data with failover across providers.

        Returns ``UnifiedFundamentalData`` on success, ``None`` if every
        provider fails (including stale-cache fallback).
        """
        symbol = stock_code.upper()

        for fetcher in self._fetchers:
            # 1. Check fetcher availability
            if not fetcher.is_available():
                logger.debug("[FundamentalManager] %s unavailable, skipping", fetcher.name)
                continue

            # 2. Check circuit breaker
            if self._cb and not self._cb.is_available(fetcher.name):
                logger.debug("[FundamentalManager] %s circuit-broken, skipping", fetcher.name)
                continue

            # 3. Try fetching
            try:
                data = fetcher.get_fundamentals(stock_code)
            except Exception as exc:
                logger.warning(
                    "[FundamentalManager] %s raised %s: %s", fetcher.name, type(exc).__name__, exc
                )
                if self._cb:
                    self._cb.record_failure(fetcher.name, str(exc))
                continue

            if data is None:
                # Inconclusive — provider returned nothing
                logger.debug("[FundamentalManager] %s returned None for %s", fetcher.name, symbol)
                if self._cb:
                    self._cb.record_inconclusive(fetcher.name)
                continue

            # 4. Success path
            logger.info("[FundamentalManager] %s returned data for %s", fetcher.name, symbol)
            if self._cb:
                self._cb.record_success(fetcher.name)
            self._cache_put(symbol, data)
            return data

        # 5. All fetchers exhausted — try stale cache as last resort
        logger.warning("[FundamentalManager] all providers failed for %s, trying stale cache", symbol)
        stale = self._cache_get_stale(symbol)
        if stale is not None:
            logger.info("[FundamentalManager] returning stale cache entry for %s", symbol)
            return stale

        logger.warning("[FundamentalManager] no data available for %s", symbol)
        return None

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_put(self, symbol: str, data: UnifiedFundamentalData) -> None:
        if self._cache is None:
            return
        try:
            meta = {}
            if data.earnings_date:
                meta["next_earnings"] = data.earnings_date
            self._cache.put(
                f"fund:{symbol}:latest",
                data.to_dict(),
                provider=data.source,
                meta=meta or None,
            )
        except Exception as exc:
            logger.warning("[FundamentalManager] cache put failed: %s", exc)

    def _cache_get_stale(self, symbol: str) -> Optional[UnifiedFundamentalData]:
        if self._cache is None:
            return None
        try:
            entry = self._cache.get_stale(f"fund:{symbol}:latest")
            if entry is None:
                return None
            raw = entry.get("data", {})
            return UnifiedFundamentalData(**raw)
        except Exception as exc:
            logger.warning("[FundamentalManager] stale cache read failed: %s", exc)
            return None
