# -*- coding: utf-8 -*-
"""Tests for UnifiedFundamentalData dataclass."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.fundamental.types import UnifiedFundamentalData


class TestDefaults(unittest.TestCase):
    """All optional fields default to None."""

    def test_defaults_to_none(self):
        data = UnifiedFundamentalData(code="AAPL", source="fmp")
        self.assertEqual(data.code, "AAPL")
        self.assertEqual(data.source, "fmp")
        self.assertIsNone(data.pe_ratio)
        self.assertIsNone(data.forward_pe)
        self.assertIsNone(data.pb_ratio)
        self.assertIsNone(data.ps_ratio)
        self.assertIsNone(data.peg_ratio)
        self.assertIsNone(data.ev_ebitda)
        self.assertIsNone(data.eps_ttm)
        self.assertIsNone(data.eps_estimate)
        self.assertIsNone(data.revenue_ttm)
        self.assertIsNone(data.earnings_date)
        self.assertIsNone(data.earnings_surprise)
        self.assertIsNone(data.profit_margin)
        self.assertIsNone(data.operating_margin)
        self.assertIsNone(data.roe)
        self.assertIsNone(data.roa)
        self.assertIsNone(data.debt_to_equity)
        self.assertIsNone(data.current_ratio)
        self.assertIsNone(data.free_cash_flow)
        self.assertIsNone(data.dividend_yield)
        self.assertIsNone(data.payout_ratio)
        self.assertIsNone(data.insider_buy_count_90d)
        self.assertIsNone(data.insider_sell_count_90d)
        self.assertIsNone(data.institutional_ownership_pct)
        self.assertIsNone(data.short_interest_pct)


class TestToDict(unittest.TestCase):
    """to_dict filters out None values."""

    def test_only_non_none_fields(self):
        data = UnifiedFundamentalData(
            code="AAPL", source="fmp", pe_ratio=25.3, roe=0.15
        )
        d = data.to_dict()
        self.assertEqual(d["code"], "AAPL")
        self.assertEqual(d["source"], "fmp")
        self.assertAlmostEqual(d["pe_ratio"], 25.3)
        self.assertAlmostEqual(d["roe"], 0.15)
        self.assertNotIn("pb_ratio", d)
        self.assertNotIn("forward_pe", d)
        self.assertNotIn("eps_ttm", d)

    def test_to_dict_includes_code_and_source(self):
        data = UnifiedFundamentalData(code="TSLA", source="finnhub")
        d = data.to_dict()
        self.assertEqual(d["code"], "TSLA")
        self.assertEqual(d["source"], "finnhub")
        # Only code and source should be present
        self.assertEqual(len(d), 2)


class TestHasValuationData(unittest.TestCase):
    """has_valuation_data returns True if any valuation field is non-None."""

    def test_no_valuation_data(self):
        data = UnifiedFundamentalData(code="AAPL", source="fmp")
        self.assertFalse(data.has_valuation_data())

    def test_has_pe_ratio(self):
        data = UnifiedFundamentalData(code="AAPL", source="fmp", pe_ratio=25.0)
        self.assertTrue(data.has_valuation_data())

    def test_has_forward_pe(self):
        data = UnifiedFundamentalData(code="AAPL", source="fmp", forward_pe=20.0)
        self.assertTrue(data.has_valuation_data())

    def test_has_pb_ratio(self):
        data = UnifiedFundamentalData(code="AAPL", source="fmp", pb_ratio=5.0)
        self.assertTrue(data.has_valuation_data())

    def test_has_ev_ebitda(self):
        data = UnifiedFundamentalData(code="AAPL", source="fmp", ev_ebitda=18.0)
        self.assertTrue(data.has_valuation_data())

    def test_non_valuation_fields_dont_count(self):
        data = UnifiedFundamentalData(code="AAPL", source="fmp", roe=0.2, eps_ttm=5.0)
        self.assertFalse(data.has_valuation_data())


class TestMerge(unittest.TestCase):
    """merge prefers non-None from self, fills gaps from other."""

    def test_self_takes_priority(self):
        a = UnifiedFundamentalData(code="AAPL", source="fmp", pe_ratio=25.0, roe=0.15)
        b = UnifiedFundamentalData(code="AAPL", source="finnhub", pe_ratio=26.0, pb_ratio=5.0)
        merged = a.merge(b)
        # Self's pe_ratio wins
        self.assertAlmostEqual(merged.pe_ratio, 25.0)
        # Self's roe is kept
        self.assertAlmostEqual(merged.roe, 0.15)
        # Other's pb_ratio fills the gap
        self.assertAlmostEqual(merged.pb_ratio, 5.0)
        # Merged keeps self's source
        self.assertEqual(merged.source, "fmp")
        self.assertEqual(merged.code, "AAPL")

    def test_merge_fills_all_gaps(self):
        a = UnifiedFundamentalData(code="AAPL", source="fmp", pe_ratio=25.0)
        b = UnifiedFundamentalData(
            code="AAPL", source="finnhub",
            pb_ratio=5.0, eps_ttm=6.0, dividend_yield=0.006,
            insider_buy_count_90d=3,
        )
        merged = a.merge(b)
        self.assertAlmostEqual(merged.pe_ratio, 25.0)
        self.assertAlmostEqual(merged.pb_ratio, 5.0)
        self.assertAlmostEqual(merged.eps_ttm, 6.0)
        self.assertAlmostEqual(merged.dividend_yield, 0.006)
        self.assertEqual(merged.insider_buy_count_90d, 3)

    def test_merge_returns_new_instance(self):
        a = UnifiedFundamentalData(code="AAPL", source="fmp", pe_ratio=25.0)
        b = UnifiedFundamentalData(code="AAPL", source="finnhub", pb_ratio=5.0)
        merged = a.merge(b)
        self.assertIsNot(merged, a)
        self.assertIsNot(merged, b)

    def test_merge_with_empty_other(self):
        a = UnifiedFundamentalData(code="AAPL", source="fmp", pe_ratio=25.0, roe=0.15)
        b = UnifiedFundamentalData(code="AAPL", source="finnhub")
        merged = a.merge(b)
        self.assertAlmostEqual(merged.pe_ratio, 25.0)
        self.assertAlmostEqual(merged.roe, 0.15)


if __name__ == "__main__":
    unittest.main()
