# -*- coding: utf-8 -*-
"""Tests for MacroManager."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from data_provider.macro.types import MacroIndicator, EconEvent, UnifiedMacroSnapshot
from data_provider.macro.manager import MacroManager


def _make_indicator(name, value, unit="%", source="fred"):
    return MacroIndicator(
        name=name,
        display_name=name.replace("_", " ").title(),
        value=value,
        previous_value=None,
        change=None,
        unit=unit,
        as_of_date="2026-04-08",
        source=source,
    )


def _make_event(event_name="FOMC Meeting", date="2026-04-15", impact="high"):
    return EconEvent(event=event_name, date=date, impact=impact)


class TestMacroManagerCombines:
    """combines indicators and events -- FRED returns indicators, Finnhub returns events."""

    def test_combines_indicators_and_events(self):
        indicator_fetcher = MagicMock()
        indicator_fetcher.get_indicators.return_value = {
            "vix": _make_indicator("vix", 20.0, unit="index"),
            "yield_spread": _make_indicator("yield_spread", 0.3),
        }

        calendar_fetcher = MagicMock()
        calendar_fetcher.get_economic_calendar.return_value = [
            _make_event("FOMC Meeting", "2026-04-15", "high"),
            _make_event("CPI Release", "2026-04-20", "medium"),
        ]

        mgr = MacroManager(
            indicator_fetchers=[indicator_fetcher],
            calendar_fetchers=[calendar_fetcher],
        )
        snapshot = mgr.get_snapshot()

        assert snapshot is not None
        assert isinstance(snapshot, UnifiedMacroSnapshot)
        assert "vix" in snapshot.indicators
        assert "yield_spread" in snapshot.indicators
        assert len(snapshot.upcoming_events) == 2
        assert snapshot.upcoming_events[0].event == "FOMC Meeting"


class TestMarketRegimeRiskOff:
    """market regime risk_off -- VIX > 25 -> risk_off."""

    def test_vix_above_25(self):
        indicator_fetcher = MagicMock()
        indicator_fetcher.get_indicators.return_value = {
            "vix": _make_indicator("vix", 30.0, unit="index"),
            "yield_spread": _make_indicator("yield_spread", 0.5),
        }

        mgr = MacroManager(
            indicator_fetchers=[indicator_fetcher],
            calendar_fetchers=[],
        )
        snapshot = mgr.get_snapshot()

        assert snapshot is not None
        assert snapshot.market_regime == "risk_off"

    def test_negative_yield_spread(self):
        indicator_fetcher = MagicMock()
        indicator_fetcher.get_indicators.return_value = {
            "vix": _make_indicator("vix", 20.0, unit="index"),
            "yield_spread": _make_indicator("yield_spread", -0.3),
        }

        mgr = MacroManager(
            indicator_fetchers=[indicator_fetcher],
            calendar_fetchers=[],
        )
        snapshot = mgr.get_snapshot()

        assert snapshot is not None
        assert snapshot.market_regime == "risk_off"


class TestMarketRegimeRiskOn:
    """market regime risk_on -- VIX < 15, spread > 0.5 -> risk_on."""

    def test_risk_on(self):
        indicator_fetcher = MagicMock()
        indicator_fetcher.get_indicators.return_value = {
            "vix": _make_indicator("vix", 12.0, unit="index"),
            "yield_spread": _make_indicator("yield_spread", 1.0),
        }

        mgr = MacroManager(
            indicator_fetchers=[indicator_fetcher],
            calendar_fetchers=[],
        )
        snapshot = mgr.get_snapshot()

        assert snapshot is not None
        assert snapshot.market_regime == "risk_on"


class TestMarketRegimeNeutral:
    """market regime neutral -- moderate values -> neutral."""

    def test_moderate_vix_and_spread(self):
        indicator_fetcher = MagicMock()
        indicator_fetcher.get_indicators.return_value = {
            "vix": _make_indicator("vix", 18.0, unit="index"),
            "yield_spread": _make_indicator("yield_spread", 0.3),
        }

        mgr = MacroManager(
            indicator_fetchers=[indicator_fetcher],
            calendar_fetchers=[],
        )
        snapshot = mgr.get_snapshot()

        assert snapshot is not None
        assert snapshot.market_regime == "neutral"

    def test_missing_indicators_defaults_neutral(self):
        """No VIX or spread available -> neutral."""
        indicator_fetcher = MagicMock()
        indicator_fetcher.get_indicators.return_value = {
            "fed_funds_rate": _make_indicator("fed_funds_rate", 5.33),
        }
        calendar_fetcher = MagicMock()
        calendar_fetcher.get_economic_calendar.return_value = [_make_event()]

        mgr = MacroManager(
            indicator_fetchers=[indicator_fetcher],
            calendar_fetchers=[calendar_fetcher],
        )
        snapshot = mgr.get_snapshot()

        assert snapshot is not None
        assert snapshot.market_regime == "neutral"


class TestAllFailReturnsNone:
    """all fail returns None -- all fetchers raise -> None."""

    def test_all_fetchers_raise(self):
        indicator_fetcher = MagicMock()
        indicator_fetcher.get_indicators.side_effect = Exception("FRED down")

        calendar_fetcher = MagicMock()
        calendar_fetcher.get_economic_calendar.side_effect = Exception("Finnhub down")

        mgr = MacroManager(
            indicator_fetchers=[indicator_fetcher],
            calendar_fetchers=[calendar_fetcher],
        )
        snapshot = mgr.get_snapshot()

        assert snapshot is None

    def test_all_return_empty(self):
        indicator_fetcher = MagicMock()
        indicator_fetcher.get_indicators.return_value = {}

        calendar_fetcher = MagicMock()
        calendar_fetcher.get_economic_calendar.return_value = []

        mgr = MacroManager(
            indicator_fetchers=[indicator_fetcher],
            calendar_fetchers=[calendar_fetcher],
        )
        snapshot = mgr.get_snapshot()

        assert snapshot is None

    def test_no_fetchers_at_all(self):
        mgr = MacroManager(indicator_fetchers=[], calendar_fetchers=[])
        snapshot = mgr.get_snapshot()

        assert snapshot is None


class TestPartialFailure:
    """partial failure still works -- indicator fetcher fails, calendar works."""

    def test_indicator_fails_calendar_works(self):
        indicator_fetcher = MagicMock()
        indicator_fetcher.get_indicators.side_effect = Exception("FRED down")

        calendar_fetcher = MagicMock()
        calendar_fetcher.get_economic_calendar.return_value = [
            _make_event("FOMC Meeting"),
        ]

        mgr = MacroManager(
            indicator_fetchers=[indicator_fetcher],
            calendar_fetchers=[calendar_fetcher],
        )
        snapshot = mgr.get_snapshot()

        assert snapshot is not None
        assert len(snapshot.indicators) == 0
        assert len(snapshot.upcoming_events) == 1
        assert snapshot.market_regime == "neutral"

    def test_calendar_fails_indicator_works(self):
        indicator_fetcher = MagicMock()
        indicator_fetcher.get_indicators.return_value = {
            "vix": _make_indicator("vix", 30.0, unit="index"),
        }

        calendar_fetcher = MagicMock()
        calendar_fetcher.get_economic_calendar.side_effect = Exception("Finnhub down")

        mgr = MacroManager(
            indicator_fetchers=[indicator_fetcher],
            calendar_fetchers=[calendar_fetcher],
        )
        snapshot = mgr.get_snapshot()

        assert snapshot is not None
        assert "vix" in snapshot.indicators
        assert len(snapshot.upcoming_events) == 0

    def test_multiple_indicator_fetchers_first_non_none_wins(self):
        fetcher_a = MagicMock()
        fetcher_a.get_indicators.return_value = {
            "vix": _make_indicator("vix", 20.0, unit="index", source="fred"),
            "yield_spread": _make_indicator("yield_spread", 0.5, source="fred"),
        }

        fetcher_b = MagicMock()
        fetcher_b.get_indicators.return_value = {
            "vix": _make_indicator("vix", 99.0, unit="index", source="backup"),
            "unemployment": _make_indicator("unemployment", 4.0, source="backup"),
        }

        mgr = MacroManager(
            indicator_fetchers=[fetcher_a, fetcher_b],
            calendar_fetchers=[],
        )
        snapshot = mgr.get_snapshot()

        assert snapshot is not None
        # First non-None wins: fetcher_a's VIX should be kept
        assert snapshot.indicators["vix"].value == 20.0
        # But fetcher_b's unique key should be added
        assert snapshot.indicators["unemployment"].value == 4.0
