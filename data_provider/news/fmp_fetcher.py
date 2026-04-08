# -*- coding: utf-8 -*-
"""
FMP (Financial Modeling Prep) news fetcher.

Secondary provider, priority 1. Free tier: 250 req/day.
Base URL: https://financialmodelingprep.com/api/v3

Endpoints used:
- /stock_news?tickers={symbol}&limit=50 -- stock news articles
"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from .base import BaseNewsFetcher
from .types import NewsEventType, UnifiedNewsItem

logger = logging.getLogger(__name__)

_BASE_URL = "https://financialmodelingprep.com/api/v3"


class FMPNewsFetcher(BaseNewsFetcher):
    """FMP news fetcher (priority 1)."""

    name = "fmp"
    priority = 1

    def __init__(self) -> None:
        self._api_key = os.environ.get("FMP_API_KEY", "").strip() or None

    def is_available(self) -> bool:
        return self._api_key is not None

    def get_news(self, stock_code: str, days: int = 7) -> List[UnifiedNewsItem]:
        if not self.is_available():
            logger.debug("[fmp] API key not configured, skipping news")
            return []

        symbol = stock_code.strip().upper()

        url = f"{_BASE_URL}/stock_news?tickers={symbol}&limit=50&apikey={self._api_key}"
        data = self._get_json(url)

        if not isinstance(data, list):
            logger.warning("[fmp] Unexpected response type for %s news", symbol)
            return []

        items: List[UnifiedNewsItem] = []

        for article in data:
            try:
                title = (article.get("title") or "").strip()
                article_url = (article.get("url") or "").strip()
                if not title or not article_url:
                    continue

                # FMP returns publishedDate as "YYYY-MM-DD HH:MM:SS" string
                pub_str = article.get("publishedDate", "")
                try:
                    published = datetime.strptime(pub_str, "%Y-%m-%d %H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                except (ValueError, TypeError):
                    published = datetime.now(timezone.utc)

                site = article.get("site", "")
                text = article.get("text", "")

                # FMP news symbol field
                raw_symbol = article.get("symbol", symbol)
                tickers = (
                    [t.strip() for t in raw_symbol.split(",") if t.strip()]
                    if raw_symbol
                    else [symbol]
                )

                items.append(
                    UnifiedNewsItem(
                        title=title,
                        url=article_url,
                        published_at=published,
                        source_name="fmp",
                        tickers=tickers,
                        event_type=NewsEventType.GENERAL,
                        summary=text[:500] if text else None,
                    )
                )
            except Exception as e:
                logger.debug("[fmp] Error parsing news article: %s", e)
                continue

        return items
