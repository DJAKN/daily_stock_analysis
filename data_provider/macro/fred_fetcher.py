# -*- coding: utf-8 -*-
"""
FRED macro indicator fetcher.

Primary indicator provider. Free tier: 120 req/min.
Base URL: https://api.stlouisfed.org/fred

Fetches latest observations for pre-configured economic series
(fed funds rate, CPI, treasuries, unemployment, VIX, etc.)
and normalizes them into MacroIndicator instances.
"""

import logging
import os
from typing import Dict

from .base import BaseMacroIndicatorFetcher
from .types import MacroIndicator

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.stlouisfed.org/fred"

# (series_id, display_name, unit)
MACRO_SERIES = {
    "fed_funds_rate": ("FEDFUNDS", "Federal Funds Rate", "%"),
    "cpi_yoy": ("CPIAUCSL", "CPI All Urban", "%"),
    "core_cpi_yoy": ("CPILFESL", "Core CPI", "%"),
    "pce_yoy": ("PCEPI", "PCE Price Index", "%"),
    "ppi_yoy": ("PPIACO", "Producer Price Index", "%"),
    "treasury_2y": ("DGS2", "2-Year Treasury", "%"),
    "treasury_10y": ("DGS10", "10-Year Treasury", "%"),
    "treasury_30y": ("DGS30", "30-Year Treasury", "%"),
    "yield_spread": ("T10Y2Y", "10Y-2Y Spread", "%"),
    "unemployment": ("UNRATE", "Unemployment Rate", "%"),
    "nonfarm_payrolls": ("PAYEMS", "Nonfarm Payrolls", "thousands"),
    "vix": ("VIXCLS", "CBOE VIX", "index"),
}


class FREDMacroFetcher(BaseMacroIndicatorFetcher):
    """FRED macro indicator fetcher (primary provider)."""

    name = "fred"

    def __init__(self) -> None:
        self._api_key = os.environ.get("FRED_API_KEY", "").strip() or None

    def is_available(self) -> bool:
        return self._api_key is not None

    def get_indicators(self) -> Dict[str, MacroIndicator]:
        """Fetch latest observations for all configured FRED series.

        Returns dict keyed by indicator name. Individual series failures
        are logged and skipped without failing the whole batch.
        """
        if not self.is_available():
            logger.debug("[fred] API key not configured, skipping")
            return {}

        results: Dict[str, MacroIndicator] = {}

        for indicator_name, (series_id, display_name, unit) in MACRO_SERIES.items():
            try:
                indicator = self._fetch_series(
                    indicator_name, series_id, display_name, unit
                )
                if indicator is not None:
                    results[indicator_name] = indicator
            except Exception as e:
                logger.warning(
                    "[fred] Failed to fetch %s (%s): %s",
                    indicator_name,
                    series_id,
                    e,
                )
                continue

        return results

    def _fetch_series(
        self,
        indicator_name: str,
        series_id: str,
        display_name: str,
        unit: str,
    ) -> MacroIndicator | None:
        """Fetch latest 2 observations for a single FRED series.

        Returns MacroIndicator on success, None on failure or missing data.
        """
        url = f"{_BASE_URL}/series/observations"
        params = {
            "series_id": series_id,
            "api_key": self._api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 2,
        }

        data = self._get_json(url, params=params)
        if not data or not isinstance(data, dict):
            return None

        observations = data.get("observations", [])
        if not observations:
            return None

        # Parse current value (first observation, most recent due to desc sort)
        current_obs = observations[0]
        current_val_str = current_obs.get("value", "")
        current_val = self._safe(current_val_str)

        # FRED uses "." for missing/unavailable values
        if current_val is None:
            return None

        as_of_date = current_obs.get("date", "")

        # Parse previous value (second observation, if available)
        previous_value = None
        change = None
        if len(observations) >= 2:
            prev_obs = observations[1]
            prev_val_str = prev_obs.get("value", "")
            previous_value = self._safe(prev_val_str)
            if previous_value is not None:
                change = round(current_val - previous_value, 4)

        return MacroIndicator(
            name=indicator_name,
            display_name=display_name,
            value=current_val,
            previous_value=previous_value,
            change=change,
            unit=unit,
            as_of_date=as_of_date,
            source="fred",
        )
