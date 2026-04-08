# -*- coding: utf-8 -*-
"""Tests for NewsManager aggregation, dedup, and relevance scoring."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.news.types import NewsEventType, UnifiedNewsItem
from data_provider.news.manager import NewsManager


def _make_item(title, url, source, hours_ago=0, event_type=NewsEventType.GENERAL):
    """Helper to create a UnifiedNewsItem for testing."""
    return UnifiedNewsItem(
        title=title,
        url=url,
        published_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        source_name=source,
        tickers=["AAPL"],
        event_type=event_type,
    )


def _mock_fetcher(name="mock", priority=0, available=True, result=None, side_effect=None):
    """Create a MagicMock that mimics BaseNewsFetcher."""
    fetcher = MagicMock()
    fetcher.name = name
    fetcher.priority = priority
    fetcher.is_available.return_value = available
    if side_effect is not None:
        fetcher.get_news.side_effect = side_effect
    else:
        fetcher.get_news.return_value = result if result is not None else []
    return fetcher


class TestDedup(unittest.TestCase):
    """Deduplication removes items with the same URL."""

    def test_dedup_by_url_keeps_higher_authority(self):
        """Two items same URL -> one result, from higher-authority source."""
        item_fmp = _make_item("News A", "https://example.com/1", "fmp")
        item_finnhub = _make_item("News A dup", "https://example.com/1", "finnhub")
        result = NewsManager._deduplicate([item_fmp, item_finnhub])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source_name, "finnhub")

    def test_different_urls_kept(self):
        """Two items with different URLs -> both kept."""
        item_a = _make_item("News A", "https://example.com/1", "finnhub")
        item_b = _make_item("News B", "https://example.com/2", "fmp")
        result = NewsManager._deduplicate([item_a, item_b])
        self.assertEqual(len(result), 2)


class TestScoring(unittest.TestCase):
    """Relevance scoring based on recency, source authority, event type."""

    def test_earnings_scored_higher_than_general(self):
        """EARNINGS item gets higher relevance_score than GENERAL."""
        earnings = _make_item("Earnings", "https://a.com/1", "finnhub", hours_ago=1,
                              event_type=NewsEventType.EARNINGS)
        general = _make_item("General", "https://a.com/2", "finnhub", hours_ago=1,
                             event_type=NewsEventType.GENERAL)
        scored = NewsManager._score_items([earnings, general])
        earnings_score = next(i for i in scored if i.title == "Earnings").relevance_score
        general_score = next(i for i in scored if i.title == "General").relevance_score
        self.assertGreater(earnings_score, general_score)

    def test_newer_scored_higher(self):
        """Recent item scores higher than old item (same source, same event type)."""
        recent = _make_item("Recent", "https://a.com/1", "finnhub", hours_ago=1)
        old = _make_item("Old", "https://a.com/2", "finnhub", hours_ago=120)
        scored = NewsManager._score_items([recent, old])
        recent_score = next(i for i in scored if i.title == "Recent").relevance_score
        old_score = next(i for i in scored if i.title == "Old").relevance_score
        self.assertGreater(recent_score, old_score)

    def test_score_range(self):
        """Scores should be between 0 and 1."""
        items = [
            _make_item("A", "https://a.com/1", "finnhub", hours_ago=0,
                        event_type=NewsEventType.EARNINGS),
            _make_item("B", "https://a.com/2", "search_adapter", hours_ago=168,
                        event_type=NewsEventType.GENERAL),
        ]
        scored = NewsManager._score_items(items)
        for item in scored:
            self.assertGreaterEqual(item.relevance_score, 0.0)
            self.assertLessEqual(item.relevance_score, 1.0)


class TestAggregation(unittest.TestCase):
    """NewsManager aggregates results from all fetchers."""

    def test_combines_sources(self):
        """Two fetchers each return items -> all combined in result."""
        item_a = _make_item("From Finnhub", "https://a.com/1", "finnhub")
        item_b = _make_item("From FMP", "https://b.com/1", "fmp")
        fetcher_a = _mock_fetcher(name="finnhub", priority=0, result=[item_a])
        fetcher_b = _mock_fetcher(name="fmp", priority=1, result=[item_b])

        mgr = NewsManager(fetchers=[fetcher_a, fetcher_b])
        results = mgr.get_financial_news("AAPL")

        self.assertEqual(len(results), 2)
        titles = {r.title for r in results}
        self.assertIn("From Finnhub", titles)
        self.assertIn("From FMP", titles)

    def test_all_fail_returns_empty(self):
        """All fetchers raise exception -> empty list returned."""
        fetcher_a = _mock_fetcher(name="finnhub", priority=0,
                                  side_effect=RuntimeError("boom"))
        fetcher_b = _mock_fetcher(name="fmp", priority=1,
                                  side_effect=ConnectionError("timeout"))

        mgr = NewsManager(fetchers=[fetcher_a, fetcher_b])
        results = mgr.get_financial_news("AAPL")

        self.assertEqual(results, [])

    def test_partial_failure_still_returns_results(self):
        """One fetcher fails, another succeeds -> results from the survivor."""
        item = _make_item("Good news", "https://a.com/1", "fmp")
        failing = _mock_fetcher(name="finnhub", priority=0,
                                side_effect=RuntimeError("boom"))
        working = _mock_fetcher(name="fmp", priority=1, result=[item])

        mgr = NewsManager(fetchers=[failing, working])
        results = mgr.get_financial_news("AAPL")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Good news")

    def test_results_sorted_by_relevance_descending(self):
        """Results should be sorted by relevance_score descending."""
        # Earnings + recent + finnhub should be scored highest
        high = _make_item("High", "https://a.com/1", "finnhub", hours_ago=1,
                          event_type=NewsEventType.EARNINGS)
        low = _make_item("Low", "https://a.com/2", "search_adapter", hours_ago=120,
                         event_type=NewsEventType.GENERAL)
        fetcher = _mock_fetcher(name="finnhub", result=[low, high])

        mgr = NewsManager(fetchers=[fetcher])
        results = mgr.get_financial_news("AAPL")

        self.assertEqual(results[0].title, "High")
        self.assertGreaterEqual(results[0].relevance_score, results[1].relevance_score)

    def test_unavailable_fetcher_skipped(self):
        """Unavailable fetcher is skipped, available fetcher still queried."""
        item = _make_item("Available", "https://a.com/1", "fmp")
        unavail = _mock_fetcher(name="finnhub", available=False)
        avail = _mock_fetcher(name="fmp", result=[item])

        mgr = NewsManager(fetchers=[unavail, avail])
        results = mgr.get_financial_news("AAPL")

        self.assertEqual(len(results), 1)
        unavail.get_news.assert_not_called()
        avail.get_news.assert_called_once()


if __name__ == "__main__":
    unittest.main()
