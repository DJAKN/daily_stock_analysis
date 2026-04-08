# -*- coding: utf-8 -*-
"""
Finnhub news fetcher.

Primary provider, priority 0. Free tier: 60 req/min.
Base URL: https://finnhub.io/api/v1

Endpoints used:
- /company-news?symbol={symbol}&from={start}&to={end} -- ticker-tagged articles
- /stock/recommendation?symbol={symbol} -- analyst upgrades/downgrades
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from .base import BaseNewsFetcher
from .types import NewsEventType, UnifiedNewsItem

logger = logging.getLogger(__name__)

_BASE_URL = "https://finnhub.io/api/v1"

# Mapping from Finnhub news categories to our NewsEventType
_CATEGORY_MAP = {
    "merger": NewsEventType.M_AND_A,
    "acquisition": NewsEventType.M_AND_A,
    "earnings": NewsEventType.EARNINGS,
    "insider": NewsEventType.INSIDER,
    "sec filing": NewsEventType.SEC_FILING,
    "filing": NewsEventType.SEC_FILING,
}


def _map_category(category: str) -> NewsEventType:
    """Map Finnhub category string to NewsEventType."""
    if not category:
        return NewsEventType.GENERAL
    return _CATEGORY_MAP.get(category.lower().strip(), NewsEventType.GENERAL)


class FinnhubNewsFetcher(BaseNewsFetcher):
    """Finnhub news fetcher (priority 0)."""

    name = "finnhub"
    priority = 0

    def __init__(self) -> None:
        self._api_key = os.environ.get("FINNHUB_API_KEY", "").strip() or None

    def is_available(self) -> bool:
        return self._api_key is not None

    def get_news(self, stock_code: str, days: int = 7) -> List[UnifiedNewsItem]:
        if not self.is_available():
            logger.debug("[finnhub] API key not configured, skipping news")
            return []

        symbol = stock_code.strip().upper()
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        items: List[UnifiedNewsItem] = []

        # 1. Company news
        news_url = (
            f"{_BASE_URL}/company-news"
            f"?symbol={symbol}&from={start_date}&to={end_date}"
            f"&token={self._api_key}"
        )
        news_data = self._get_json(news_url)

        if isinstance(news_data, list):
            for article in news_data:
                try:
                    ts = article.get("datetime")
                    if ts is None:
                        continue
                    published = datetime.fromtimestamp(ts, tz=timezone.utc)
                    headline = article.get("headline", "").strip()
                    url = article.get("url", "").strip()
                    if not headline or not url:
                        continue

                    related = article.get("related", "")
                    tickers = (
                        [t.strip() for t in related.split(",") if t.strip()]
                        if related
                        else [symbol]
                    )

                    category = article.get("category", "")
                    event_type = _map_category(category)

                    sentiment = self._safe(article.get("sentiment"))

                    items.append(
                        UnifiedNewsItem(
                            title=headline,
                            url=url,
                            published_at=published,
                            source_name="finnhub",
                            tickers=tickers,
                            event_type=event_type,
                            sentiment=sentiment,
                            summary=article.get("summary"),
                        )
                    )
                except Exception as e:
                    logger.debug("[finnhub] Error parsing news article: %s", e)
                    continue

        # 2. Analyst recommendations -> synthetic ANALYST_RATING item
        rec_url = (
            f"{_BASE_URL}/stock/recommendation"
            f"?symbol={symbol}&token={self._api_key}"
        )
        rec_data = self._get_json(rec_url)

        if isinstance(rec_data, list) and rec_data:
            try:
                latest = rec_data[0]
                period = latest.get("period", "")
                buy = latest.get("buy", 0) or 0
                strong_buy = latest.get("strongBuy", 0) or 0
                hold = latest.get("hold", 0) or 0
                sell = latest.get("sell", 0) or 0
                strong_sell = latest.get("strongSell", 0) or 0

                total = buy + strong_buy + hold + sell + strong_sell
                if total > 0:
                    # Compute a sentiment-like score from recommendations
                    # Range: -1 (all strong sell) to +1 (all strong buy)
                    weighted = (
                        strong_buy * 1.0
                        + buy * 0.5
                        + hold * 0.0
                        + sell * -0.5
                        + strong_sell * -1.0
                    )
                    rec_sentiment = weighted / total

                    # Parse period date or use now
                    try:
                        rec_date = datetime.strptime(period, "%Y-%m-%d").replace(
                            tzinfo=timezone.utc
                        )
                    except (ValueError, TypeError):
                        rec_date = now

                    summary_text = (
                        f"Analyst consensus: "
                        f"Strong Buy={strong_buy}, Buy={buy}, Hold={hold}, "
                        f"Sell={sell}, Strong Sell={strong_sell}"
                    )

                    items.append(
                        UnifiedNewsItem(
                            title=f"Analyst Recommendations for {symbol}",
                            url=f"https://finnhub.io/api/v1/stock/recommendation?symbol={symbol}",
                            published_at=rec_date,
                            source_name="finnhub",
                            tickers=[symbol],
                            event_type=NewsEventType.ANALYST_RATING,
                            sentiment=round(rec_sentiment, 3),
                            summary=summary_text,
                        )
                    )
            except Exception as e:
                logger.debug("[finnhub] Error parsing recommendations: %s", e)

        return items
