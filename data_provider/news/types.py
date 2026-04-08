# -*- coding: utf-8 -*-
"""
Unified news item type for US stock analysis.

All news provider fetchers normalize their output into UnifiedNewsItem,
enabling seamless dedup, scoring, and merge across providers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class NewsEventType(Enum):
    """Classification of news events."""

    EARNINGS = "earnings"
    ANALYST_RATING = "analyst_rating"
    SEC_FILING = "sec_filing"
    INSIDER = "insider"
    M_AND_A = "m_and_a"
    GENERAL = "general"


@dataclass
class UnifiedNewsItem:
    """Normalized news item from any provider.

    Required fields: title, url, published_at, source_name, tickers, event_type.
    Optional fields default to None or 0.0.
    """

    title: str
    url: str
    published_at: datetime
    source_name: str              # "finnhub", "fmp", "edgar", "tavily"
    tickers: List[str]            # Related tickers ["AAPL", "MSFT"]
    event_type: NewsEventType
    sentiment: Optional[float] = None    # -1.0 to 1.0
    summary: Optional[str] = None
    body: Optional[str] = None
    relevance_score: float = 0.0  # 0-1, computed by NewsManager

    def to_dict(self) -> dict:
        """Return dict with all fields, event_type as its string value."""
        return {
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at,
            "source_name": self.source_name,
            "tickers": self.tickers,
            "event_type": self.event_type.value,
            "sentiment": self.sentiment,
            "summary": self.summary,
            "body": self.body,
            "relevance_score": self.relevance_score,
        }
