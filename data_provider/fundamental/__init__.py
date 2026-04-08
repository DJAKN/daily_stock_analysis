# -*- coding: utf-8 -*-
"""
Fundamental data provider package.

Provides unified fundamental data types and multi-provider fetchers
for US stock market data (FMP, Finnhub, Alpha Vantage, SEC EDGAR).
"""

from .types import UnifiedFundamentalData
from .base import BaseFundamentalFetcher
from .manager import FundamentalManager

__all__ = ["UnifiedFundamentalData", "BaseFundamentalFetcher", "FundamentalManager"]
