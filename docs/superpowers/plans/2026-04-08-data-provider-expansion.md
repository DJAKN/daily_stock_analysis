# Data Provider Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FundamentalManager, NewsManager, and MacroManager to the data provider layer, backed by FMP, Finnhub, FRED, Alpha Vantage, and SEC EDGAR freemium APIs, with cross-run persistence via `actions/cache`.

**Architecture:** Category Managers pattern — three new manager classes alongside the existing `DataFetcherManager`, each with its own fetcher chain, failover, and circuit breaker. Shared rate limiter prevents cross-manager quota collisions. All new managers are optional; failures return `None` and the pipeline continues.

**Tech Stack:** Python 3.11, requests, SQLite (stdlib), tenacity (existing dep), pytest, unittest.mock

**Branch:** All work on a dedicated dev branch `feat/data-provider-expansion` created from the latest `main`.

**Spec:** `docs/superpowers/specs/2026-04-08-data-provider-expansion-design.md`

---

## File Structure

```
data_provider/
├── shared/                        # Task 2: Shared infrastructure
│   ├── __init__.py
│   ├── rate_limiter.py            # Token-bucket per-provider rate limiter
│   └── cache.py                   # SQLite-backed persistent cache
│
├── fundamental/                   # Tasks 3-4: Fundamental data
│   ├── __init__.py
│   ├── base.py                    # BaseFundamentalFetcher ABC
│   ├── types.py                   # UnifiedFundamentalData dataclass
│   ├── fmp_fetcher.py             # FMP provider (primary)
│   ├── finnhub_fetcher.py         # Finnhub provider (secondary)
│   ├── alpha_vantage_fetcher.py   # Alpha Vantage provider (fallback)
│   ├── edgar_fetcher.py           # SEC EDGAR provider (last resort)
│   └── manager.py                 # FundamentalManager orchestration
│
├── news/                          # Tasks 5-6: Financial news
│   ├── __init__.py
│   ├── base.py                    # BaseNewsFetcher ABC
│   ├── types.py                   # UnifiedNewsItem, NewsEventType
│   ├── finnhub_fetcher.py         # Finnhub news (primary)
│   ├── fmp_fetcher.py             # FMP news (secondary)
│   ├── edgar_fetcher.py           # SEC EDGAR filings
│   ├── search_adapter.py          # Wraps existing search_service.py
│   └── manager.py                 # NewsManager (dedup + scoring)
│
├── macro/                         # Tasks 7-8: Macro data
│   ├── __init__.py
│   ├── base.py                    # BaseMacroFetcher ABC
│   ├── types.py                   # MacroIndicator, EconEvent, UnifiedMacroSnapshot
│   ├── fred_fetcher.py            # FRED API (primary)
│   ├── finnhub_fetcher.py         # Finnhub economic calendar
│   └── manager.py                 # MacroManager

tests/
├── test_shared_rate_limiter.py    # Task 2
├── test_shared_cache.py           # Task 2
├── test_fundamental_types.py      # Task 3
├── test_fundamental_fmp.py        # Task 3
├── test_fundamental_finnhub.py    # Task 3
├── test_fundamental_manager.py    # Task 4
├── test_news_types.py             # Task 5
├── test_news_finnhub.py           # Task 5
├── test_news_manager.py           # Task 6
├── test_macro_types.py            # Task 7
├── test_macro_fred.py             # Task 7
├── test_macro_manager.py          # Task 8

.github/workflows/daily_analysis.yml  # Task 1: actions/cache + env vars
.env.example                           # Task 10: config docs
src/config.py                          # Task 9: new config fields
src/core/pipeline.py                   # Task 9: pipeline integration
```

---

## Task 0: Create dev branch

**Files:**
- None (git operation only)

- [ ] **Step 1: Fetch latest main and create dev branch from it**

```bash
git fetch origin main
git checkout -b feat/data-provider-expansion origin/main
```

- [ ] **Step 2: Verify branch**

Run: `git branch --show-current`
Expected: `feat/data-provider-expansion`

- [ ] **Step 3: Verify clean baseline**

Run: `python -m pytest tests/ -m "not network" --timeout=60 -x -q`
Expected: All existing tests pass — this is the baseline before any changes

---

## Task 1: Enable cross-run persistence in GitHub Actions

**Files:**
- Modify: `.github/workflows/daily_analysis.yml`

- [ ] **Step 1: Add `actions/cache` step to workflow**

In `.github/workflows/daily_analysis.yml`, add the following step **after** "创建必要目录" and **before** "执行股票分析":

```yaml
      - name: Restore analysis data cache
        uses: actions/cache@v4
        with:
          path: data/
          key: analysis-data-${{ runner.os }}
```

- [ ] **Step 2: Add new provider env vars to the workflow**

In the `env:` block of the "执行股票分析" step, add a new section after the `# 搜索服务` block:

```yaml
          # ==========================================
          # 数据源 (Data Providers)
          # ==========================================
          FMP_API_KEY: ${{ secrets.FMP_API_KEY }}
          FINNHUB_API_KEY: ${{ secrets.FINNHUB_API_KEY }}
          ALPHA_VANTAGE_API_KEY: ${{ secrets.ALPHA_VANTAGE_API_KEY }}
          FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
          SEC_EDGAR_USER_AGENT: ${{ vars.SEC_EDGAR_USER_AGENT || secrets.SEC_EDGAR_USER_AGENT }}
```

- [ ] **Step 3: Add provider status to config check output**

In the config check `echo` block, after the existing `【数据源】` section, add:

```bash
          echo "  FMP: $([ -n "$FMP_API_KEY" ] && echo '✅ 已配置' || echo '⚪ 未配置')"
          echo "  Finnhub: $([ -n "$FINNHUB_API_KEY" ] && echo '✅ 已配置' || echo '⚪ 未配置')"
          echo "  Alpha Vantage: $([ -n "$ALPHA_VANTAGE_API_KEY" ] && echo '✅ 已配置' || echo '⚪ 未配置')"
          echo "  FRED: $([ -n "$FRED_API_KEY" ] && echo '✅ 已配置' || echo '⚪ 未配置')"
          echo "  SEC EDGAR: ✅ 免密钥（仅需 User-Agent）"
```

- [ ] **Step 4: Validate YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/daily_analysis.yml'))"`
Expected: No error

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/daily_analysis.yml
git commit -m "feat: enable cross-run data persistence and add provider env vars"
```

- [ ] **Step 6: Regression check — verify no existing tests broken**

Run: `python -m pytest tests/ -m "not network" --timeout=60 -x -q`
Expected: All existing tests still pass (workflow-only change should not affect any test)

---

## Task 2: Shared infrastructure — rate limiter and cache

**Files:**
- Create: `data_provider/shared/__init__.py`
- Create: `data_provider/shared/rate_limiter.py`
- Create: `data_provider/shared/cache.py`
- Create: `tests/test_shared_rate_limiter.py`
- Create: `tests/test_shared_cache.py`

- [ ] **Step 1: Write rate limiter test**

Create `tests/test_shared_rate_limiter.py`:

```python
# -*- coding: utf-8 -*-
"""Tests for shared rate limiter."""

import time
import unittest

from data_provider.shared.rate_limiter import RateLimit, SharedRateLimiter


