# -*- coding: utf-8 -*-
"""
News data provider package.

Provides unified news item types and multi-provider fetchers
for US stock market news (Finnhub, FMP, SEC EDGAR, search adapter).
"""

from .types import UnifiedNewsItem, NewsEventType
from .base import BaseNewsFetcher

__all__ = ["UnifiedNewsItem", "NewsEventType", "BaseNewsFetcher"]
