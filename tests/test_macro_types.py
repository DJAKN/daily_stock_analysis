# -*- coding: utf-8 -*-
"""Tests for macro data types: MacroIndicator, EconEvent, UnifiedMacroSnapshot."""

import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.macro.types import MacroIndicator, EconEvent, UnifiedMacroSnapshot


class TestMacroIndicator(unittest.TestCase):
    """MacroIndicator creation and field access."""

    def test_creation(self):
        ind = MacroIndicator(
            name="fed_funds_rate",
            display_name="Federal Funds Rate",
            value=5.33,
            previous_value=5.50,
            change=-0.17,
            unit="%",
            as_of_date="2026-03-01",
            source="fred",
        )
        self.assertEqual(ind.name, "fed_funds_rate")
        self.assertEqual(ind.display_name, "Federal Funds Rate")
        self.assertAlmostEqual(ind.value, 5.33)
        self.assertAlmostEqual(ind.previous_value, 5.50)
        self.assertAlmostEqual(ind.change, -0.17)
        self.assertEqual(ind.unit, "%")
        self.assertEqual(ind.as_of_date, "2026-03-01")
        self.assertEqual(ind.source, "fred")

    def test_optional_fields_accept_none(self):
        ind = MacroIndicator(
            name="vix",
            display_name="CBOE VIX",
            value=18.5,
            previous_value=None,
            change=None,
            unit="index",
            as_of_date="2026-04-01",
            source="fred",
        )
        self.assertIsNone(ind.previous_value)
        self.assertIsNone(ind.change)


class TestEconEvent(unittest.TestCase):
    """EconEvent creation with defaults."""

    def test_creation_with_all_fields(self):
        ev = EconEvent(
            event="FOMC Meeting",
            date="2026-04-15",
            impact="high",
            estimate=5.25,
            previous=5.50,
        )
        self.assertEqual(ev.event, "FOMC Meeting")
        self.assertEqual(ev.date, "2026-04-15")
        self.assertEqual(ev.impact, "high")
        self.assertAlmostEqual(ev.estimate, 5.25)
        self.assertAlmostEqual(ev.previous, 5.50)

    def test_defaults(self):
        ev = EconEvent(
            event="CPI Release",
            date="2026-04-10",
            impact="high",
        )
        self.assertIsNone(ev.estimate)
        self.assertIsNone(ev.previous)


class TestUnifiedMacroSnapshot(unittest.TestCase):
    """UnifiedMacroSnapshot creation and serialization."""

    def _make_snapshot(self):
        indicator = MacroIndicator(
            name="fed_funds_rate",
            display_name="Federal Funds Rate",
            value=5.33,
            previous_value=5.50,
            change=-0.17,
            unit="%",
            as_of_date="2026-03-01",
            source="fred",
        )
        event = EconEvent(
            event="FOMC Meeting",
            date="2026-04-15",
            impact="high",
            estimate=5.25,
            previous=5.50,
        )
        return UnifiedMacroSnapshot(
            timestamp=datetime(2026, 4, 8, 12, 0, 0),
            indicators={"fed_funds_rate": indicator},
            upcoming_events=[event],
            market_regime="risk_off",
        )

    def test_creation(self):
        snap = self._make_snapshot()
        self.assertEqual(snap.timestamp, datetime(2026, 4, 8, 12, 0, 0))
        self.assertIn("fed_funds_rate", snap.indicators)
        self.assertEqual(len(snap.upcoming_events), 1)
        self.assertEqual(snap.market_regime, "risk_off")

    def test_to_dict_serialization(self):
        snap = self._make_snapshot()
        d = snap.to_dict()

        # Top-level keys
        self.assertIn("timestamp", d)
        self.assertIn("indicators", d)
        self.assertIn("upcoming_events", d)
        self.assertIn("market_regime", d)
        self.assertEqual(d["market_regime"], "risk_off")

        # Indicators serialized as dict of dicts
        self.assertIn("fed_funds_rate", d["indicators"])
        ind_dict = d["indicators"]["fed_funds_rate"]
        self.assertEqual(ind_dict["name"], "fed_funds_rate")
        self.assertAlmostEqual(ind_dict["value"], 5.33)

        # Events serialized as list of dicts
        self.assertIsInstance(d["upcoming_events"], list)
        self.assertEqual(len(d["upcoming_events"]), 1)
        ev_dict = d["upcoming_events"][0]
        self.assertEqual(ev_dict["event"], "FOMC Meeting")
        self.assertEqual(ev_dict["impact"], "high")

    def test_to_dict_with_empty_collections(self):
        snap = UnifiedMacroSnapshot(
            timestamp=datetime(2026, 4, 8),
            indicators={},
            upcoming_events=[],
            market_regime="neutral",
        )
        d = snap.to_dict()
        self.assertEqual(d["indicators"], {})
        self.assertEqual(d["upcoming_events"], [])
        self.assertEqual(d["market_regime"], "neutral")


if __name__ == "__main__":
    unittest.main()
