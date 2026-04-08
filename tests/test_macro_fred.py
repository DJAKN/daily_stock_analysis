# -*- coding: utf-8 -*-
"""Tests for FREDMacroFetcher."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.macro.fred_fetcher import FREDMacroFetcher


class TestAvailability(unittest.TestCase):
    """FRED fetcher availability depends on API key."""

    @patch.dict(os.environ, {}, clear=True)
    def test_unavailable_without_key(self):
        os.environ.pop("FRED_API_KEY", None)
        fetcher = FREDMacroFetcher()
        self.assertFalse(fetcher.is_available())

    @patch.dict(os.environ, {"FRED_API_KEY": "test_fred_key"})
    def test_available_with_key(self):
        fetcher = FREDMacroFetcher()
        self.assertTrue(fetcher.is_available())


class TestGetIndicators(unittest.TestCase):
    """FRED fetcher returns Dict[str, MacroIndicator] on success."""

    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {"FRED_API_KEY": "test_fred_key"})
        self.env_patcher.start()
        self.fetcher = FREDMacroFetcher()

    def tearDown(self):
        self.env_patcher.stop()

    @patch.object(FREDMacroFetcher, "_get_json")
    def test_success_with_mocked_response(self, mock_get_json):
        """Two observations produce value, previous_value, and change."""

        def side_effect(url, **kwargs):
            params = kwargs.get("params", {})
            series_id = params.get("series_id", "")
            if series_id == "FEDFUNDS":
                return {
                    "observations": [
                        {"date": "2026-03-01", "value": "5.33"},
                        {"date": "2026-02-01", "value": "5.50"},
                    ]
                }
            elif series_id == "DGS10":
                return {
                    "observations": [
                        {"date": "2026-04-01", "value": "4.25"},
                        {"date": "2026-03-28", "value": "4.30"},
                    ]
                }
            # Return empty for all other series
            return {"observations": []}

        mock_get_json.side_effect = side_effect

        result = self.fetcher.get_indicators()

        self.assertIn("fed_funds_rate", result)
        ffr = result["fed_funds_rate"]
        self.assertAlmostEqual(ffr.value, 5.33)
        self.assertAlmostEqual(ffr.previous_value, 5.50)
        self.assertAlmostEqual(ffr.change, -0.17)
        self.assertEqual(ffr.unit, "%")
        self.assertEqual(ffr.as_of_date, "2026-03-01")
        self.assertEqual(ffr.source, "fred")

        self.assertIn("treasury_10y", result)
        t10 = result["treasury_10y"]
        self.assertAlmostEqual(t10.value, 4.25)
        self.assertAlmostEqual(t10.previous_value, 4.30)
        self.assertAlmostEqual(t10.change, -0.05)

    @patch.object(FREDMacroFetcher, "_get_json")
    def test_individual_series_failure_doesnt_break_batch(self, mock_get_json):
        """If one series fails, others still succeed."""

        call_count = 0

        def side_effect(url, **kwargs):
            nonlocal call_count
            call_count += 1
            params = kwargs.get("params", {})
            series_id = params.get("series_id", "")
            if series_id == "FEDFUNDS":
                return {
                    "observations": [
                        {"date": "2026-03-01", "value": "5.33"},
                        {"date": "2026-02-01", "value": "5.50"},
                    ]
                }
            elif series_id == "CPIAUCSL":
                # Simulate failure
                raise Exception("Network error")
            # All others return empty
            return {"observations": []}

        mock_get_json.side_effect = side_effect

        result = self.fetcher.get_indicators()

        # fed_funds_rate should still be present
        self.assertIn("fed_funds_rate", result)
        # cpi_yoy should NOT be present (failed)
        self.assertNotIn("cpi_yoy", result)

    @patch.object(FREDMacroFetcher, "_get_json")
    def test_returns_empty_dict_on_total_failure(self, mock_get_json):
        """Returns empty dict when all series fail."""
        mock_get_json.side_effect = Exception("Total failure")

        result = self.fetcher.get_indicators()
        self.assertEqual(result, {})

    @patch.object(FREDMacroFetcher, "_get_json")
    def test_single_observation_no_previous(self, mock_get_json):
        """Single observation means no previous_value and no change."""

        def side_effect(url, **kwargs):
            params = kwargs.get("params", {})
            series_id = params.get("series_id", "")
            if series_id == "VIXCLS":
                return {
                    "observations": [
                        {"date": "2026-04-07", "value": "18.50"},
                    ]
                }
            return {"observations": []}

        mock_get_json.side_effect = side_effect

        result = self.fetcher.get_indicators()

        self.assertIn("vix", result)
        vix = result["vix"]
        self.assertAlmostEqual(vix.value, 18.50)
        self.assertIsNone(vix.previous_value)
        self.assertIsNone(vix.change)

    @patch.object(FREDMacroFetcher, "_get_json")
    def test_dot_value_skipped(self, mock_get_json):
        """FRED uses '.' for missing values; these observations should be skipped."""

        def side_effect(url, **kwargs):
            params = kwargs.get("params", {})
            series_id = params.get("series_id", "")
            if series_id == "DGS2":
                return {
                    "observations": [
                        {"date": "2026-04-07", "value": "."},
                    ]
                }
            return {"observations": []}

        mock_get_json.side_effect = side_effect

        result = self.fetcher.get_indicators()
        # DGS2 with value "." should be skipped
        self.assertNotIn("treasury_2y", result)

    def test_name(self):
        self.assertEqual(self.fetcher.name, "fred")

    @patch.dict(os.environ, {}, clear=True)
    def test_get_indicators_without_key_returns_empty(self):
        os.environ.pop("FRED_API_KEY", None)
        fetcher = FREDMacroFetcher()
        result = fetcher.get_indicators()
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
