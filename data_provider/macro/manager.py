# -*- coding: utf-8 -*-
"""
MacroManager -- orchestrates macro indicator and calendar fetchers.

Called once per daily run. The resulting UnifiedMacroSnapshot is shared
across all stock analyses in the same run.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .base import BaseMacroIndicatorFetcher, BaseMacroCalendarFetcher
from .types import EconEvent, MacroIndicator, UnifiedMacroSnapshot

logger = logging.getLogger(__name__)


class MacroManager:
    """Aggregate multiple macro data sources into a single snapshot.

    Parameters
    ----------
    indicator_fetchers : list of BaseMacroIndicatorFetcher
        Providers that return macro indicator readings (e.g. FRED).
    calendar_fetchers : list of BaseMacroCalendarFetcher
        Providers that return upcoming economic events (e.g. Finnhub).
    cache : ProviderCache or None
        Optional persistent cache (currently unused, reserved for FRED caching).
    """

    def __init__(
        self,
        indicator_fetchers: Optional[List[BaseMacroIndicatorFetcher]] = None,
        calendar_fetchers: Optional[List[BaseMacroCalendarFetcher]] = None,
        cache=None,
    ) -> None:
        self._indicator_fetchers = indicator_fetchers or []
        self._calendar_fetchers = calendar_fetchers or []
        self._cache = cache  # Optional[ProviderCache]

    @classmethod
    def from_config(cls) -> "MacroManager":
        """Instantiate MacroManager with default fetchers based on env config.

        Creates a FRED indicator fetcher and Finnhub calendar fetcher.
        Fetchers that are not configured (missing API keys) will still
        be included but will gracefully return empty results.
        """
        from .fred_fetcher import FREDMacroFetcher
        from .finnhub_fetcher import FinnhubCalendarFetcher

        indicator_fetchers: List[BaseMacroIndicatorFetcher] = [FREDMacroFetcher()]
        calendar_fetchers: List[BaseMacroCalendarFetcher] = [FinnhubCalendarFetcher()]

        return cls(
            indicator_fetchers=indicator_fetchers,
            calendar_fetchers=calendar_fetchers,
        )

    def get_snapshot(self) -> Optional[UnifiedMacroSnapshot]:
        """Fetch macro indicators and economic calendar.

        Returns None if all fetchers fail or return empty data.

        Logic:
        1. Query all indicator fetchers, merge results (first non-None wins per key).
        2. Query all calendar fetchers, combine event lists.
        3. Compute market_regime from indicators.
        4. Return UnifiedMacroSnapshot, or None if everything is empty.
        """
        indicators = self._collect_indicators()
        events = self._collect_events()

        if not indicators and not events:
            logger.warning("[MacroManager] All fetchers returned empty data")
            return None

        market_regime = self._compute_market_regime(indicators)

        snapshot = UnifiedMacroSnapshot(
            timestamp=datetime.now(timezone.utc),
            indicators=indicators,
            upcoming_events=events,
            market_regime=market_regime,
        )

        logger.info(
            "[MacroManager] Snapshot: %d indicators, %d events, regime=%s",
            len(indicators),
            len(events),
            market_regime,
        )
        return snapshot

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_indicators(self) -> Dict[str, MacroIndicator]:
        """Query all indicator fetchers and merge. First non-None wins per key."""
        merged: Dict[str, MacroIndicator] = {}

        for fetcher in self._indicator_fetchers:
            try:
                result = fetcher.get_indicators()
                if not result:
                    continue
                for key, indicator in result.items():
                    if key not in merged:
                        merged[key] = indicator
            except Exception as e:
                fetcher_name = getattr(fetcher, "name", type(fetcher).__name__)
                logger.warning(
                    "[MacroManager] Indicator fetcher '%s' failed: %s",
                    fetcher_name,
                    e,
                )

        return merged

    def _collect_events(self) -> List[EconEvent]:
        """Query all calendar fetchers and combine event lists."""
        all_events: List[EconEvent] = []

        for fetcher in self._calendar_fetchers:
            try:
                events = fetcher.get_economic_calendar()
                if events:
                    all_events.extend(events)
            except Exception as e:
                fetcher_name = getattr(fetcher, "name", type(fetcher).__name__)
                logger.warning(
                    "[MacroManager] Calendar fetcher '%s' failed: %s",
                    fetcher_name,
                    e,
                )

        return all_events

    @staticmethod
    def _compute_market_regime(indicators: Dict[str, MacroIndicator]) -> str:
        """Derive market regime label from indicator values.

        Rules:
        - If VIX > 25 OR yield_spread < 0 -> "risk_off"
        - If VIX < 15 AND yield_spread > 0.5 -> "risk_on"
        - Otherwise -> "neutral"
        """
        vix_indicator = indicators.get("vix")
        spread_indicator = indicators.get("yield_spread")

        vix_value = vix_indicator.value if vix_indicator else None
        spread_value = spread_indicator.value if spread_indicator else None

        # Risk-off check
        if vix_value is not None and vix_value > 25:
            return "risk_off"
        if spread_value is not None and spread_value < 0:
            return "risk_off"

        # Risk-on check (both conditions must be met)
        if (
            vix_value is not None
            and spread_value is not None
            and vix_value < 15
            and spread_value > 0.5
        ):
            return "risk_on"

        return "neutral"
