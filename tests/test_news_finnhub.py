# -*- coding: utf-8 -*-
"""Tests for FinnhubNewsFetcher."""

import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.news.finnhub_fetcher import FinnhubNewsFetcher
from data_provider.news.types import NewsEventType


class TestAvailability(unittest.TestCase):
    """Finnhub news fetcher availability depends on API key."""

    @patch.dict(os.environ, {}, clear=True)
    def test_unavailable_without_key(self):
        os.environ.pop("FINNHUB_API_KEY", None)
        fetcher = FinnhubNewsFetcher()
        self.assertFalse(fetcher.is_available())

    @patch.dict(os.environ, {"FINNHUB_API_KEY": "test_key_abc"})
    def test_available_with_key(self):
        fetcher = FinnhubNewsFetcher()
        self.assertTrue(fetcher.is_available())


class TestGetNews(unittest.TestCase):
    """Finnhub news fetcher returns UnifiedNewsItem list on success."""

    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {"FINNHUB_API_KEY": "test_key_abc"})
        self.env_patcher.start()
        self.fetcher = FinnhubNewsFetcher()

    def tearDown(self):
        self.env_patcher.stop()

    @patch.object(FinnhubNewsFetcher, "_get_json")
    def test_success_with_mocked_company_news(self, mock_get_json):
        """Full success path with company-news endpoint."""
        company_news_response = [
            {
                "category": "company",
                "datetime": 1704067200,  # 2024-01-01 00:00:00 UTC
                "headline": "Apple reports record Q4 earnings",
                "id": 12345,
                "image": "https://example.com/img.png",
                "related": "AAPL",
                "source": "Reuters",
                "summary": "Apple Inc reported record earnings...",
                "url": "https://reuters.com/article/apple-earnings",
            },
            {
                "category": "company",
                "datetime": 1704153600,  # 2024-01-02 00:00:00 UTC
                "headline": "Apple M&A: acquires AI startup",
                "id": 12346,
                "image": "",
                "related": "AAPL",
                "source": "Bloomberg",
                "summary": "Apple acquired an AI startup...",
                "url": "https://bloomberg.com/article/apple-ma",
            },
        ]

        recommendation_response = [
            {
                "buy": 25,
                "hold": 8,
                "period": "2024-01-01",
                "sell": 2,
                "strongBuy": 12,
                "strongSell": 1,
                "symbol": "AAPL",
            }
        ]

        def side_effect(url, **kwargs):
            if "company-news" in url:
                return company_news_response
            elif "recommendation" in url:
                return recommendation_response
            return None

        mock_get_json.side_effect = side_effect

        results = self.fetcher.get_news("AAPL", days=7)

        self.assertIsInstance(results, list)
        # Should have company news items + analyst rating item
        self.assertGreater(len(results), 0)

        # Verify first news item
        news_item = results[0]
        self.assertEqual(news_item.title, "Apple reports record Q4 earnings")
        self.assertEqual(news_item.url, "https://reuters.com/article/apple-earnings")
        self.assertEqual(news_item.source_name, "finnhub")
        self.assertIn("AAPL", news_item.tickers)
        self.assertIsNotNone(news_item.summary)

    @patch.object(FinnhubNewsFetcher, "_get_json")
    def test_success_with_mocked_recommendation(self, mock_get_json):
        """Analyst recommendations create ANALYST_RATING items."""
        recommendation_response = [
            {
                "buy": 25,
                "hold": 8,
                "period": "2024-01-01",
                "sell": 2,
                "strongBuy": 12,
                "strongSell": 1,
                "symbol": "AAPL",
            }
        ]

        def side_effect(url, **kwargs):
            if "company-news" in url:
                return []
            elif "recommendation" in url:
                return recommendation_response
            return None

        mock_get_json.side_effect = side_effect

        results = self.fetcher.get_news("AAPL", days=7)

        # Should have at least the analyst rating item
        analyst_items = [r for r in results if r.event_type == NewsEventType.ANALYST_RATING]
        self.assertGreater(len(analyst_items), 0)

    @patch.object(FinnhubNewsFetcher, "_get_json")
    def test_returns_empty_list_on_api_failure(self, mock_get_json):
        """Returns empty list when all API calls fail."""
        mock_get_json.return_value = None

        results = self.fetcher.get_news("AAPL")
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 0)

    @patch.object(FinnhubNewsFetcher, "_get_json")
    def test_returns_empty_list_without_key(self, mock_get_json):
        """Returns empty list when no API key."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("FINNHUB_API_KEY", None)
            fetcher = FinnhubNewsFetcher()
            results = fetcher.get_news("AAPL")
            self.assertEqual(results, [])
            mock_get_json.assert_not_called()

    @patch.object(FinnhubNewsFetcher, "_get_json")
    def test_maps_event_types_correctly(self, mock_get_json):
        """Verifies category-to-event-type mapping."""
        company_news_response = [
            {
                "category": "merger",
                "datetime": 1704067200,
                "headline": "Merger news",
                "id": 1,
                "related": "AAPL",
                "source": "Test",
                "summary": "Test",
                "url": "https://example.com/1",
            },
            {
                "category": "company",
                "datetime": 1704067200,
                "headline": "Company news",
                "id": 2,
                "related": "AAPL",
                "source": "Test",
                "summary": "Test",
                "url": "https://example.com/2",
            },
        ]

        def side_effect(url, **kwargs):
            if "company-news" in url:
                return company_news_response
            elif "recommendation" in url:
                return []
            return None

        mock_get_json.side_effect = side_effect

        results = self.fetcher.get_news("AAPL", days=7)

        event_types = {r.title: r.event_type for r in results}
        self.assertEqual(event_types.get("Merger news"), NewsEventType.M_AND_A)
        self.assertEqual(event_types.get("Company news"), NewsEventType.GENERAL)

    def test_name_and_priority(self):
        self.assertEqual(self.fetcher.name, "finnhub")
        self.assertEqual(self.fetcher.priority, 0)


if __name__ == "__main__":
    unittest.main()
