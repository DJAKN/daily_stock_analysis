# -*- coding: utf-8 -*-
"""
FMP (Financial Modeling Prep) fundamental data fetcher.

Primary provider, priority 0. Free tier: 250 req/day.
Base URL: https://financialmodelingprep.com/api/v3

Endpoints used:
- /ratios-ttm/{symbol}       — valuation, margins, ROE/ROA, balance sheet, dividends
- /earnings-surprises/{symbol} — EPS actual/estimate, earnings date, surprise %
- /insider-trading?symbol=    — insider buy/sell activity (last 90 days)
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from .base import BaseFundamentalFetcher
from .types import UnifiedFundamentalData

logger = logging.getLogger(__name__)

_BASE_URL = "https://financialmodelingprep.com/api/v3"


class FMPFundamentalFetcher(BaseFundamentalFetcher):
    """FMP fundamental data fetcher (priority 0)."""

    name = "fmp"
    priority = 0

    def __init__(self) -> None:
        self._api_key = os.environ.get("FMP_API_KEY", "").strip() or None

    def is_available(self) -> bool:
        return self._api_key is not None

    def get_fundamentals(self, stock_code: str) -> Optional[UnifiedFundamentalData]:
        if not self.is_available():
            logger.debug("[fmp] API key not configured, skipping")
            return None

        symbol = stock_code.strip().upper()

        # 1. Ratios TTM — primary data source
        ratios_url = f"{_BASE_URL}/ratios-ttm/{symbol}?apikey={self._api_key}"
        ratios_data = self._get_json(ratios_url)

        # 2. Earnings surprises
        earnings_url = f"{_BASE_URL}/earnings-surprises/{symbol}?apikey={self._api_key}"
        earnings_data = self._get_json(earnings_url)

        # 3. Insider trading (last 90 days)
        insider_url = f"{_BASE_URL}/insider-trading?symbol={symbol}&apikey={self._api_key}"
        insider_data = self._get_json(insider_url)

        # If all endpoints failed, return None
        has_ratios = isinstance(ratios_data, list) and len(ratios_data) > 0
        has_earnings = isinstance(earnings_data, list) and len(earnings_data) > 0
        has_insider = isinstance(insider_data, list) and len(insider_data) > 0

        if not has_ratios and not has_earnings and not has_insider:
            logger.warning("[fmp] All endpoints returned no data for %s", symbol)
            return None

        # Parse ratios
        pe_ratio = None
        pb_ratio = None
        ps_ratio = None
        peg_ratio = None
        ev_ebitda = None
        profit_margin = None
        operating_margin = None
        roe = None
        roa = None
        debt_to_equity = None
        current_ratio = None
        dividend_yield = None
        payout_ratio = None
        free_cash_flow = None

        if has_ratios:
            r = ratios_data[0]
            pe_ratio = self._safe(r.get("peRatioTTM"))
            pb_ratio = self._safe(r.get("priceToBookRatioTTM"))
            ps_ratio = self._safe(r.get("priceToSalesRatioTTM"))
            peg_ratio = self._safe(r.get("pegRatioTTM"))
            ev_ebitda = self._safe(r.get("enterpriseValueOverEBITDATTM"))
            profit_margin = self._safe(r.get("netProfitMarginTTM"))
            operating_margin = self._safe(r.get("operatingProfitMarginTTM"))
            roe = self._safe(r.get("returnOnEquityTTM"))
            roa = self._safe(r.get("returnOnAssetsTTM"))
            debt_to_equity = self._safe(r.get("debtToEquityTTM"))
            current_ratio = self._safe(r.get("currentRatioTTM"))
            dividend_yield = self._safe(r.get("dividendYieldTTM"))
            payout_ratio = self._safe(r.get("payoutRatioTTM"))
            fcf_per_share = self._safe(r.get("freeCashFlowPerShareTTM"))
            if fcf_per_share is not None:
                free_cash_flow = fcf_per_share  # store per-share value

        # Parse earnings
        eps_ttm = None
        eps_estimate = None
        earnings_date = None
        earnings_surprise = None

        if has_earnings:
            latest = earnings_data[0]
            eps_ttm = self._safe(latest.get("actualEarningResult"))
            eps_estimate = self._safe(latest.get("estimatedEarning"))
            earnings_date = latest.get("date")
            # Calculate surprise % if both actual and estimate available
            if eps_ttm is not None and eps_estimate is not None and eps_estimate != 0:
                earnings_surprise = self._safe(
                    ((eps_ttm - eps_estimate) / abs(eps_estimate)) * 100
                )

        # Parse insider trading (count buys/sells in last 90 days)
        insider_buy_count = None
        insider_sell_count = None

        if has_insider:
            cutoff = datetime.now() - timedelta(days=90)
            buys = 0
            sells = 0
            for trade in insider_data:
                tx_type = (trade.get("transactionType") or "").upper()
                tx_date_str = trade.get("transactionDate", "")
                try:
                    tx_date = datetime.strptime(tx_date_str, "%Y-%m-%d")
                    if tx_date < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass  # include if date can't be parsed
                if "PURCHASE" in tx_type or tx_type.startswith("P"):
                    buys += 1
                elif "SALE" in tx_type or tx_type.startswith("S"):
                    sells += 1
            insider_buy_count = buys
            insider_sell_count = sells

        return UnifiedFundamentalData(
            code=symbol,
            source="fmp",
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
            eps_estimate=eps_estimate,
            earnings_date=earnings_date,
            earnings_surprise=earnings_surprise,
            insider_buy_count_90d=insider_buy_count,
            insider_sell_count_90d=insider_sell_count,
        )