class TestRateLimit(unittest.TestCase):
    def test_acquire_within_budget(self):
        limiter = SharedRateLimiter()
        limiter.configure("test_provider", RateLimit(max_calls=5, period="minute"))
        for _ in range(5):
            self.assertTrue(limiter.acquire("test_provider"))

    def test_acquire_exceeds_budget(self):
        limiter = SharedRateLimiter()
        limiter.configure("test_provider", RateLimit(max_calls=2, period="minute"))
        self.assertTrue(limiter.acquire("test_provider"))
        self.assertTrue(limiter.acquire("test_provider"))
        self.assertFalse(limiter.acquire("test_provider"))

    def test_acquire_unconfigured_provider_always_allowed(self):
        limiter = SharedRateLimiter()
        self.assertTrue(limiter.acquire("unknown_provider"))

    def test_remaining(self):
        limiter = SharedRateLimiter()
        limiter.configure("fmp", RateLimit(max_calls=250, period="day"))
        limiter.acquire("fmp")
        limiter.acquire("fmp")
        self.assertEqual(limiter.remaining("fmp"), 248)

    def test_day_period_budget(self):
        limiter = SharedRateLimiter()
        limiter.configure("fmp", RateLimit(max_calls=3, period="day"))
        self.assertTrue(limiter.acquire("fmp"))
        self.assertTrue(limiter.acquire("fmp"))
        self.assertTrue(limiter.acquire("fmp"))
        self.assertFalse(limiter.acquire("fmp"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_shared_rate_limiter.py -v`
Expected: FAIL (import error — module doesn't exist yet)

- [ ] **Step 3: Implement rate limiter**

Create `data_provider/shared/__init__.py`:

```python
from .rate_limiter import RateLimit, SharedRateLimiter
from .cache import ProviderCache
```

Create `data_provider/shared/rate_limiter.py`:

```python
# -*- coding: utf-8 -*-
"""
Token-bucket rate limiter shared across data provider managers.

Each provider (FMP, Finnhub, etc.) has a global budget. Multiple managers
that share a provider (e.g. FundamentalManager + NewsManager both use FMP)
go through the same limiter instance to prevent exceeding free-tier quotas.
"""

import logging
import time
import threading
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class RateLimit:
    """Rate limit configuration for a provider."""
    max_calls: int
    period: str  # "second", "minute", "day"

    @property
    def period_seconds(self) -> float:
        return {"second": 1.0, "minute": 60.0, "day": 86400.0}[self.period]


class SharedRateLimiter:
    """
    Process-global rate limiter for external API providers.

    Thread-safe. Call configure() once per provider at startup,
    then acquire() before each API call.
    """

    def __init__(self):
        self._limits: Dict[str, RateLimit] = {}
        self._calls: Dict[str, list] = {}  # provider -> list of timestamps
        self._lock = threading.Lock()

    def configure(self, provider: str, limit: RateLimit) -> None:
        with self._lock:
            self._limits[provider] = limit
            self._calls.setdefault(provider, [])

    def acquire(self, provider: str) -> bool:
        """Try to acquire a call slot. Returns False if budget exhausted."""
        with self._lock:
            if provider not in self._limits:
                return True  # unconfigured provider — no limit

            limit = self._limits[provider]
            now = time.monotonic()
            window = limit.period_seconds
            calls = self._calls[provider]

            # Prune expired timestamps
            cutoff = now - window
            self._calls[provider] = [t for t in calls if t > cutoff]
            calls = self._calls[provider]

            if len(calls) >= limit.max_calls:
                logger.debug(
                    "[RateLimiter] %s budget exhausted (%d/%d in %s)",
                    provider, len(calls), limit.max_calls, limit.period,
                )
                return False

            calls.append(now)
            return True

    def remaining(self, provider: str) -> int:
        """Return remaining calls in current window."""
        with self._lock:
            if provider not in self._limits:
                return 999999
            limit = self._limits[provider]
            now = time.monotonic()
            cutoff = now - limit.period_seconds
            calls = [t for t in self._calls.get(provider, []) if t > cutoff]
            return max(0, limit.max_calls - len(calls))
```

- [ ] **Step 4: Run rate limiter tests**

Run: `python -m pytest tests/test_shared_rate_limiter.py -v`
Expected: All PASS

- [ ] **Step 5: Write cache test**

Create `tests/test_shared_cache.py`:

```python
# -*- coding: utf-8 -*-
"""Tests for shared provider cache."""

import json
import os
import tempfile
import unittest
from datetime import datetime

from data_provider.shared.cache import ProviderCache


class TestProviderCache(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_cache.db")
        self.cache = ProviderCache(self.db_path)

    def tearDown(self):
        self.cache.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_put_and_get(self):
        self.cache.put("fund:AAPL:financials", {"pe": 28.3}, provider="fmp")
        entry = self.cache.get("fund:AAPL:financials")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["data"]["pe"], 28.3)
        self.assertEqual(entry["provider"], "fmp")
        self.assertFalse(entry["stale"])

    def test_get_missing_key(self):
        entry = self.cache.get("nonexistent")
        self.assertIsNone(entry)

    def test_put_with_meta(self):
        meta = {"next_earnings": "2026-05-01"}
        self.cache.put("fund:AAPL:financials", {"eps": 6.5}, provider="fmp", meta=meta)
        entry = self.cache.get("fund:AAPL:financials")
        self.assertEqual(entry["meta"]["next_earnings"], "2026-05-01")

    def test_get_meta(self):
        meta = {"next_earnings": "2026-05-01"}
        self.cache.put("fund:AAPL:financials", {"eps": 6.5}, provider="fmp", meta=meta)
        result = self.cache.get_meta("fund:AAPL:financials")
        self.assertEqual(result["next_earnings"], "2026-05-01")

    def test_get_meta_missing_key(self):
        result = self.cache.get_meta("nonexistent")
        self.assertIsNone(result)

    def test_delete(self):
        self.cache.put("key1", {"v": 1}, provider="test")
        self.cache.delete("key1")
        self.assertIsNone(self.cache.get("key1"))

    def test_persistence_across_instances(self):
        self.cache.put("persistent_key", {"val": 42}, provider="fmp")
        self.cache.close()
        cache2 = ProviderCache(self.db_path)
        entry = cache2.get("persistent_key")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["data"]["val"], 42)
        cache2.close()

    def test_stale_fallback(self):
        self.cache.put("fund:MSFT:financials", {"pe": 35.0}, provider="fmp")
        entry = self.cache.get_stale("fund:MSFT:financials")
        self.assertIsNotNone(entry)
        self.assertTrue(entry["stale"])
        self.assertEqual(entry["data"]["pe"], 35.0)
```

- [ ] **Step 6: Run cache test to verify it fails**

Run: `python -m pytest tests/test_shared_cache.py -v`
Expected: FAIL (import error)

- [ ] **Step 7: Implement cache**

Create `data_provider/shared/cache.py`:

```python
# -*- coding: utf-8 -*-
"""
SQLite-backed persistent cache for data providers.

Colocated under data/ so it's covered by the actions/cache step.
Each entry stores JSON data + metadata (e.g. next_earnings_date for
cache invalidation decisions).
"""

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = os.path.join("data", "provider_cache.db")


class ProviderCache:
    """
    SQLite-backed persistent key-value cache.

    Thread-safe. Keys are strings like "fund:AAPL:financials".
    Values are JSON-serializable dicts.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or os.getenv("PROVIDER_CACHE_DIR", _DEFAULT_DB_PATH)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_db()

    def _ensure_db(self) -> None:
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_entries (
                key         TEXT PRIMARY KEY,
                data        TEXT NOT NULL,
                meta        TEXT,
                fetched_at  TEXT NOT NULL,
                provider    TEXT,
                hits        INTEGER DEFAULT 0
            )
        """)
        self._conn.commit()

    def put(
        self,
        key: str,
        data: Dict[str, Any],
        provider: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO cache_entries (key, data, meta, fetched_at, provider, hits)
                VALUES (?, ?, ?, ?, ?, 0)
                ON CONFLICT(key) DO UPDATE SET
                    data=excluded.data,
                    meta=excluded.meta,
                    fetched_at=excluded.fetched_at,
                    provider=excluded.provider,
                    hits=0
                """,
                (key, json.dumps(data), json.dumps(meta) if meta else None, now, provider),
            )
            self._conn.commit()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get a cache entry. Returns None if not found."""
        with self._lock:
            row = self._conn.execute(
                "SELECT data, meta, fetched_at, provider FROM cache_entries WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
            self._conn.execute(
                "UPDATE cache_entries SET hits = hits + 1 WHERE key = ?", (key,)
            )
            self._conn.commit()
            return {
                "data": json.loads(row[0]),
                "meta": json.loads(row[1]) if row[1] else None,
                "fetched_at": row[2],
                "provider": row[3],
                "stale": False,
            }

    def get_stale(self, key: str) -> Optional[Dict[str, Any]]:
        """Get a cache entry marked as stale (for fallback on provider failure)."""
        entry = self.get(key)
        if entry is not None:
            entry["stale"] = True
        return entry

    def get_meta(self, key: str) -> Optional[Dict[str, Any]]:
        """Get only the metadata for a cache entry."""
        with self._lock:
            row = self._conn.execute(
                "SELECT meta FROM cache_entries WHERE key = ?", (key,)
            ).fetchone()
            if row is None or row[0] is None:
                return None
            return json.loads(row[0])

    def delete(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
```

- [ ] **Step 8: Run cache tests**

Run: `python -m pytest tests/test_shared_cache.py -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add data_provider/shared/ tests/test_shared_rate_limiter.py tests/test_shared_cache.py
git commit -m "feat: add shared rate limiter and persistent cache infrastructure"
```

- [ ] **Step 10: Regression check — all tests (existing + new) pass**

Run: `python -m pytest tests/ -m "not network" --timeout=60 -x -q`
Expected: All pass. New shared/ tests pass alongside all existing tests.

---

## Task 3: Fundamental types and FMP/Finnhub fetchers

**Files:**
- Create: `data_provider/fundamental/__init__.py`
- Create: `data_provider/fundamental/types.py`
- Create: `data_provider/fundamental/base.py`
- Create: `data_provider/fundamental/fmp_fetcher.py`
- Create: `data_provider/fundamental/finnhub_fetcher.py`
- Create: `data_provider/fundamental/alpha_vantage_fetcher.py`
- Create: `data_provider/fundamental/edgar_fetcher.py`
- Create: `tests/test_fundamental_types.py`
- Create: `tests/test_fundamental_fmp.py`
- Create: `tests/test_fundamental_finnhub.py`

This is a large task. Due to plan size constraints, I'll define the type system and FMP fetcher in full detail. Finnhub, Alpha Vantage, and EDGAR fetchers follow the same pattern — each subagent should read the spec Section 5 and the FMP fetcher as reference.

- [ ] **Step 1: Write types test**

Create `tests/test_fundamental_types.py`:

```python
# -*- coding: utf-8 -*-
"""Tests for fundamental data types."""

import unittest

from data_provider.fundamental.types import UnifiedFundamentalData


class TestUnifiedFundamentalData(unittest.TestCase):
    def test_defaults_to_none(self):
        data = UnifiedFundamentalData(code="AAPL", source="fmp")
        self.assertEqual(data.code, "AAPL")
        self.assertIsNone(data.pe_ratio)
        self.assertIsNone(data.eps_ttm)
        self.assertIsNone(data.insider_buy_count_90d)

    def test_to_dict_filters_none(self):
        data = UnifiedFundamentalData(code="AAPL", source="fmp", pe_ratio=28.3)
        d = data.to_dict()
        self.assertEqual(d["code"], "AAPL")
        self.assertEqual(d["pe_ratio"], 28.3)
        self.assertNotIn("eps_ttm", d)

    def test_has_valuation_data(self):
        data = UnifiedFundamentalData(code="AAPL", source="fmp", pe_ratio=28.3)
        self.assertTrue(data.has_valuation_data())
        empty = UnifiedFundamentalData(code="AAPL", source="fmp")
        self.assertFalse(empty.has_valuation_data())

    def test_merge_prefers_non_none(self):
        base = UnifiedFundamentalData(code="AAPL", source="fmp", pe_ratio=28.3)
        supplement = UnifiedFundamentalData(
            code="AAPL", source="finnhub", eps_ttm=6.5, pe_ratio=None
        )
        merged = base.merge(supplement)
        self.assertEqual(merged.pe_ratio, 28.3)  # kept from base
        self.assertEqual(merged.eps_ttm, 6.5)    # filled from supplement
        self.assertEqual(merged.source, "fmp")    # base source preserved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fundamental_types.py -v`
Expected: FAIL (import error)

- [ ] **Step 3: Implement types and base**

Create `data_provider/fundamental/__init__.py`:

```python
from .types import UnifiedFundamentalData
from .manager import FundamentalManager
```

Create `data_provider/fundamental/types.py`:

```python
# -*- coding: utf-8 -*-
"""Unified fundamental data types."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Dict, List, Optional


@dataclass
class UnifiedFundamentalData:
    code: str
    source: str

    # Valuation (fetch fresh daily — price-dependent)
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    peg_ratio: Optional[float] = None
    ev_ebitda: Optional[float] = None

    # Earnings
    eps_ttm: Optional[float] = None
    eps_estimate: Optional[float] = None
    revenue_ttm: Optional[float] = None
    earnings_date: Optional[str] = None
    earnings_surprise: Optional[float] = None

    # Profitability (cacheable — quarterly filings)
    profit_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None

    # Balance Sheet (cacheable — quarterly filings)
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    free_cash_flow: Optional[float] = None

    # Dividends
    dividend_yield: Optional[float] = None
    payout_ratio: Optional[float] = None

    # Ownership Signals (fetch fresh daily)
    insider_buy_count_90d: Optional[int] = None
    insider_sell_count_90d: Optional[int] = None
    institutional_ownership_pct: Optional[float] = None
    short_interest_pct: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"code": self.code, "source": self.source}
        for f in fields(self):
            if f.name in ("code", "source"):
                continue
            val = getattr(self, f.name)
            if val is not None:
                result[f.name] = val
        return result

    def has_valuation_data(self) -> bool:
        return any(
            getattr(self, f) is not None
            for f in ("pe_ratio", "forward_pe", "pb_ratio", "ev_ebitda")
        )

    def merge(self, other: UnifiedFundamentalData) -> UnifiedFundamentalData:
        """Merge another instance into this one. Non-None values in self take priority."""
        merged_kwargs = {"code": self.code, "source": self.source}
        for f in fields(self):
            if f.name in ("code", "source"):
                continue
            val = getattr(self, f.name)
            if val is None:
                val = getattr(other, f.name)
            merged_kwargs[f.name] = val
        return UnifiedFundamentalData(**merged_kwargs)
```

Create `data_provider/fundamental/base.py`:

```python
# -*- coding: utf-8 -*-
"""Base class for fundamental data fetchers."""

from abc import ABC, abstractmethod
from typing import Optional

from .types import UnifiedFundamentalData


class BaseFundamentalFetcher(ABC):
    """Abstract base for fundamental data providers."""

    name: str = "BaseFundamentalFetcher"
    priority: int = 99

    @abstractmethod
    def get_fundamentals(self, stock_code: str) -> Optional[UnifiedFundamentalData]:
        """Fetch fundamental data for a US stock ticker. Returns None on failure."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this fetcher has valid credentials."""
        ...
```

- [ ] **Step 4: Run types test**

Run: `python -m pytest tests/test_fundamental_types.py -v`
Expected: All PASS

- [ ] **Step 5: Write FMP fetcher test**

Create `tests/test_fundamental_fmp.py`:

```python
# -*- coding: utf-8 -*-
"""Tests for FMP fundamental fetcher."""

import unittest
from unittest.mock import patch, MagicMock

from data_provider.fundamental.fmp_fetcher import FMPFundamentalFetcher


class TestFMPAvailability(unittest.TestCase):
    def test_unavailable_without_key(self):
        fetcher = FMPFundamentalFetcher(api_key=None)
        self.assertFalse(fetcher.is_available())

    def test_available_with_key(self):
        fetcher = FMPFundamentalFetcher(api_key="test_key")
        self.assertTrue(fetcher.is_available())


class TestFMPGetFundamentals(unittest.TestCase):
    def setUp(self):
        self.fetcher = FMPFundamentalFetcher(api_key="test_key")

    @patch("data_provider.fundamental.fmp_fetcher._get_json")
    def test_success(self, mock_get):
        mock_get.side_effect = [
            # /profile endpoint
            [{"symbol": "AAPL", "price": 195.0, "mktCap": 3000000000000,
              "pe": 28.3, "sector": "Technology"}],
            # /ratios-ttm endpoint
            [{"peRatioTTM": 28.3, "pbRatioTTM": 45.1, "psRatioTTM": 7.8,
              "pegRatioTTM": 2.1, "returnOnEquityTTM": 1.56,
              "returnOnAssetsTTM": 0.31, "netProfitMarginTTM": 0.26,
              "operatingProfitMarginTTM": 0.30, "debtEquityRatioTTM": 1.87,
              "currentRatioTTM": 0.99, "dividendYieldTTM": 0.005,
              "payoutRatioTTM": 0.15, "priceToSalesRatioTTM": 7.8,
              "enterpriseValueOverEBITDATTM": 22.5}],
            # /earnings-surprises endpoint
            [{"actualEarningResult": 2.18, "estimatedEarning": 2.10,
              "date": "2026-01-30"}],
            # /insider-trading endpoint
            [{"transactionType": "P-Purchase", "securitiesTransacted": 1000},
             {"transactionType": "S-Sale", "securitiesTransacted": 500},
             {"transactionType": "P-Purchase", "securitiesTransacted": 200}],
        ]

        result = self.fetcher.get_fundamentals("AAPL")
        self.assertIsNotNone(result)
        self.assertEqual(result.code, "AAPL")
        self.assertAlmostEqual(result.pe_ratio, 28.3)
        self.assertAlmostEqual(result.roe, 1.56)
        self.assertEqual(result.insider_buy_count_90d, 2)
        self.assertEqual(result.insider_sell_count_90d, 1)

    @patch("data_provider.fundamental.fmp_fetcher._get_json")
    def test_returns_none_on_failure(self, mock_get):
        mock_get.side_effect = Exception("API error")
        result = self.fetcher.get_fundamentals("AAPL")
        self.assertIsNone(result)
```

- [ ] **Step 6: Run FMP test to verify it fails**

Run: `python -m pytest tests/test_fundamental_fmp.py -v`
Expected: FAIL (import error)

- [ ] **Step 7: Implement FMP fetcher**

Create `data_provider/fundamental/fmp_fetcher.py`:

```python
# -*- coding: utf-8 -*-
"""
FMP (Financial Modeling Prep) fundamental data fetcher.

Priority 0 (primary). Free tier: 250 requests/day.
Covers: ratios, earnings, financials, insider trades, institutional holdings.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import requests
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_sleep_log,
)

from .base import BaseFundamentalFetcher
from .types import UnifiedFundamentalData

logger = logging.getLogger(__name__)

_BASE_URL = "https://financialmodelingprep.com/api/v3"
_TIMEOUT = 15


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type((requests.exceptions.ConnectionError,
                                    requests.exceptions.Timeout)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _get_json(url: str, params: Dict[str, Any]) -> Any:
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


class FMPFundamentalFetcher(BaseFundamentalFetcher):
    name = "FMPFundamentalFetcher"
    priority = 0

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = (api_key or os.getenv("FMP_API_KEY", "")).strip()

    def is_available(self) -> bool:
        return bool(self._api_key)

    def get_fundamentals(self, stock_code: str) -> Optional[UnifiedFundamentalData]:
        if not self.is_available():
            return None
        symbol = stock_code.strip().upper()
        params = {"apikey": self._api_key}
        try:
            # Ratios TTM
            ratios_data = _get_json(f"{_BASE_URL}/ratios-ttm/{symbol}", params)
            r = ratios_data[0] if ratios_data else {}

            # Earnings surprises (last quarter)
            earnings_data = _get_json(
                f"{_BASE_URL}/earnings-surprises/{symbol}", params
            )
            last_earnings = earnings_data[0] if earnings_data else {}
            surprise = None
            if last_earnings.get("estimatedEarning") and last_earnings.get("actualEarningResult"):
                est = float(last_earnings["estimatedEarning"])
                actual = float(last_earnings["actualEarningResult"])
                if est != 0:
                    surprise = ((actual - est) / abs(est)) * 100

            # Insider trading (last 90 days)
            insider_data = _get_json(
                f"{_BASE_URL}/insider-trading",
                {**params, "symbol": symbol, "limit": 50},
            )
            buys = sum(
                1 for t in (insider_data or [])
                if "Purchase" in (t.get("transactionType") or "")
            )
            sells = sum(
                1 for t in (insider_data or [])
                if "Sale" in (t.get("transactionType") or "")
            )

            return UnifiedFundamentalData(
                code=symbol,
                source="fmp",
                pe_ratio=_safe(r.get("peRatioTTM")),
                forward_pe=None,  # FMP requires separate endpoint
                pb_ratio=_safe(r.get("pbRatioTTM")),
                ps_ratio=_safe(r.get("priceToSalesRatioTTM")),
                peg_ratio=_safe(r.get("pegRatioTTM")),
                ev_ebitda=_safe(r.get("enterpriseValueOverEBITDATTM")),
                eps_ttm=_safe(last_earnings.get("actualEarningResult")),
                eps_estimate=_safe(last_earnings.get("estimatedEarning")),
                earnings_date=last_earnings.get("date"),
                earnings_surprise=surprise,
                profit_margin=_safe(r.get("netProfitMarginTTM")),
                operating_margin=_safe(r.get("operatingProfitMarginTTM")),
                roe=_safe(r.get("returnOnEquityTTM")),
                roa=_safe(r.get("returnOnAssetsTTM")),
                debt_to_equity=_safe(r.get("debtEquityRatioTTM")),
                current_ratio=_safe(r.get("currentRatioTTM")),
                dividend_yield=_safe(r.get("dividendYieldTTM")),
                payout_ratio=_safe(r.get("payoutRatioTTM")),
                insider_buy_count_90d=buys,
                insider_sell_count_90d=sells,
            )
        except Exception as e:
            logger.warning("[FMP] Failed to fetch fundamentals for %s: %s", symbol, e)
            return None


def _safe(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        import math
        return None if math.isnan(f) or math.isinf(f) else f
    except (ValueError, TypeError):
        return None
```

- [ ] **Step 8: Run FMP tests**

Run: `python -m pytest tests/test_fundamental_fmp.py -v`
Expected: All PASS

- [ ] **Step 9: Implement Finnhub, Alpha Vantage, and EDGAR fetchers**

Each follows the same pattern as FMP. Refer to spec Section 5.1 for endpoint details:

- `data_provider/fundamental/finnhub_fetcher.py` — Uses Finnhub `/stock/metric`, `/stock/insider-sentiment`, `/stock/ownership` endpoints
- `data_provider/fundamental/alpha_vantage_fetcher.py` — Uses `/query?function=OVERVIEW`, `/query?function=INCOME_STATEMENT`, `/query?function=BALANCE_SHEET`
- `data_provider/fundamental/edgar_fetcher.py` — Uses SEC EDGAR company-facts XBRL API (no key, requires User-Agent)

Write corresponding tests: `tests/test_fundamental_finnhub.py` with mocked API responses, following the same structure as `test_fundamental_fmp.py`.

- [ ] **Step 10: Run all fundamental fetcher tests**

Run: `python -m pytest tests/test_fundamental_fmp.py tests/test_fundamental_finnhub.py tests/test_fundamental_types.py -v`
Expected: All PASS

- [ ] **Step 11: Commit**

```bash
git add data_provider/fundamental/ tests/test_fundamental_*.py
git commit -m "feat: add fundamental data types and provider fetchers (FMP, Finnhub, AlphaVantage, EDGAR)"
```

- [ ] **Step 12: Regression check**

Run: `python -m pytest tests/ -m "not network" --timeout=60 -x -q`
Expected: All pass (existing + shared + fundamental tests)

---

## Task 4: FundamentalManager with failover and two-phase fetch

**Files:**
- Create: `data_provider/fundamental/manager.py`
- Create: `tests/test_fundamental_manager.py`

- [ ] **Step 1: Write manager test**

Create `tests/test_fundamental_manager.py`:

```python
# -*- coding: utf-8 -*-
"""Tests for FundamentalManager failover and two-phase fetch."""

import unittest
from unittest.mock import MagicMock, patch

from data_provider.fundamental.manager import FundamentalManager
from data_provider.fundamental.types import UnifiedFundamentalData


class TestFailover(unittest.TestCase):
    def test_primary_success_skips_secondary(self):
        fmp = MagicMock()
        fmp.is_available.return_value = True
        fmp.name = "FMP"
        fmp.get_fundamentals.return_value = UnifiedFundamentalData(
            code="AAPL", source="fmp", pe_ratio=28.3
        )
        finnhub = MagicMock()
        finnhub.is_available.return_value = True
        finnhub.name = "Finnhub"

        manager = FundamentalManager(fetchers=[fmp, finnhub])
        result = manager.get_fundamentals("AAPL")
        self.assertIsNotNone(result)
        self.assertEqual(result.pe_ratio, 28.3)
        finnhub.get_fundamentals.assert_not_called()

    def test_failover_on_primary_failure(self):
        fmp = MagicMock()
        fmp.is_available.return_value = True
        fmp.name = "FMP"
        fmp.get_fundamentals.return_value = None

        finnhub = MagicMock()
        finnhub.is_available.return_value = True
        finnhub.name = "Finnhub"
        finnhub.get_fundamentals.return_value = UnifiedFundamentalData(
            code="AAPL", source="finnhub", pe_ratio=27.9
        )

        manager = FundamentalManager(fetchers=[fmp, finnhub])
        result = manager.get_fundamentals("AAPL")
        self.assertIsNotNone(result)
        self.assertEqual(result.source, "finnhub")

    def test_all_fail_returns_none(self):
        fmp = MagicMock()
        fmp.is_available.return_value = True
        fmp.name = "FMP"
        fmp.get_fundamentals.return_value = None

        manager = FundamentalManager(fetchers=[fmp])
        result = manager.get_fundamentals("AAPL")
        self.assertIsNone(result)

    def test_skip_unavailable_fetcher(self):
        fmp = MagicMock()
        fmp.is_available.return_value = False
        fmp.name = "FMP"

        finnhub = MagicMock()
        finnhub.is_available.return_value = True
        finnhub.name = "Finnhub"
        finnhub.get_fundamentals.return_value = UnifiedFundamentalData(
            code="AAPL", source="finnhub", pe_ratio=27.9
        )

        manager = FundamentalManager(fetchers=[fmp, finnhub])
        result = manager.get_fundamentals("AAPL")
        fmp.get_fundamentals.assert_not_called()
        self.assertEqual(result.source, "finnhub")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fundamental_manager.py -v`
Expected: FAIL (import error)

- [ ] **Step 3: Implement FundamentalManager**

Create `data_provider/fundamental/manager.py`:

```python
# -*- coding: utf-8 -*-
"""
FundamentalManager — orchestrates fundamental data fetchers with failover.

Implements the two-phase fetch strategy:
  Phase 1: Always-fresh data (ratios, estimates, insider) from first available fetcher
  Phase 2: Cacheable data (financial statements) — use cache if earnings date not passed
"""

import logging
from typing import List, Optional

from data_provider.realtime_types import CircuitBreaker
from data_provider.shared.cache import ProviderCache

from .base import BaseFundamentalFetcher
from .types import UnifiedFundamentalData

logger = logging.getLogger(__name__)


class FundamentalManager:
    """
    Orchestrates multiple fundamental data fetchers with priority-based failover.

    Usage:
        manager = FundamentalManager.from_config()
        data = manager.get_fundamentals("AAPL")
    """

    def __init__(
        self,
        fetchers: Optional[List[BaseFundamentalFetcher]] = None,
        cache: Optional[ProviderCache] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        self._fetchers = fetchers or []
        self._cache = cache
        self._cb = circuit_breaker or CircuitBreaker(
            failure_threshold=3, cooldown_seconds=300.0
        )

    @classmethod
    def from_config(cls) -> "FundamentalManager":
        """Create a FundamentalManager with all configured fetchers."""
        from .fmp_fetcher import FMPFundamentalFetcher
        from .finnhub_fetcher import FinnhubFundamentalFetcher
        from .alpha_vantage_fetcher import AlphaVantageFundamentalFetcher
        from .edgar_fetcher import EDGARFundamentalFetcher

        fetchers: List[BaseFundamentalFetcher] = [
            FMPFundamentalFetcher(),
            FinnhubFundamentalFetcher(),
            AlphaVantageFundamentalFetcher(),
            EDGARFundamentalFetcher(),
        ]
        return cls(
            fetchers=fetchers,
            cache=ProviderCache(),
        )

    def get_fundamentals(self, stock_code: str) -> Optional[UnifiedFundamentalData]:
        """
        Fetch fundamental data with failover across providers.

        Tries each fetcher in priority order. Returns the first successful result.
        On total failure, returns stale cached data (if available) or None.
        """
        symbol = stock_code.strip().upper()

        for fetcher in self._fetchers:
            if not fetcher.is_available():
                continue
            if not self._cb.is_available(fetcher.name):
                logger.debug("[FundamentalManager] %s is circuit-broken, skipping", fetcher.name)
                continue
            try:
                result = fetcher.get_fundamentals(symbol)
                if result is not None:
                    self._cb.record_success(fetcher.name)
                    self._update_cache(symbol, result)
                    logger.info(
                        "[FundamentalManager] Got fundamentals for %s from %s",
                        symbol, fetcher.name,
                    )
                    return result
                self._cb.record_inconclusive(fetcher.name)
            except Exception as e:
                logger.warning(
                    "[FundamentalManager] %s failed for %s: %s",
                    fetcher.name, symbol, e,
                )
                self._cb.record_failure(fetcher.name, str(e))

        # All fetchers failed — try stale cache
        if self._cache:
            stale = self._cache.get_stale(f"fund:{symbol}:latest")
            if stale:
                logger.warning(
                    "[FundamentalManager] All fetchers failed for %s, using stale cache from %s",
                    symbol, stale["fetched_at"],
                )
                return UnifiedFundamentalData(**stale["data"])

        logger.warning("[FundamentalManager] No fundamental data available for %s", symbol)
        return None

    def _update_cache(self, symbol: str, data: UnifiedFundamentalData) -> None:
        if self._cache:
            meta = {}
            if data.earnings_date:
                meta["next_earnings"] = data.earnings_date
            self._cache.put(
                f"fund:{symbol}:latest",
                data.to_dict(),
                provider=data.source,
                meta=meta or None,
            )
```

- [ ] **Step 4: Run manager tests**

Run: `python -m pytest tests/test_fundamental_manager.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add data_provider/fundamental/manager.py tests/test_fundamental_manager.py
git commit -m "feat: add FundamentalManager with failover and cache integration"
```

- [ ] **Step 6: Regression check**

Run: `python -m pytest tests/ -m "not network" --timeout=60 -x -q`
Expected: All pass

---

## Task 5: News types and fetchers

**Files:**
- Create: `data_provider/news/__init__.py`
- Create: `data_provider/news/types.py`
- Create: `data_provider/news/base.py`
- Create: `data_provider/news/finnhub_fetcher.py`
- Create: `data_provider/news/fmp_fetcher.py`
- Create: `data_provider/news/edgar_fetcher.py`
- Create: `data_provider/news/search_adapter.py`
- Create: `tests/test_news_types.py`
- Create: `tests/test_news_finnhub.py`

Follows the same TDD pattern as Task 3. Refer to spec Section 6 for schema and endpoints.

- [ ] **Step 1: Write types test**

Create `tests/test_news_types.py`:

```python
# -*- coding: utf-8 -*-
"""Tests for news data types."""

import unittest
from datetime import datetime

from data_provider.news.types import UnifiedNewsItem, NewsEventType


class TestUnifiedNewsItem(unittest.TestCase):
    def test_creation(self):
        item = UnifiedNewsItem(
            title="AAPL beats earnings",
            url="https://example.com/article",
            published_at=datetime(2026, 4, 1, 14, 0),
            source_name="finnhub",
            tickers=["AAPL"],
            event_type=NewsEventType.EARNINGS,
        )
        self.assertEqual(item.event_type, NewsEventType.EARNINGS)
        self.assertEqual(item.relevance_score, 0.0)

    def test_to_dict(self):
        item = UnifiedNewsItem(
            title="Test",
            url="https://example.com",
            published_at=datetime(2026, 4, 1),
            source_name="fmp",
            tickers=["MSFT"],
            event_type=NewsEventType.GENERAL,
            sentiment=0.5,
        )
        d = item.to_dict()
        self.assertEqual(d["source_name"], "fmp")
        self.assertEqual(d["event_type"], "general")
        self.assertEqual(d["sentiment"], 0.5)
```

- [ ] **Step 2: Implement types, base, and all fetchers**

Create the following files per spec Section 6:

- `data_provider/news/types.py` — `UnifiedNewsItem` dataclass, `NewsEventType` enum
- `data_provider/news/base.py` — `BaseNewsFetcher` ABC with `get_news(stock_code, days)` method
- `data_provider/news/finnhub_fetcher.py` — Uses `/company-news` and `/stock/recommendation` endpoints
- `data_provider/news/fmp_fetcher.py` — Uses `/stock_news` endpoint
- `data_provider/news/edgar_fetcher.py` — Uses SEC EDGAR submissions API for recent 8-K filings
- `data_provider/news/search_adapter.py` — Wraps existing `src/search_service.py` as a `BaseNewsFetcher`, converting `SearchResponse` items to `UnifiedNewsItem` with `event_type=GENERAL`
- `data_provider/news/__init__.py` — exports `UnifiedNewsItem`, `NewsEventType`, `NewsManager`

Write tests: `tests/test_news_finnhub.py` with mocked API responses.

- [ ] **Step 3: Run all news tests**

Run: `python -m pytest tests/test_news_types.py tests/test_news_finnhub.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add data_provider/news/ tests/test_news_*.py
git commit -m "feat: add news data types and provider fetchers (Finnhub, FMP, EDGAR, search adapter)"
```

- [ ] **Step 5: Regression check**

Run: `python -m pytest tests/ -m "not network" --timeout=60 -x -q`
Expected: All pass

---

## Task 6: NewsManager with dedup and relevance scoring

**Files:**
- Create: `data_provider/news/manager.py`
- Create: `tests/test_news_manager.py`

- [ ] **Step 1: Write manager test**

Create `tests/test_news_manager.py`:

```python
# -*- coding: utf-8 -*-
"""Tests for NewsManager deduplication and scoring."""

import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from data_provider.news.manager import NewsManager
from data_provider.news.types import UnifiedNewsItem, NewsEventType


def _make_item(title, url, source, hours_ago=0, event_type=NewsEventType.GENERAL):
    return UnifiedNewsItem(
        title=title,
        url=url,
        published_at=datetime.now() - timedelta(hours=hours_ago),
        source_name=source,
        tickers=["AAPL"],
        event_type=event_type,
    )


class TestDedup(unittest.TestCase):
    def test_dedup_by_url(self):
        items = [
            _make_item("Article A", "https://example.com/a", "finnhub"),
            _make_item("Article A copy", "https://example.com/a", "fmp"),
        ]
        deduped = NewsManager._deduplicate(items)
        self.assertEqual(len(deduped), 1)

    def test_different_urls_kept(self):
        items = [
            _make_item("Article A", "https://example.com/a", "finnhub"),
            _make_item("Article B", "https://example.com/b", "fmp"),
        ]
        deduped = NewsManager._deduplicate(items)
        self.assertEqual(len(deduped), 2)


class TestScoring(unittest.TestCase):
    def test_earnings_scored_higher_than_general(self):
        earnings_item = _make_item("AAPL earnings", "https://a.com", "finnhub",
                                    hours_ago=1, event_type=NewsEventType.EARNINGS)
        general_item = _make_item("AAPL mentioned", "https://b.com", "tavily",
                                   hours_ago=1, event_type=NewsEventType.GENERAL)
        scored = NewsManager._score_items([earnings_item, general_item])
        self.assertGreater(scored[0].relevance_score, scored[1].relevance_score)

    def test_newer_scored_higher(self):
        recent = _make_item("Recent", "https://a.com", "finnhub", hours_ago=1)
        old = _make_item("Old", "https://b.com", "finnhub", hours_ago=48)
        scored = NewsManager._score_items([recent, old])
        self.assertGreater(scored[0].relevance_score, scored[1].relevance_score)


class TestManagerIntegration(unittest.TestCase):
    def test_get_financial_news_combines_sources(self):
        fetcher1 = MagicMock()
        fetcher1.is_available.return_value = True
        fetcher1.name = "Finnhub"
        fetcher1.get_news.return_value = [
            _make_item("From Finnhub", "https://a.com", "finnhub")
        ]
        fetcher2 = MagicMock()
        fetcher2.is_available.return_value = True
        fetcher2.name = "FMP"
        fetcher2.get_news.return_value = [
            _make_item("From FMP", "https://b.com", "fmp")
        ]

        manager = NewsManager(fetchers=[fetcher1, fetcher2])
        results = manager.get_financial_news("AAPL")
        self.assertEqual(len(results), 2)

    def test_all_fail_returns_empty(self):
        fetcher = MagicMock()
        fetcher.is_available.return_value = True
        fetcher.name = "Finnhub"
        fetcher.get_news.side_effect = Exception("API error")

        manager = NewsManager(fetchers=[fetcher])
        results = manager.get_financial_news("AAPL")
        self.assertEqual(results, [])
```

- [ ] **Step 2: Implement NewsManager**

Create `data_provider/news/manager.py` with:
- `get_financial_news(stock_code, days=7)` — queries ALL available fetchers (not failover — news aggregates), deduplicates, scores, sorts
- `_deduplicate(items)` — static method, removes items with duplicate URLs
- `_score_items(items)` — static method, computes `relevance_score` based on recency, source authority, and event type

Key difference from FundamentalManager: NewsManager queries **all** fetchers and combines results (aggregation), not failover. This is because different sources have different news coverage.

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_news_manager.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add data_provider/news/manager.py tests/test_news_manager.py
git commit -m "feat: add NewsManager with dedup and relevance scoring"
```

- [ ] **Step 5: Regression check**

Run: `python -m pytest tests/ -m "not network" --timeout=60 -x -q`
Expected: All pass

---

## Task 7: Macro types and FRED fetcher

**Files:**
- Create: `data_provider/macro/__init__.py`
- Create: `data_provider/macro/types.py`
- Create: `data_provider/macro/base.py`
- Create: `data_provider/macro/fred_fetcher.py`
- Create: `data_provider/macro/finnhub_fetcher.py`
- Create: `tests/test_macro_types.py`
- Create: `tests/test_macro_fred.py`

- [ ] **Step 1: Write types test**

Create `tests/test_macro_types.py`:

```python
# -*- coding: utf-8 -*-
"""Tests for macro data types."""

import unittest
from datetime import datetime

from data_provider.macro.types import (
    MacroIndicator, EconEvent, UnifiedMacroSnapshot,
)


class TestMacroIndicator(unittest.TestCase):
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
        self.assertEqual(ind.value, 5.33)
        self.assertEqual(ind.change, -0.17)


class TestUnifiedMacroSnapshot(unittest.TestCase):
    def test_market_regime(self):
        snap = UnifiedMacroSnapshot(
            timestamp=datetime.now(),
            indicators={},
            upcoming_events=[],
            market_regime="risk_off",
        )
        self.assertEqual(snap.market_regime, "risk_off")

    def test_to_dict(self):
        snap = UnifiedMacroSnapshot(
            timestamp=datetime(2026, 4, 8, 10, 0),
            indicators={
                "fed_funds_rate": MacroIndicator(
                    name="fed_funds_rate", display_name="Fed Funds",
                    value=5.33, previous_value=None, change=None,
                    unit="%", as_of_date="2026-03-01", source="fred",
                )
            },
            upcoming_events=[
                EconEvent(event="FOMC", date="2026-04-15",
                         impact="high", estimate=None, previous=None)
            ],
            market_regime="neutral",
        )
        d = snap.to_dict()
        self.assertIn("fed_funds_rate", d["indicators"])
        self.assertEqual(len(d["upcoming_events"]), 1)
```

- [ ] **Step 2: Implement types, base, FRED fetcher, Finnhub calendar fetcher**

Refer to spec Section 7 for the `MACRO_SERIES` dict and schema definitions. The FRED fetcher uses:
- `https://api.stlouisfed.org/fred/series/observations` for data
- `https://api.stlouisfed.org/fred/series` for metadata (last_updated check)

The Finnhub macro fetcher uses `/calendar/economic` for upcoming events.

Write `tests/test_macro_fred.py` with mocked API responses.

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_macro_types.py tests/test_macro_fred.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add data_provider/macro/ tests/test_macro_*.py
git commit -m "feat: add macro data types and FRED/Finnhub fetchers"
```

- [ ] **Step 5: Regression check**

Run: `python -m pytest tests/ -m "not network" --timeout=60 -x -q`
Expected: All pass

---

## Task 8: MacroManager

**Files:**
- Create: `data_provider/macro/manager.py`
- Create: `tests/test_macro_manager.py`

- [ ] **Step 1: Write manager test**

Create `tests/test_macro_manager.py`:

```python
# -*- coding: utf-8 -*-
"""Tests for MacroManager."""

import unittest
from unittest.mock import MagicMock
from datetime import datetime

from data_provider.macro.manager import MacroManager
from data_provider.macro.types import (
    MacroIndicator, EconEvent, UnifiedMacroSnapshot,
)


class TestMacroManager(unittest.TestCase):
    def test_get_snapshot_combines_indicators_and_events(self):
        fred = MagicMock()
        fred.is_available.return_value = True
        fred.name = "FRED"
        fred.get_indicators.return_value = {
            "fed_funds_rate": MacroIndicator(
                name="fed_funds_rate", display_name="Fed Funds",
                value=5.33, previous_value=5.50, change=-0.17,
                unit="%", as_of_date="2026-03-01", source="fred",
            )
        }

        finnhub = MagicMock()
        finnhub.is_available.return_value = True
        finnhub.name = "Finnhub"
        finnhub.get_economic_calendar.return_value = [
            EconEvent(event="FOMC", date="2026-04-15",
                     impact="high", estimate=None, previous=None)
        ]

        manager = MacroManager(indicator_fetchers=[fred], calendar_fetchers=[finnhub])
        snap = manager.get_snapshot()
        self.assertIsNotNone(snap)
        self.assertIn("fed_funds_rate", snap.indicators)
        self.assertEqual(len(snap.upcoming_events), 1)
        self.assertIn(snap.market_regime, ("risk_on", "risk_off", "neutral"))

    def test_all_fail_returns_none(self):
        fred = MagicMock()
        fred.is_available.return_value = True
        fred.name = "FRED"
        fred.get_indicators.side_effect = Exception("fail")

        manager = MacroManager(indicator_fetchers=[fred], calendar_fetchers=[])
        snap = manager.get_snapshot()
        self.assertIsNone(snap)
```

- [ ] **Step 2: Implement MacroManager**

Create `data_provider/macro/manager.py`. Key points:
- `get_snapshot()` returns `UnifiedMacroSnapshot`
- Queries indicator fetchers (FRED, FMP) for economic data
- Queries calendar fetchers (Finnhub) for upcoming events
- Computes `market_regime` from VIX level + yield curve spread (T10Y2Y)
- Called once per daily run, not per stock

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_macro_manager.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add data_provider/macro/manager.py tests/test_macro_manager.py
git commit -m "feat: add MacroManager with market regime computation"
```

- [ ] **Step 5: Regression check**

Run: `python -m pytest tests/ -m "not network" --timeout=60 -x -q`
Expected: All pass

---

## Task 9: Pipeline integration and config

**Files:**
- Modify: `src/config.py` (add new env var fields)
- Modify: `src/core/pipeline.py` (add new manager calls)

- [ ] **Step 1: Add config fields for new providers**

In `src/config.py`, add fields to the config dataclass and `_load_from_env()`:

```python
# New provider API keys
fmp_api_key: str = ""
finnhub_api_key: str = ""
alpha_vantage_api_key: str = ""
fred_api_key: str = ""
sec_edgar_user_agent: str = ""
provider_cache_enabled: bool = True
provider_cache_dir: str = "./data/provider_cache.db"
```

And in `_load_from_env()`:

```python
fmp_api_key=os.getenv('FMP_API_KEY', ''),
finnhub_api_key=os.getenv('FINNHUB_API_KEY', ''),
alpha_vantage_api_key=os.getenv('ALPHA_VANTAGE_API_KEY', ''),
fred_api_key=os.getenv('FRED_API_KEY', ''),
sec_edgar_user_agent=os.getenv('SEC_EDGAR_USER_AGENT', ''),
provider_cache_enabled=os.getenv('PROVIDER_CACHE_ENABLED', 'true').lower() == 'true',
provider_cache_dir=os.getenv('PROVIDER_CACHE_DIR', './data/provider_cache.db'),
```

- [ ] **Step 2: Integrate managers into pipeline**

In `src/core/pipeline.py`, where the analysis context is built for each stock:
- Import and instantiate the three new managers (lazily, wrapped in try/except)
- Call them alongside existing data fetching
- Pass results into the analysis context
- Each call wrapped in try/except returning `None` on failure

The exact integration point depends on the current pipeline structure. Read `src/core/pipeline.py` to find where `DataFetcherManager` calls are made and add the new manager calls alongside them.

- [ ] **Step 3: Verify compilation**

Run: `python -m py_compile src/config.py && python -m py_compile src/core/pipeline.py`
Expected: No errors

- [ ] **Step 4: Run existing tests to verify no regression**

Run: `python -m pytest tests/ -m "not network" --timeout=60 -x -q`
Expected: All existing tests still pass

- [ ] **Step 5: Commit**

```bash
git add src/config.py src/core/pipeline.py
git commit -m "feat: integrate FundamentalManager, NewsManager, MacroManager into pipeline"
```

---

## Task 10: Configuration docs and .env.example

**Files:**
- Modify: `.env.example` (add new provider keys)
- Modify: `docs/CHANGELOG.md` (add to [Unreleased])

- [ ] **Step 1: Update .env.example**

Add the new provider configuration section:

```env
# ==========================================
# Data Providers (all optional)
# ==========================================
# FMP (Financial Modeling Prep) - fundamentals, news
# Free tier: 250 requests/day. Sign up: https://site.financialmodelingprep.com/developer/docs
FMP_API_KEY=

# Finnhub - news, analyst ratings, economic calendar
# Free tier: 60 requests/min. Sign up: https://finnhub.io/
FINNHUB_API_KEY=

# Alpha Vantage - fundamental data fallback
# Free tier: 25 requests/day. Sign up: https://www.alphavantage.co/support/#api-key
ALPHA_VANTAGE_API_KEY=

# FRED (Federal Reserve Economic Data) - macro indicators
# Free: 120 requests/min. Sign up: https://fred.stlouisfed.org/docs/api/api_key.html
FRED_API_KEY=

# SEC EDGAR - filings, insider trades (no API key needed, just email for User-Agent)
SEC_EDGAR_USER_AGENT=your-email@example.com

# Provider cache (persists quarterly financial data between runs)
PROVIDER_CACHE_ENABLED=true
```

- [ ] **Step 2: Update CHANGELOG.md**

Add to `[Unreleased]`:

```markdown
- [新功能] Add FundamentalManager for US stock fundamental data (FMP, Finnhub, Alpha Vantage, SEC EDGAR)
- [新功能] Add NewsManager for financial-grade news aggregation with dedup and relevance scoring
- [新功能] Add MacroManager for economic context (FRED macro indicators, economic calendar, market regime)
- [新功能] Add shared rate limiter and persistent SQLite cache for provider data
- [新功能] Enable cross-run data persistence in GitHub Actions via actions/cache
- [改进] Add FMP, Finnhub, Alpha Vantage, FRED, SEC EDGAR provider env vars to daily_analysis workflow
```

- [ ] **Step 3: Commit**

```bash
git add .env.example docs/CHANGELOG.md
git commit -m "docs: update .env.example and CHANGELOG for data provider expansion"
```

- [ ] **Step 4: Regression check**

Run: `python -m pytest tests/ -m "not network" --timeout=60 -x -q`
Expected: All pass (docs-only change, no test impact)

---

## Task 11: Final validation

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -m "not network" --timeout=60 -q`
Expected: All tests pass (existing + new)

- [ ] **Step 2: Run ci_gate.sh**

Run: `./scripts/ci_gate.sh`
Expected: Pass

- [ ] **Step 3: Verify all new files compile**

Run: `python -m py_compile data_provider/shared/rate_limiter.py && python -m py_compile data_provider/shared/cache.py && python -m py_compile data_provider/fundamental/manager.py && python -m py_compile data_provider/news/manager.py && python -m py_compile data_provider/macro/manager.py`
Expected: No errors

- [ ] **Step 4: Verify import works end-to-end**

Run: `python -c "from data_provider.fundamental import FundamentalManager; from data_provider.news.manager import NewsManager; from data_provider.macro.manager import MacroManager; print('All managers importable')"`
Expected: "All managers importable"
