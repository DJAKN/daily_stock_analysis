# -*- coding: utf-8 -*-
"""Tests for FinnhubFundamentalFetcher."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.fundamental.finnhub_fetcher import FinnhubFundamentalFetcher


class TestAvailability(unittest.TestCase):
    """Finnhub fetcher availability depends on API key."""

    @patch.dict(os.environ, {}, clear=True)
    def test_unavailable_without_key(self):
        os.environ.pop("FINNHUB_API_KEY", None)
        fetcher = FinnhubFundamentalFetcher()
        self.assertFalse(fetcher.is_available())

    @patch.dict(os.environ, {"FINNHUB_API_KEY": "test_key_abc"})
    def test_available_with_key(self):
        fetcher = FinnhubFundamentalFetcher()
        self.assertTrue(fetcher.is_available())


class TestGetFundamentals(unittest.TestCase):
    """Finnhub fetcher returns UnifiedFundamentalData on success."""

    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {"FINNHUB_API_KEY": "test_key_abc"})
        self.env_patcher.start()
        self.fetcher = FinnhubFundamentalFetcher()

    def tearDown(self):
        self.env_patcher.stop()

    @patch.object(FinnhubFundamentalFetcher, "_get_json")
    def test_success_with_mocked_api(self, mock_get_json):
        """Full success path with metric + insider endpoints."""
        metric_response = {
            "metric": {
                "peNormalizedAnnual": 29.5,
                "peTTM": 28.0,
                "pbQuarterly": 42.0,
                "psAnnual": 7.5,
                "pegRatio": 1.8,
                "currentEv/freeCashFlowTTM": 20.0,
                "epsGrowthTTMYoy": 0.12,
                "revenuePerShareTTM": 24.5,
                "netProfitMarginTTM": 0.253,
                "operatingMarginTTM": 0.301,
                "roeTTM": 1.47,
                "roaTTM": 0.28,
                "totalDebt/totalEquityQuarterly": 1.80,
                "currentRatioQuarterly": 0.99,
                "dividendYieldIndicatedAnnual": 0.55,
                "payoutRatioAnnual": 15.2,
                "freeCashFlowTTM": 110500000000,
                "epsBasicExclExtraItemsTTM": 6.42,
            }
        }

        insider_response = {
            "data": [
                {"change": 5000},   # buy
                {"change": -2000},  # sell
                {"change": 3000},   # buy
                {"change": -1000},  # sell
                {"change": -500},   # sell
            ]
        }

        def side_effect(url):
            if "metric" in url:
                return metric_response
            elif "insider-sentiment" in url:
                return insider_response
            return None

        mock_get_json.side_effect = side_effect

        result = self.fetcher.get_fundamentals("AAPL")

        self.assertIsNotNone(result)
        self.assertEqual(result.code, "AAPL")
        self.assertEqual(result.source, "finnhub")
        self.assertAlmostEqual(result.pe_ratio, 28.0)
        self.assertAlmostEqual(result.pb_ratio, 42.0)
        self.assertAlmostEqual(result.ps_ratio, 7.5)
        self.assertAlmostEqual(result.profit_margin, 0.253)
        self.assertAlmostEqual(result.operating_margin, 0.301)
        self.assertAlmostEqual(result.roe, 1.47)
        self.assertAlmostEqual(result.roa, 0.28)
        self.assertAlmostEqual(result.current_ratio, 0.99)
        # Insider: 2 buys (positive change), 3 sells (negative change)
        self.assertEqual(result.insider_buy_count_90d, 2)
        self.assertEqual(result.insider_sell_count_90d, 3)

    @patch.object(FinnhubFundamentalFetcher, "_get_json")
    def test_returns_none_on_api_failure(self, mock_get_json):
        """Returns None when all API calls fail."""
        mock_get_json.return_value = None

        result = self.fetcher.get_fundamentals("AAPL")
        self.assertIsNone(result)

    @patch.object(FinnhubFundamentalFetcher, "_get_json")
    def test_partial_data_metrics_only(self, mock_get_json):
        """Returns data when only metrics succeed."""
        metric_response = {
            "metric": {
                "peTTM": 28.0,
                "roeTTM": 1.47,
            }
        }

        def side_effect(url):
            if "metric" in url:
                return metric_response
            return None

        mock_get_json.side_effect = side_effect

        result = self.fetcher.get_fundamentals("AAPL")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.pe_ratio, 28.0)
        self.assertAlmostEqual(result.roe, 1.47)
        self.assertIsNone(result.insider_buy_count_90d)

    @patch.object(FinnhubFundamentalFetcher, "_get_json")
    def test_handles_empty_metric(self, mock_get_json):
        """Returns None when metric key is missing."""
        mock_get_json.return_value = {}

        result = self.fetcher.get_fundamentals("AAPL")
        self.assertIsNone(result)

    def test_name_and_priority(self):
        self.assertEqual(self.fetcher.name, "finnhub")
        self.assertEqual(self.fetcher.priority, 1)


if __name__ == "__main__":
    unittest.main()
