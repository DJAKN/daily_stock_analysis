# -*- coding: utf-8 -*-
"""Tests for UnifiedNewsItem and NewsEventType."""

import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.news.types import UnifiedNewsItem, NewsEventType


class TestNewsEventType(unittest.TestCase):
    """NewsEventType enum has expected members."""

    def test_enum_values(self):
        self.assertEqual(NewsEventType.EARNINGS.value, "earnings")
        self.assertEqual(NewsEventType.ANALYST_RATING.value, "analyst_rating")
        self.assertEqual(NewsEventType.SEC_FILING.value, "sec_filing")
        self.assertEqual(NewsEventType.INSIDER.value, "insider")
        self.assertEqual(NewsEventType.M_AND_A.value, "m_and_a")
        self.assertEqual(NewsEventType.GENERAL.value, "general")


class TestUnifiedNewsItemCreation(unittest.TestCase):
    """UnifiedNewsItem creation with required fields."""

    def test_creation_with_required_fields(self):
        now = datetime.now(timezone.utc)
        item = UnifiedNewsItem(
            title="Apple beats earnings",
            url="https://example.com/article",
            published_at=now,
            source_name="finnhub",
            tickers=["AAPL"],
            event_type=NewsEventType.EARNINGS,
        )
        self.assertEqual(item.title, "Apple beats earnings")
        self.assertEqual(item.url, "https://example.com/article")
        self.assertEqual(item.published_at, now)
        self.assertEqual(item.source_name, "finnhub")
        self.assertEqual(item.tickers, ["AAPL"])
        self.assertEqual(item.event_type, NewsEventType.EARNINGS)

    def test_default_values(self):
        now = datetime.now(timezone.utc)
        item = UnifiedNewsItem(
            title="Test",
            url="https://example.com",
            published_at=now,
            source_name="fmp",
            tickers=["TSLA"],
            event_type=NewsEventType.GENERAL,
        )
        self.assertIsNone(item.sentiment)
        self.assertIsNone(item.summary)
        self.assertIsNone(item.body)
        self.assertAlmostEqual(item.relevance_score, 0.0)

    def test_creation_with_all_fields(self):
        now = datetime.now(timezone.utc)
        item = UnifiedNewsItem(
            title="SEC Filing",
            url="https://sec.gov/filing",
            published_at=now,
            source_name="edgar",
            tickers=["MSFT", "AAPL"],
            event_type=NewsEventType.SEC_FILING,
            sentiment=0.5,
            summary="A summary",
            body="Full body text",
            relevance_score=0.85,
        )
        self.assertAlmostEqual(item.sentiment, 0.5)
        self.assertEqual(item.summary, "A summary")
        self.assertEqual(item.body, "Full body text")
        self.assertAlmostEqual(item.relevance_score, 0.85)


class TestUnifiedNewsItemToDict(unittest.TestCase):
    """to_dict includes event_type as string."""

    def test_to_dict_event_type_as_string(self):
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        item = UnifiedNewsItem(
            title="Earnings beat",
            url="https://example.com",
            published_at=now,
            source_name="finnhub",
            tickers=["AAPL"],
            event_type=NewsEventType.EARNINGS,
            sentiment=0.8,
        )
        d = item.to_dict()
        self.assertEqual(d["title"], "Earnings beat")
        self.assertEqual(d["url"], "https://example.com")
        self.assertEqual(d["published_at"], now)
        self.assertEqual(d["source_name"], "finnhub")
        self.assertEqual(d["tickers"], ["AAPL"])
        self.assertEqual(d["event_type"], "earnings")
        self.assertAlmostEqual(d["sentiment"], 0.8)
        self.assertAlmostEqual(d["relevance_score"], 0.0)

    def test_to_dict_includes_none_optional_fields(self):
        now = datetime.now(timezone.utc)
        item = UnifiedNewsItem(
            title="Test",
            url="https://example.com",
            published_at=now,
            source_name="fmp",
            tickers=[],
            event_type=NewsEventType.GENERAL,
        )
        d = item.to_dict()
        self.assertIn("sentiment", d)
        self.assertIsNone(d["sentiment"])
        self.assertIn("summary", d)
        self.assertIsNone(d["summary"])
        self.assertIn("body", d)
        self.assertIsNone(d["body"])

    def test_to_dict_multiple_tickers(self):
        now = datetime.now(timezone.utc)
        item = UnifiedNewsItem(
            title="M&A News",
            url="https://example.com",
            published_at=now,
            source_name="fmp",
            tickers=["AAPL", "MSFT", "GOOG"],
            event_type=NewsEventType.M_AND_A,
        )
        d = item.to_dict()
        self.assertEqual(d["tickers"], ["AAPL", "MSFT", "GOOG"])
        self.assertEqual(d["event_type"], "m_and_a")


if __name__ == "__main__":
    unittest.main()
