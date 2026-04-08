# -*- coding: utf-8 -*-
"""Tests for FMPFundamentalFetcher."""

import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.fundamental.fmp_fetcher import FMPFundamentalFetcher


class TestAvailability(unittest.TestCase):
    """FMP fetcher availability depends on API key."""

    @patch.dict(os.environ, {}, clear=True)
    def test_unavailable_without_key(self):
        # Ensure FMP_API_KEY is not set
        os.environ.pop("FMP_API_KEY", None)
        fetcher = FMPFundamentalFetcher()
        self.assertFalse(fetcher.is_available())

    @patch.dict(os.environ, {"FMP_API_KEY": "test_key_123"})
    def test_available_with_key(self):
        fetcher = FMPFundamentalFetcher()
        self.assertTrue(fetcher.is_available())


class TestGetFundamentals(unittest.TestCase):
    """FMP fetcher returns UnifiedFundamentalData on success."""

    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {"FMP_API_KEY": "test_key_123"})
        self.env_patcher.start()
        self.fetcher = FMPFundamentalFetcher()

    def tearDown(self):
        self.env_patcher.stop()

    @patch.object(FMPFundamentalFetcher, "_get_json")
    def test_success_with_mocked_api(self, mock_get_json):
        """Full success path with all three API responses."""
        ratios_response = [
            {
                "peRatioTTM": 28.5,
                "priceToBookRatioTTM": 45.2,
                "priceToSalesRatioTTM": 7.8,
                "pegRatioTTM": 2.1,
                "enterpriseValueOverEBITDATTM": 22.3,
                "netProfitMarginTTM": 0.25,
                "operatingProfitMarginTTM": 0.30,
                "returnOnEquityTTM": 1.47,
                "returnOnAssetsTTM": 0.28,
                "debtToEquityTTM": 1.76,
                "currentRatioTTM": 0.98,
                "dividendYieldTTM": 0.006,
                "payoutRatioTTM": 0.15,
                "freeCashFlowPerShareTTM": 6.5,
            }
        ]

        earnings_response = [
            {
                "date": "2024-01-25",
                "actualEarningResult": 2.18,
                "estimatedEarning": 2.10,
            }
        ]

        # Use dates within the last 90 days
        recent_date_1 = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        recent_date_2 = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        recent_date_3 = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
        recent_date_4 = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        insider_response = [
            {"transactionType": "P-Purchase", "transactionDate": recent_date_1},
            {"transactionType": "S-Sale", "transactionDate": recent_date_2},
            {"transactionType": "S-Sale", "transactionDate": recent_date_3},
            {"transactionType": "P-Purchase", "transactionDate": recent_date_4},
        ]

        def side_effect(url):
            if "ratios-ttm" in url:
                return ratios_response
            elif "earnings-surprises" in url:
                return earnings_response
            elif "insider-trading" in url:
                return insider_response
            return None

        mock_get_json.side_effect = side_effect

        result = self.fetcher.get_fundamentals("AAPL")

        self.assertIsNotNone(result)
        self.assertEqual(result.code, "AAPL")
        self.assertEqual(result.source, "fmp")
        self.assertAlmostEqual(result.pe_ratio, 28.5)
        self.assertAlmostEqual(result.pb_ratio, 45.2)
        self.assertAlmostEqual(result.ps_ratio, 7.8)
        self.assertAlmostEqual(result.peg_ratio, 2.1)
        self.assertAlmostEqual(result.ev_ebitda, 22.3)
        self.assertAlmostEqual(result.profit_margin, 0.25)
        self.assertAlmostEqual(result.operating_margin, 0.30)
        self.assertAlmostEqual(result.roe, 1.47)
        self.assertAlmostEqual(result.roa, 0.28)
        self.assertAlmostEqual(result.debt_to_equity, 1.76)
        self.assertAlmostEqual(result.current_ratio, 0.98)
        self.assertAlmostEqual(result.dividend_yield, 0.006)
        self.assertAlmostEqual(result.payout_ratio, 0.15)
        # Earnings
        self.assertAlmostEqual(result.eps_ttm, 2.18)
        self.assertAlmostEqual(result.eps_estimate, 2.10)
        self.assertEqual(result.earnings_date, "2024-01-25")
        # Insider trading: 2 buys, 2 sells
        self.assertEqual(result.insider_buy_count_90d, 2)
        self.assertEqual(result.insider_sell_count_90d, 2)

    @patch.object(FMPFundamentalFetcher, "_get_json")
    def test_returns_none_on_api_failure(self, mock_get_json):
        """Returns None when all API calls fail."""
        mock_get_json.return_value = None

        result = self.fetcher.get_fundamentals("AAPL")
        self.assertIsNone(result)

    @patch.object(FMPFundamentalFetcher, "_get_json")
    def test_partial_data_when_some_endpoints_fail(self, mock_get_json):
        """Returns partial data when only ratios succeed."""
        ratios_response = [
            {
                "peRatioTTM": 28.5,
                "priceToBookRatioTTM": 45.2,
            }
        ]

        def side_effect(url):
            if "ratios-ttm" in url:
                return ratios_response
            return None

        mock_get_json.side_effect = side_effect

        result = self.fetcher.get_fundamentals("AAPL")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.pe_ratio, 28.5)
        self.assertAlmostEqual(result.pb_ratio, 45.2)
        # Earnings fields should be None since that endpoint failed
        self.assertIsNone(result.eps_ttm)
        self.assertIsNone(result.insider_buy_count_90d)

    @patch.object(FMPFundamentalFetcher, "_get_json")
    def test_handles_empty_list_response(self, mock_get_json):
        """Returns None when API returns empty lists."""
        mock_get_json.return_value = []

        result = self.fetcher.get_fundamentals("AAPL")
        self.assertIsNone(result)

    def test_name_and_priority(self):
        self.assertEqual(self.fetcher.name, "fmp")
        self.assertEqual(self.fetcher.priority, 0)


class TestSafeHelper(unittest.TestCase):
    """_safe helper handles edge cases."""

    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {"FMP_API_KEY": "test_key_123"})
        self.env_patcher.start()
        self.fetcher = FMPFundamentalFetcher()

    def tearDown(self):
        self.env_patcher.stop()

    def test_safe_with_none(self):
        self.assertIsNone(self.fetcher._safe(None))

    def test_safe_with_float(self):
        self.assertAlmostEqual(self.fetcher._safe(25.3), 25.3)

    def test_safe_with_nan(self):
        import math
        self.assertIsNone(self.fetcher._safe(float("nan")))

    def test_safe_with_inf(self):
        self.assertIsNone(self.fetcher._safe(float("inf")))

    def test_safe_with_neg_inf(self):
        self.assertIsNone(self.fetcher._safe(float("-inf")))

    def test_safe_with_int(self):
        self.assertAlmostEqual(self.fetcher._safe(25), 25.0)

    def test_safe_with_string(self):
        self.assertIsNone(self.fetcher._safe("not_a_number"))

    def test_safe_with_zero(self):
        self.assertAlmostEqual(self.fetcher._safe(0), 0.0)


if __name__ == "__main__":
    unittest.main()
