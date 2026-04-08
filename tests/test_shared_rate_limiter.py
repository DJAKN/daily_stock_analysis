# -*- coding: utf-8 -*-
"""
Tests for SharedRateLimiter and RateLimit.
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.shared.rate_limiter import RateLimit, SharedRateLimiter


class TestRateLimit(unittest.TestCase):
    def test_period_seconds_second(self) -> None:
        rl = RateLimit(max_calls=5, period="second")
        self.assertEqual(rl.period_seconds, 1)

    def test_period_seconds_minute(self) -> None:
        rl = RateLimit(max_calls=60, period="minute")
        self.assertEqual(rl.period_seconds, 60)

    def test_period_seconds_day(self) -> None:
        rl = RateLimit(max_calls=1000, period="day")
        self.assertEqual(rl.period_seconds, 86400)

    def test_period_seconds_invalid_raises(self) -> None:
        rl = RateLimit(max_calls=5, period="hour")
        with self.assertRaises(ValueError):
            _ = rl.period_seconds


class TestSharedRateLimiter(unittest.TestCase):
    def test_acquire_within_budget_succeeds(self) -> None:
        limiter = SharedRateLimiter()
        limiter.configure("fmp", RateLimit(max_calls=3, period="second"))
        self.assertTrue(limiter.acquire("fmp"))
        self.assertTrue(limiter.acquire("fmp"))
        self.assertTrue(limiter.acquire("fmp"))

    def test_acquire_exceeding_budget_returns_false(self) -> None:
        limiter = SharedRateLimiter()
        limiter.configure("fmp", RateLimit(max_calls=2, period="second"))
        self.assertTrue(limiter.acquire("fmp"))
        self.assertTrue(limiter.acquire("fmp"))
        self.assertFalse(limiter.acquire("fmp"))

    def test_unconfigured_provider_always_allowed(self) -> None:
        limiter = SharedRateLimiter()
        for _ in range(100):
            self.assertTrue(limiter.acquire("unknown_provider"))

    def test_remaining_returns_correct_count(self) -> None:
        limiter = SharedRateLimiter()
        limiter.configure("fmp", RateLimit(max_calls=5, period="second"))
        self.assertEqual(limiter.remaining("fmp"), 5)
        limiter.acquire("fmp")
        self.assertEqual(limiter.remaining("fmp"), 4)
        limiter.acquire("fmp")
        self.assertEqual(limiter.remaining("fmp"), 3)

    def test_remaining_unconfigured_returns_max(self) -> None:
        limiter = SharedRateLimiter()
        # Unconfigured providers should report unlimited remaining
        self.assertEqual(limiter.remaining("unknown"), float("inf"))

    def test_day_period_budget_works(self) -> None:
        limiter = SharedRateLimiter()
        limiter.configure("fred", RateLimit(max_calls=3, period="day"))
        self.assertTrue(limiter.acquire("fred"))
        self.assertTrue(limiter.acquire("fred"))
        self.assertTrue(limiter.acquire("fred"))
        self.assertFalse(limiter.acquire("fred"))
        self.assertEqual(limiter.remaining("fred"), 0)


if __name__ == "__main__":
    unittest.main()
