# -*- coding: utf-8 -*-
"""
Alpha Vantage fundamental data fetcher.

Fallback provider, priority 2. Free tier: 25 req/day.
Base URL: https://www.alphavantage.co/query

Endpoints used:
- ?function=OVERVIEW&symbol={symbol} — company overview with valuation,
  EPS, revenue, margins, ROE, ROA, dividend yield

Note: Alpha Vantage does NOT provide insider/institutional data.
"""

import logging
import os
from typing import Optional

from .base import BaseFundamentalFetcher
from .types import UnifiedFundamentalData

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageFundamentalFetcher(BaseFundamentalFetcher):
    """Alpha Vantage fundamental data fetcher (priority 2)."""

    name = "alpha_vantage"
    priority = 2

    def __init__(self) -> None:
        self._api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip() or None

    def is_available(self) -> bool:
        return self._api_key is not None

    def get_fundamentals(self, stock_code: str) -> Optional[UnifiedFundamentalData]:
        if not self.is_available():
            logger.debug("[alpha_vantage] API key not configured, skipping")
            return None

        symbol = stock_code.strip().upper()

        url = f"{_BASE_URL}?function=OVERVIEW&symbol={symbol}&apikey={self._api_key}"
        data = self._get_json(url)

        if not isinstance(data, dict) or not data:
            logger.warning("[alpha_vantage] No data for %s", symbol)
            return None

        # Alpha Vantage returns an error message for invalid symbols
        if "Error Message" in data or "Note" in data:
            logger.warning("[alpha_vantage] API error for %s: %s",
                           symbol, data.get("Error Message") or data.get("Note"))
            return None

        # Check if the response has actual data (Symbol field present)
        if "Symbol" not in data:
            logger.warning("[alpha_vantage] Empty response for %s", symbol)
            return None

        pe_ratio = self._safe(data.get("TrailingPE"))
        forward_pe = self._safe(data.get("ForwardPE"))
        pb_ratio = self._safe(data.get("PriceToBookRatio"))
        ps_ratio = self._safe(data.get("PriceToSalesRatioTTM"))
        peg_ratio = self._safe(data.get("PEGRatio"))
        ev_ebitda = self._safe(data.get("EVToEBITDA"))
        eps_ttm = self._safe(data.get("EPS"))
        revenue_ttm = self._safe(data.get("RevenueTTM"))
        profit_margin = self._safe(data.get("ProfitMargin"))
        operating_margin = self._safe(data.get("OperatingMarginTTM"))
        roe = self._safe(data.get("ReturnOnEquityTTM"))
        roa = self._safe(data.get("ReturnOnAssetsTTM"))
        dividend_yield = self._safe(data.get("DividendYield"))
        payout_ratio = self._safe(data.get("PayoutRatio"))
        debt_to_equity = self._safe(data.get("DebtToEquityRatio"))  # not always available

        return UnifiedFundamentalData(
            code=symbol,
            source="alpha_vantage",
            pe_ratio=pe_ratio,
            forward_pe=forward_pe,
            pb_ratio=pb_ratio,
            ps_ratio=ps_ratio,
            peg_ratio=peg_ratio,
            ev_ebitda=ev_ebitda,
            eps_ttm=eps_ttm,
            revenue_ttm=revenue_ttm,
            profit_margin=profit_margin,
            operating_margin=operating_margin,
            roe=roe,
            roa=roa,
            dividend_yield=dividend_yield,
            payout_ratio=payout_ratio,
            debt_to_equity=debt_to_equity,
        )
