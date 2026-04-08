# -*- coding: utf-8 -*-
"""
Finnhub fundamental data fetcher.

Secondary provider, priority 1. Free tier: 60 req/min.
Base URL: https://finnhub.io/api/v1

Endpoints used:
- /stock/metric?symbol={symbol}&metric=all — key financial metrics
- /stock/insider-sentiment?symbol={symbol} — insider buy/sell activity
"""

import logging
import os
from typing import Optional

from .base import BaseFundamentalFetcher
from .types import UnifiedFundamentalData

logger = logging.getLogger(__name__)

_BASE_URL = "https://finnhub.io/api/v1"


class FinnhubFundamentalFetcher(BaseFundamentalFetcher):
    """Finnhub fundamental data fetcher (priority 1)."""

    name = "finnhub"
    priority = 1

    def __init__(self) -> None:
        self._api_key = os.environ.get("FINNHUB_API_KEY", "").strip() or None

    def is_available(self) -> bool:
        return self._api_key is not None

    def get_fundamentals(self, stock_code: str) -> Optional[UnifiedFundamentalData]:
        if not self.is_available():
            logger.debug("[finnhub] API key not configured, skipping")
            return None

        symbol = stock_code.strip().upper()

        # 1. Basic metrics
        metric_url = f"{_BASE_URL}/stock/metric?symbol={symbol}&metric=all&token={self._api_key}"
        metric_data = self._get_json(metric_url)

        # 2. Insider sentiment
        insider_url = f"{_BASE_URL}/stock/insider-sentiment?symbol={symbol}&token={self._api_key}"
        insider_data = self._get_json(insider_url)

        # Parse metrics
        metrics = {}
        if isinstance(metric_data, dict):
            metrics = metric_data.get("metric", {}) or {}

        if not metrics:
            logger.warning("[finnhub] No metric data for %s", symbol)
            return None

        pe_ratio = self._safe(metrics.get("peTTM"))
        pb_ratio = self._safe(metrics.get("pbQuarterly"))
        ps_ratio = self._safe(metrics.get("psAnnual") or metrics.get("psTTM"))
        peg_ratio = self._safe(metrics.get("pegRatio"))
        ev_ebitda = self._safe(metrics.get("currentEv/freeCashFlowTTM"))
        profit_margin = self._safe(metrics.get("netProfitMarginTTM"))
        operating_margin = self._safe(metrics.get("operatingMarginTTM"))
        roe = self._safe(metrics.get("roeTTM"))
        roa = self._safe(metrics.get("roaTTM"))
        debt_to_equity = self._safe(metrics.get("totalDebt/totalEquityQuarterly"))
        current_ratio = self._safe(metrics.get("currentRatioQuarterly"))
        dividend_yield = self._safe(metrics.get("dividendYieldIndicatedAnnual"))
        payout_ratio = self._safe(metrics.get("payoutRatioAnnual"))
        free_cash_flow = self._safe(metrics.get("freeCashFlowTTM"))
        eps_ttm = self._safe(metrics.get("epsBasicExclExtraItemsTTM") or metrics.get("epsInclExtraItemsTTM"))
        revenue_ttm = self._safe(metrics.get("revenuePerShareTTM"))

        # Parse insider sentiment
        insider_buy_count = None
        insider_sell_count = None

        if isinstance(insider_data, dict):
            entries = insider_data.get("data", [])
            if isinstance(entries, list) and entries:
                buys = 0
                sells = 0
                for entry in entries:
                    change = entry.get("change", 0)
                    if isinstance(change, (int, float)):
                        if change > 0:
                            buys += 1
                        elif change < 0:
                            sells += 1
                insider_buy_count = buys
                insider_sell_count = sells

        return UnifiedFundamentalData(
            code=symbol,
            source="finnhub",
            pe_ratio=pe_ratio,
            pb_ratio=pb_ratio,
            ps_ratio=ps_ratio,
            peg_ratio=peg_ratio,
            ev_ebitda=ev_ebitda,
            profit_margin=profit_margin,
            operating_margin=operating_margin,
            roe=roe,
            roa=roa,
            debt_to_equity=debt_to_equity,
            current_ratio=current_ratio,
            dividend_yield=dividend_yield,
            payout_ratio=payout_ratio,
            free_cash_flow=free_cash_flow,
            eps_ttm=eps_ttm,
            revenue_ttm=revenue_ttm,
            insider_buy_count_90d=insider_buy_count,
            insider_sell_count_90d=insider_sell_count,
        )
