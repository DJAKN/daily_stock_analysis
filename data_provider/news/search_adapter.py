# -*- coding: utf-8 -*-
"""
Search adapter for news fetching.

Fallback provider, priority 3. Wraps the existing search_service.py
to provide news results through the unified news interface.

This is a thin adapter -- it delegates to the existing SearchService
rather than duplicating search logic.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from .base import BaseNewsFetcher
from .types import NewsEventType, UnifiedNewsItem

logger = logging.getLogger(__name__)


class SearchAdapterNewsFetcher(BaseNewsFetcher):
    """Search service adapter as news fetcher (priority 3, fallback).

    Wraps the existing SearchService.search_stock_news() method.
    Gracefully handles import or runtime failures.
    """

    name = "search_adapter"
    priority = 3

    def __init__(self) -> None:
        self._search_service = None
        self._init_error: Optional[str] = None
        try:
            from src.search_service import SearchService
            self._search_service = SearchService()
        except Exception as e:
            self._init_error = str(e)
            logger.debug(
                "[search_adapter] Could not initialize SearchService: %s", e
            )

    def is_available(self) -> bool:
        # search_service handles its own provider availability internally
        return True

    def get_news(self, stock_code: str, days: int = 7) -> List[UnifiedNewsItem]:
        if self._search_service is None:
            logger.debug(
                "[search_adapter] SearchService not available: %s", self._init_error
            )
            return []

        symbol = stock_code.strip().upper()

        try:
            response = self._search_service.search_stock_news(
                stock_code=symbol,
                stock_name=symbol,  # Use ticker as name for search query
                max_results=10,
            )

            if not response.success or not response.results:
                return []

            items: List[UnifiedNewsItem] = []
            for result in response.results:
                try:
                    # Parse published_date if available
                    published = datetime.now(timezone.utc)
                    if result.published_date:
                        try:
                            published = datetime.strptime(
                                result.published_date, "%Y-%m-%d"
                            ).replace(tzinfo=timezone.utc)
                        except (ValueError, TypeError):
                            try:
                                published = datetime.strptime(
                                    result.published_date, "%Y-%m-%dT%H:%M:%S"
                                ).replace(tzinfo=timezone.utc)
                            except (ValueError, TypeError):
                                pass  # keep default

                    title = (result.title or "").strip()
                    url = (result.url or "").strip()
                    if not title or not url:
                        continue

                    items.append(
                        UnifiedNewsItem(
                            title=title,
                            url=url,
                            published_at=published,
                            source_name="tavily",
                            tickers=[symbol],
                            event_type=NewsEventType.GENERAL,
                            summary=result.snippet if result.snippet else None,
                        )
                    )
                except Exception as e:
                    logger.debug("[search_adapter] Error converting result: %s", e)
                    continue

            return items

        except Exception as e:
            logger.warning("[search_adapter] Error fetching news for %s: %s", symbol, e)
            return []
