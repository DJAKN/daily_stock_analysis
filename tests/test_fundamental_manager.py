# -*- coding: utf-8 -*-
"""Tests for FundamentalManager failover and cache integration."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.fundamental.types import UnifiedFundamentalData
from data_provider.fundamental.manager import FundamentalManager


def _make_data(source="test_provider", code="AAPL", **kwargs):
    """Helper to build a UnifiedFundamentalData for tests."""
    return UnifiedFundamentalData(code=code, source=source, **kwargs)


def _mock_fetcher(name="mock", priority=0, available=True, result=None, side_effect=None):
    """Create a MagicMock that mimics BaseFundamentalFetcher."""
    fetcher = MagicMock()
    fetcher.name = name
    fetcher.priority = priority
    fetcher.is_available.return_value = available
    if side_effect is not None:
        fetcher.get_fundamentals.side_effect = side_effect
    else:
        fetcher.get_fundamentals.return_value = result
    return fetcher


class TestPrimarySuccess(unittest.TestCase):
    """Primary fetcher succeeds — secondary should never be called."""

    def test_primary_success_skips_secondary(self):
        data = _make_data(source="primary")
        primary = _mock_fetcher(name="primary", priority=0, result=data)
        secondary = _mock_fetcher(name="secondary", priority=1, result=_make_data(source="secondary"))

        mgr = FundamentalManager(fetchers=[primary, secondary])
        result = mgr.get_fundamentals("AAPL")

        self.assertIsNotNone(result)
        self.assertEqual(result.source, "primary")
        primary.get_fundamentals.assert_called_once_with("AAPL")
        secondary.get_fundamentals.assert_not_called()


class TestFailover(unittest.TestCase):
    """Failover when primary returns None."""

    def test_failover_on_primary_failure(self):
        primary = _mock_fetcher(name="primary", priority=0, result=None)
        secondary = _mock_fetcher(name="secondary", priority=1, result=_make_data(source="secondary"))

        mgr = FundamentalManager(fetchers=[primary, secondary])
        result = mgr.get_fundamentals("AAPL")

        self.assertIsNotNone(result)
        self.assertEqual(result.source, "secondary")
        primary.get_fundamentals.assert_called_once()
        secondary.get_fundamentals.assert_called_once()


class TestAllFail(unittest.TestCase):
    """All fetchers fail — returns None."""

    def test_all_fail_returns_none(self):
        fetcher = _mock_fetcher(name="only", priority=0, result=None)

        mgr = FundamentalManager(fetchers=[fetcher])
        result = mgr.get_fundamentals("AAPL")

        self.assertIsNone(result)


class TestSkipUnavailable(unittest.TestCase):
    """Unavailable fetcher should be skipped."""

    def test_skip_unavailable_fetcher(self):
        unavailable = _mock_fetcher(name="unavailable", priority=0, available=False)
        available = _mock_fetcher(name="available", priority=1, result=_make_data(source="available"))

        mgr = FundamentalManager(fetchers=[unavailable, available])
        result = mgr.get_fundamentals("AAPL")

        self.assertIsNotNone(result)
        self.assertEqual(result.source, "available")
        unavailable.get_fundamentals.assert_not_called()
        available.get_fundamentals.assert_called_once()


class TestExceptionFailover(unittest.TestCase):
    """Exception from a fetcher triggers failover to next."""

    def test_exception_triggers_failover(self):
        failing = _mock_fetcher(name="failing", priority=0, side_effect=RuntimeError("boom"))
        backup = _mock_fetcher(name="backup", priority=1, result=_make_data(source="backup"))

        mgr = FundamentalManager(fetchers=[failing, backup])
        result = mgr.get_fundamentals("AAPL")

        self.assertIsNotNone(result)
        self.assertEqual(result.source, "backup")
        failing.get_fundamentals.assert_called_once()
        backup.get_fundamentals.assert_called_once()


class TestStaleCacheFallback(unittest.TestCase):
    """All fetchers fail — stale cache entry used as fallback."""

    def test_stale_cache_fallback(self):
        fetcher = _mock_fetcher(name="only", priority=0, result=None)

        cache = MagicMock()
        cache.get_stale.return_value = {
            "data": {"code": "AAPL", "source": "cached_provider", "pe_ratio": 25.0},
            "stale": True,
        }

        mgr = FundamentalManager(fetchers=[fetcher], cache=cache)
        result = mgr.get_fundamentals("AAPL")

        self.assertIsNotNone(result)
        self.assertEqual(result.code, "AAPL")
        self.assertEqual(result.source, "cached_provider")
        self.assertEqual(result.pe_ratio, 25.0)
        cache.get_stale.assert_called_once()


class TestCacheOnSuccess(unittest.TestCase):
    """Successful fetch stores result in cache."""

    def test_cache_updated_on_success(self):
        data = _make_data(source="fmp", pe_ratio=30.0, earnings_date="2026-05-01")
        fetcher = _mock_fetcher(name="fmp", priority=0, result=data)
        cache = MagicMock()

        mgr = FundamentalManager(fetchers=[fetcher], cache=cache)
        mgr.get_fundamentals("AAPL")

        cache.put.assert_called_once()
        call_args = cache.put.call_args
        self.assertIn("fund:AAPL:latest", call_args[0] if call_args[0] else [call_args[1].get("key")])


class TestCircuitBreakerIntegration(unittest.TestCase):
    """Circuit breaker skips circuit-broken fetchers."""

    def test_circuit_broken_fetcher_skipped(self):
        broken = _mock_fetcher(name="broken", priority=0, result=_make_data(source="broken"))
        healthy = _mock_fetcher(name="healthy", priority=1, result=_make_data(source="healthy"))

        cb = MagicMock()
        # broken is circuit-broken, healthy is available
        cb.is_available.side_effect = lambda src: src != "broken"

        mgr = FundamentalManager(fetchers=[broken, healthy], circuit_breaker=cb)
        result = mgr.get_fundamentals("AAPL")

        self.assertIsNotNone(result)
        self.assertEqual(result.source, "healthy")
        broken.get_fundamentals.assert_not_called()
        healthy.get_fundamentals.assert_called_once()

    def test_circuit_breaker_records_success(self):
        data = _make_data(source="fmp")
        fetcher = _mock_fetcher(name="fmp", priority=0, result=data)

        cb = MagicMock()
        cb.is_available.return_value = True

        mgr = FundamentalManager(fetchers=[fetcher], circuit_breaker=cb)
        mgr.get_fundamentals("AAPL")

        cb.record_success.assert_called_once_with("fmp")

    def test_circuit_breaker_records_failure_on_exception(self):
        fetcher = _mock_fetcher(name="fmp", priority=0, side_effect=RuntimeError("fail"))

        cb = MagicMock()
        cb.is_available.return_value = True

        mgr = FundamentalManager(fetchers=[fetcher], circuit_breaker=cb)
        mgr.get_fundamentals("AAPL")

        cb.record_failure.assert_called_once()
        self.assertEqual(cb.record_failure.call_args[0][0], "fmp")

    def test_circuit_breaker_records_inconclusive_on_none(self):
        fetcher = _mock_fetcher(name="fmp", priority=0, result=None)

        cb = MagicMock()
        cb.is_available.return_value = True

        mgr = FundamentalManager(fetchers=[fetcher], circuit_breaker=cb)
        mgr.get_fundamentals("AAPL")

        cb.record_inconclusive.assert_called_once_with("fmp")


class TestPrioritySorting(unittest.TestCase):
    """Fetchers are tried in priority order regardless of input order."""

    def test_fetchers_sorted_by_priority(self):
        low_prio = _mock_fetcher(name="low", priority=5, result=_make_data(source="low"))
        high_prio = _mock_fetcher(name="high", priority=0, result=_make_data(source="high"))

        # Pass in wrong order
        mgr = FundamentalManager(fetchers=[low_prio, high_prio])
        result = mgr.get_fundamentals("AAPL")

        self.assertEqual(result.source, "high")
        low_prio.get_fundamentals.assert_not_called()


if __name__ == "__main__":
    unittest.main()
