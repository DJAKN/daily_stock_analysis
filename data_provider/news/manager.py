# -*- coding: utf-8 -*-
"""
NewsManager — orchestrates news fetchers with aggregation,
deduplication, and relevance scoring.

Unlike FundamentalManager (failover), NewsManager queries ALL available
fetchers and COMBINES results, since different sources have different
news coverage.
"""

import logging
import math
from datetime import datetime, timezone
from typing import Dict, List

from .base import BaseNewsFetcher
from .types import NewsEventType, UnifiedNewsItem

logger = logging.getLogger(__name__)

# Source authority weights: higher = more authoritative
_SOURCE_AUTHORITY: Dict[str, float] = {
    "finnhub": 1.0,
    "fmp": 0.8,
    "edgar": 0.6,
    "search_adapter": 0.3,
    "tavily": 0.3,
}

# Event type importance weights: higher = more relevant
_EVENT_TYPE_WEIGHT: Dict[NewsEventType, float] = {
    NewsEventType.EARNINGS: 1.0,
    NewsEventType.ANALYST_RATING: 1.0,
    NewsEventType.SEC_FILING: 0.7,
    NewsEventType.INSIDER: 0.7,
    NewsEventType.M_AND_A: 0.5,
    NewsEventType.GENERAL: 0.3,
}

# Decay half-life in hours for recency scoring
_RECENCY_HALF_LIFE_HOURS = 48.0


class NewsManager:
    """Orchestrates news fetchers with aggregation, dedup, and scoring.

    All available fetchers are queried independently. Results are combined,
    deduplicated by URL, scored for relevance, and returned sorted.
    """

    def __init__(self, fetchers=None):
        self._fetchers: List[BaseNewsFetcher] = fetchers or []

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls) -> "NewsManager":
        """Create with all configured news fetchers."""
        from .finnhub_fetcher import FinnhubNewsFetcher
        from .fmp_fetcher import FMPNewsFetcher
        from .edgar_fetcher import EDGARNewsFetcher
        from .search_adapter import SearchAdapterNewsFetcher

        fetchers: List[BaseNewsFetcher] = [
            FinnhubNewsFetcher(),
            FMPNewsFetcher(),
            EDGARNewsFetcher(),
            SearchAdapterNewsFetcher(),
        ]
        return cls(fetchers=fetchers)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_financial_news(
        self, stock_code: str, days: int = 7
    ) -> List[UnifiedNewsItem]:
        """Query all available fetchers, aggregate, dedup, score, sort.

        Returns a list of UnifiedNewsItem sorted by relevance_score
        descending. Returns empty list if all fetchers fail.
        """
        all_items: List[UnifiedNewsItem] = []

        for fetcher in self._fetchers:
            if not fetcher.is_available():
                logger.debug(
                    "[NewsManager] %s unavailable, skipping", fetcher.name
                )
                continue

            try:
                items = fetcher.get_news(stock_code, days)
                if items:
                    logger.info(
                        "[NewsManager] %s returned %d items for %s",
                        fetcher.name,
                        len(items),
                        stock_code,
                    )
                    all_items.extend(items)
            except Exception as exc:
                logger.warning(
                    "[NewsManager] %s raised %s: %s",
                    fetcher.name,
                    type(exc).__name__,
                    exc,
                )
                continue

        if not all_items:
            logger.info("[NewsManager] no news items collected for %s", stock_code)
            return []

        # Dedup -> score -> sort
        deduped = self._deduplicate(all_items)
        scored = self._score_items(deduped)
        scored.sort(key=lambda item: item.relevance_score, reverse=True)
        return scored

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate(items: List[UnifiedNewsItem]) -> List[UnifiedNewsItem]:
        """Remove duplicates by URL, keeping the item from the higher-authority source."""
        seen: Dict[str, UnifiedNewsItem] = {}
        for item in items:
            url = item.url
            if url in seen:
                existing = seen[url]
                existing_authority = _SOURCE_AUTHORITY.get(
                    existing.source_name, 0.0
                )
                new_authority = _SOURCE_AUTHORITY.get(item.source_name, 0.0)
                if new_authority > existing_authority:
                    seen[url] = item
            else:
                seen[url] = item
        return list(seen.values())

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _score_items(items: List[UnifiedNewsItem]) -> List[UnifiedNewsItem]:
        """Compute relevance_score (0-1) based on recency, source authority, event type.

        Formula (weighted average):
            score = 0.4 * recency + 0.3 * authority + 0.3 * event_weight

        Recency uses exponential decay: exp(-lambda * hours_old)
        where lambda = ln(2) / half_life_hours.
        """
        now = datetime.now(timezone.utc)
        decay_lambda = math.log(2) / _RECENCY_HALF_LIFE_HOURS

        for item in items:
            # Recency score (0-1): exponential decay
            published = item.published_at
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            delta_hours = max(
                (now - published).total_seconds() / 3600.0, 0.0
            )
            recency = math.exp(-decay_lambda * delta_hours)

            # Source authority score (0-1)
            authority = _SOURCE_AUTHORITY.get(item.source_name, 0.3)

            # Event type score (0-1)
            event_weight = _EVENT_TYPE_WEIGHT.get(
                item.event_type, 0.3
            )

            # Weighted combination
            score = 0.4 * recency + 0.3 * authority + 0.3 * event_weight
            item.relevance_score = round(min(max(score, 0.0), 1.0), 4)

        return items
