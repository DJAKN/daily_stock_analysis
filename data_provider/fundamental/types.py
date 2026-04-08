# -*- coding: utf-8 -*-
"""
Unified fundamental data type for US stock analysis.

All provider fetchers normalize their output into this dataclass,
enabling seamless merge and failover across providers.
"""

from dataclasses import dataclass, fields
from typing import Optional


@dataclass
class UnifiedFundamentalData:
    """Normalized fundamental data for a single stock ticker.

    Required fields: code, source.
    All metric fields default to None and are filled by provider fetchers.
    """

    code: str
    source: str

    # Valuation (fetch fresh daily — price-dependent)
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    peg_ratio: Optional[float] = None
    ev_ebitda: Optional[float] = None

    # Earnings
    eps_ttm: Optional[float] = None
    eps_estimate: Optional[float] = None
    revenue_ttm: Optional[float] = None
    earnings_date: Optional[str] = None
    earnings_surprise: Optional[float] = None

    # Profitability (cacheable — quarterly filings)
    profit_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None

    # Balance Sheet (cacheable — quarterly filings)
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    free_cash_flow: Optional[float] = None

    # Dividends
    dividend_yield: Optional[float] = None
    payout_ratio: Optional[float] = None

    # Ownership Signals (fetch fresh daily)
    insider_buy_count_90d: Optional[int] = None
    insider_sell_count_90d: Optional[int] = None
    institutional_ownership_pct: Optional[float] = None
    short_interest_pct: Optional[float] = None

    def to_dict(self) -> dict:
        """Return dict with code, source, and all non-None metric fields."""
        result = {}
        for f in fields(self):
            val = getattr(self, f.name)
            if val is not None:
                result[f.name] = val
        return result

    def has_valuation_data(self) -> bool:
        """True if any of pe_ratio, forward_pe, pb_ratio, ev_ebitda is non-None."""
        return any(
            getattr(self, f) is not None
            for f in ("pe_ratio", "forward_pe", "pb_ratio", "ev_ebitda")
        )

    def merge(self, other: "UnifiedFundamentalData") -> "UnifiedFundamentalData":
        """Return new instance: self's non-None values take priority, other fills gaps.

        The returned instance keeps self's code and source.
        """
        merged_kwargs = {}
        for f in fields(self):
            self_val = getattr(self, f.name)
            other_val = getattr(other, f.name)
            if f.name in ("code", "source"):
                merged_kwargs[f.name] = self_val
            else:
                merged_kwargs[f.name] = self_val if self_val is not None else other_val
        return UnifiedFundamentalData(**merged_kwargs)
