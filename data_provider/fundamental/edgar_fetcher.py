# -*- coding: utf-8 -*-
"""
SEC EDGAR fundamental data fetcher.

Last resort provider, priority 3. Free, no API key required. 10 req/sec.
Uses the SEC EDGAR company-facts XBRL API to extract key financial metrics.

Requires User-Agent header with email (SEC policy).
Read from SEC_EDGAR_USER_AGENT env var; falls back to a default.

This is the most complex fetcher due to XBRL data parsing.
Focus: EPS, revenue, net income margin. Other fields may be None.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import requests

from .base import BaseFundamentalFetcher
from .types import UnifiedFundamentalData

logger = logging.getLogger(__name__)

_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

_DEFAULT_USER_AGENT = "DSA-StockAnalysis/1.0 (contact@example.com)"


class EDGARFundamentalFetcher(BaseFundamentalFetcher):
    """SEC EDGAR fundamental data fetcher (priority 3).

    Free, no API key required. Uses XBRL company-facts to extract
    EPS, revenue, and net income margin.
    """

    name = "edgar"
    priority = 3

    def __init__(self) -> None:
        self._user_agent = (
            os.environ.get("SEC_EDGAR_USER_AGENT", "").strip()
            or _DEFAULT_USER_AGENT
        )
        # Cache of ticker -> CIK mapping
        self._ticker_cik_map: Optional[Dict[str, str]] = None

    def is_available(self) -> bool:
        # EDGAR is always available (no API key needed)
        return True

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self._user_agent,
            "Accept": "application/json",
        }

    def _load_ticker_cik_map(self) -> Dict[str, str]:
        """Load the ticker-to-CIK mapping from SEC."""
        if self._ticker_cik_map is not None:
            return self._ticker_cik_map

        try:
            resp = requests.get(
                _COMPANY_TICKERS_URL,
                headers=self._headers,
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning("[edgar] Failed to load ticker map: HTTP %s", resp.status_code)
                return {}

            data = resp.json()
            mapping = {}
            for entry in data.values():
                ticker = (entry.get("ticker") or "").upper()
                cik = entry.get("cik_str")
                if ticker and cik:
                    mapping[ticker] = str(cik).zfill(10)
            self._ticker_cik_map = mapping
            logger.debug("[edgar] Loaded %d ticker-CIK mappings", len(mapping))
            return mapping
        except Exception as e:
            logger.warning("[edgar] Error loading ticker map: %s", e)
            return {}

    def _get_company_facts(self, cik: str) -> Optional[Dict]:
        """Fetch company facts XBRL data from SEC EDGAR."""
        url = _COMPANY_FACTS_URL.format(cik=cik)
        try:
            resp = requests.get(url, headers=self._headers, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("[edgar] HTTP %s for CIK %s", resp.status_code, cik)
        except Exception as e:
            logger.warning("[edgar] Error fetching company facts for CIK %s: %s", cik, e)
        return None

    @staticmethod
    def _extract_latest_value(
        facts: Dict,
        taxonomy: str,
        concept: str,
        unit_key: str = "USD",
    ) -> Optional[float]:
        """Extract the latest reported value for a given XBRL concept.

        Args:
            facts: The full company-facts JSON.
            taxonomy: e.g. "us-gaap" or "dei"
            concept: e.g. "EarningsPerShareBasic"
            unit_key: e.g. "USD", "USD/shares", "pure"

        Returns:
            Latest value as float, or None.
        """
        try:
            concept_data = facts.get("facts", {}).get(taxonomy, {}).get(concept, {})
            units = concept_data.get("units", {})
            entries: List[Dict[str, Any]] = units.get(unit_key, [])
            if not entries:
                return None

            # Sort by end date descending, prefer 10-K/10-Q filings
            sorted_entries = sorted(
                entries,
                key=lambda e: e.get("end", ""),
                reverse=True,
            )

            for entry in sorted_entries:
                val = entry.get("val")
                if val is not None:
                    return float(val)
        except Exception as e:
            logger.debug("[edgar] Error extracting %s/%s: %s", taxonomy, concept, e)
        return None

    def get_fundamentals(self, stock_code: str) -> Optional[UnifiedFundamentalData]:
        symbol = stock_code.strip().upper()

        # Resolve ticker to CIK
        ticker_map = self._load_ticker_cik_map()
        cik = ticker_map.get(symbol)
        if not cik:
            logger.debug("[edgar] No CIK found for %s", symbol)
            return None

        # Fetch company facts
        facts = self._get_company_facts(cik)
        if not facts:
            return None

        # Extract key metrics from XBRL data
        # EPS (basic, diluted)
        eps_basic = self._extract_latest_value(facts, "us-gaap", "EarningsPerShareBasic", "USD/shares")
        eps_diluted = self._extract_latest_value(facts, "us-gaap", "EarningsPerShareDiluted", "USD/shares")
        eps_ttm = eps_diluted if eps_diluted is not None else eps_basic

        # Revenue
        revenue = self._extract_latest_value(facts, "us-gaap", "Revenues", "USD")
        if revenue is None:
            revenue = self._extract_latest_value(facts, "us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD")
        if revenue is None:
            revenue = self._extract_latest_value(facts, "us-gaap", "SalesRevenueNet", "USD")

        # Net income
        net_income = self._extract_latest_value(facts, "us-gaap", "NetIncomeLoss", "USD")

        # Net income margin
        profit_margin = None
        if net_income is not None and revenue is not None and revenue != 0:
            profit_margin = net_income / revenue

        # ROE = net_income / stockholders_equity
        stockholders_equity = self._extract_latest_value(facts, "us-gaap", "StockholdersEquity", "USD")
        roe = None
        if net_income is not None and stockholders_equity is not None and stockholders_equity != 0:
            roe = net_income / stockholders_equity

        # ROA = net_income / total_assets
        total_assets = self._extract_latest_value(facts, "us-gaap", "Assets", "USD")
        roa = None
        if net_income is not None and total_assets is not None and total_assets != 0:
            roa = net_income / total_assets

        # If we got nothing useful, return None
        if all(v is None for v in [eps_ttm, revenue, profit_margin]):
            logger.warning("[edgar] No useful financial data for %s", symbol)
            return None

        return UnifiedFundamentalData(
            code=symbol,
            source="edgar",
            eps_ttm=self._safe(eps_ttm),
            revenue_ttm=self._safe(revenue),
            profit_margin=self._safe(profit_margin),
            roe=self._safe(roe),
            roa=self._safe(roa),
        )
