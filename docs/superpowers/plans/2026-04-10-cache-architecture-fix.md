# Cache Architecture Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the broken GitHub Actions data cache so that each daily run preserves its analysis outputs (agent memory, backtest history, provider cache) for future runs, and add lightweight data retention to prevent unbounded DB growth.

**Architecture:** Replace the static `actions/cache` key with a dynamic per-run key + `restore-keys` prefix fallback, so each run restores the latest prior cache and saves its own enriched state. Add optional SQLite-level retention pruning so the cached DB stays bounded over months/years of daily runs.

**Tech Stack:** GitHub Actions (`actions/cache@v4`), Python 3.11, SQLAlchemy (existing), SQLite, pytest

**Branch:** `feat/cache-architecture-fix` from latest `main`

**Context:** This plan was written based on a detailed investigation in a prior session. Key findings are documented in the Problem Analysis section below. The plan is intentionally written to be **revisable** — the author plans to incorporate domain knowledge from a securities analysis book before execution.

---

## Two-Layer Architecture: Cache Transport vs. Data Retention

This plan touches two **independent** layers that must not be confused:

### Layer 1: GitHub Actions cache (transport layer)

The `actions/cache@v4` step is a **transport mechanism** — it serializes the `data/` directory (containing SQLite DB files) at the end of a run and restores it at the start of the next run. It is a zip/unzip of the directory contents between runs.

- Cache entries are keyed by `analysis-data-Linux-<run_id>`, where `run_id` is an opaque GitHub-assigned number (not a date).
- We only ever need **one** cache entry — the latest one. It contains the full accumulated DB.
- `restore-keys` prefix match always picks the most recent entry. Older entries expire automatically after 7 days of non-access (GitHub's eviction policy).
- The `run_id` in the key exists solely to make it unique (since `actions/cache` keys are immutable/write-once). It has **no semantic relationship to dates or retention periods**.
- Whether the action runs 3 times in one day or once in 5 days, the cache transport works the same way: restore latest → run pipeline → save updated snapshot.

**This layer has no configurable retention.** GitHub manages eviction automatically.

### Layer 2: SQLite data rows (content layer)

Inside the cached DB files, individual data rows have their own timestamps (`created_at`, `fetched_at`, `date`). The retention pruning in Tasks 2-4 operates on **these row-level timestamps**, completely independent of which cache entry they came from or when the action ran.

- `RETENTION_ANALYSIS_HISTORY_DAYS=180` means: delete rows in `analysis_history` where `created_at` is older than 180 calendar days.
- This works correctly regardless of action execution frequency — the pruning looks at each row's own timestamp, not the cache entry's age or the `run_id`.

### How they interact

```
Run N:
  1. [Layer 1] Restore latest DB snapshot from GitHub cache
  2. [Pipeline] Run analysis → append new rows with today's timestamps
  3. [Layer 2] Prune rows where row timestamp > retention threshold
  4. [Layer 1] Save updated DB snapshot to GitHub cache (new unique key)

Run N+1:
  1. [Layer 1] Restore Run N's snapshot (prefix match)
  2. [Pipeline] Run analysis → append new rows
  3. [Layer 2] Prune old rows (same calendar-day logic)
  4. [Layer 1] Save updated snapshot (new unique key; Run N's entry expires in ~7 days)
```

The GitHub cache layer is stateless transport. The SQLite layer is stateful content with its own time-based lifecycle.

---

## Problem Analysis

### What's broken

The workflow at `.github/workflows/daily_analysis.yml:59-63` uses a **static** cache key:

```yaml
- name: Restore analysis data cache
  uses: actions/cache@v4
  with:
    path: data/
    key: analysis-data-${{ runner.os }}
```

`actions/cache@v4` caches are **immutable** — once saved with a given key, that key can never be overwritten. The post-step logic skips saving when the primary key already exists:

```
Cache hit occurred on the primary key analysis-data-Linux, not saving cache.
```

**Result:** Only the first-ever run's data is cached. All subsequent runs restore that stale snapshot, enrich it with fresh data during execution, then silently discard all new data.

### What's lost each run

| Table | Growth per run | Purpose | Impact of loss |
|-------|---------------|---------|----------------|
| `analysis_history` | ~25 KB/stock | Stores sentiment, signals, sniper targets | Agent memory cannot learn from past calls |
| `backtest_result` | ~1.5 KB/stock | Evaluates prior predictions | Backtest system non-functional (0 candidates) |
| `news_intel` | ~3 KB/stock | Deduplicated news articles | No historical news dedup across runs |
| `stock_daily` | ~500 B/stock | New trading day OHLCV | Checkpoint resume cannot skip re-fetching |
| `provider_cache.db` | variable | API response cache | Redundant API calls; rate limit pressure |
| `fundamental_snapshot` | ~6 KB/stock | P0 fundamental context | No fundamental history preservation |

### What depends on cached historical data

| Component | File | How it reads history | Impact of empty DB |
|-----------|------|---------------------|-------------------|
| Agent memory | `src/agent/memory.py:93-139` | `get_stock_history(code, limit=3)` reads `analysis_history` | Agent starts cold — no learning from prior calls |
| Backtest evaluation | `src/repositories/backtest_repo.py:27-58` | `get_candidates()` reads `analysis_history` older than N days | Zero candidates; backtest completely non-functional |
| Checkpoint resume | `src/core/pipeline.py:230-260` | `has_today_data(code)` checks `stock_daily` | Redundant API fetches on re-runs within same day |
| Agent calibration | `src/agent/memory.py:145-189` | `get_calibration()` reads backtest accuracy stats | No confidence adjustment; always returns neutral |

### What does NOT depend on cached data

| Component | Reason |
|-----------|--------|
| Trend/technical analysis (MA, RSI, MACD) | Fixed 89-day window, always recalculated from fresh API fetch |
| News search | Always fetches fresh; only recent 3-day window used |
| Market review | Single-day snapshot from live index data |

### DB growth projections (per stock, no cleanup)

| Timeframe | `stock_analysis.db` | `provider_cache.db` | Combined |
|-----------|---------------------|---------------------|----------|
| 1 month | ~2 MB | ~3 MB | ~5 MB |
| 1 year | ~22 MB | ~15 MB | ~37 MB |
| 5 years | ~110 MB | ~75 MB | ~185 MB |

GitHub Actions cache limit: 10 GB per repo. Growth is manageable but unbounded without retention.

### Branch scope constraint

GitHub Actions caches are **branch-scoped**: a branch can read caches from itself or `main`, but `main` cannot read caches created on feature branches. This is one-way inheritance by design.

Confirmed by the April 8th run on `feat/data-provider-expansion` (cache hit) vs. April 10th run on `main` (cache miss with identical key).

---

## File Structure

```
.github/workflows/
  daily_analysis.yml              # Task 1: Fix cache key strategy

src/
  storage.py                      # Task 2: Add retention/pruning methods
  config.py                       # Task 2: Add retention config knobs

data_provider/shared/
  cache.py                        # Task 3: Add TTL-based eviction to provider cache

tests/
  test_storage_retention.py       # Task 2: Test retention logic
  test_shared_cache_ttl.py        # Task 3: Test provider cache TTL
```

---

## Task 1: Fix GitHub Actions cache key strategy (Layer 1 — transport)

**Files:**
- Modify: `.github/workflows/daily_analysis.yml:59-63`

This is the critical fix to the **transport layer**. Replace the static key with a dynamic per-run key so each run saves its enriched DB. The `run_id` in the key is only for uniqueness — it has no date semantics and no relationship to the data retention in Tasks 2-4.

- [ ] **Step 1: Update cache step with dynamic key + restore-keys**

Replace lines 59-63 in `.github/workflows/daily_analysis.yml`:

```yaml
      - name: Restore analysis data cache
        uses: actions/cache@v4
        with:
          path: data/
          key: analysis-data-${{ runner.os }}-${{ github.run_id }}
          restore-keys: |
            analysis-data-${{ runner.os }}-
```

How it works:
- **Restore**: exact key `analysis-data-Linux-<run_id>` won't exist yet (unique per run) → falls back to `restore-keys` prefix → restores the most recent `analysis-data-Linux-*` entry
- **Post-step**: since the exact key was not matched, the post-step **saves** the enriched DB under the new unique key
- Each run builds on the previous run's data and persists its additions
- Old cache entries are auto-evicted by GitHub after 7 days of non-access (only the latest entry gets restored via prefix match, so older entries expire naturally)
- At ~37 MB/stock/year and 10 GB repo limit, storage is comfortable for years

- [ ] **Step 2: Verify the fix by examining two consecutive runs**

After merging, trigger two runs on `main`:
```bash
gh workflow run daily_analysis.yml --ref main -f mode=full -f force_run=true
# Wait for completion, then:
gh run view <run_id> --log 2>/dev/null | grep -E "^analyze\t(Restore analysis data cache|Post Restore analysis data cache)\t"
```

**Expected on Run 1 (first run after fix):**
```
Restore: Cache not found for input keys: analysis-data-Linux-<run1_id>
Post:    Cache saved with key: analysis-data-Linux-<run1_id>
```

**Expected on Run 2:**
```
Restore: Cache restored from key: analysis-data-Linux-<run1_id>
Post:    Cache saved with key: analysis-data-Linux-<run2_id>
```

Verify Run 2's `analysis_history` count is higher than Run 1's (accumulated data).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/daily_analysis.yml
git commit -m "fix: use dynamic cache key so each run persists enriched data

Static key analysis-data-Linux was immutable after first save,
causing all subsequent runs to discard new analysis history,
backtest results, and provider cache updates. Dynamic key with
restore-keys prefix ensures each run saves its enriched DB."
```

---

## Task 2: Add data retention pruning to analysis DB (Layer 2 — content)

**Files:**
- Modify: `src/storage.py` (add retention methods)
- Modify: `src/config.py` (add retention config)
- Create: `tests/test_storage_retention.py`

Without retention, the DB grows ~22 MB/stock/year. This task adds opt-in pruning that the pipeline can call after each run.

**Important:** Retention here operates on **row-level timestamps** inside the SQLite DB (e.g., `analysis_history.created_at`, `stock_daily.date`), not on GitHub cache entries. The "days" in `RETENTION_ANALYSIS_HISTORY_DAYS=180` means "delete rows whose own `created_at` timestamp is older than 180 calendar days from now." This is independent of how many times the action ran, when cache entries were created, or what `run_id` they carry.

### Design decisions to revisit after book study

> **Note for revision:** The retention windows below (180 days for analysis history, 365 days for daily data, 90 days for news) are initial estimates. After studying the securities analysis book, revise these based on:
> - What historical lookback windows are standard for technical/fundamental analysis?
> - How far back should agent memory reach for meaningful pattern recognition?
> - What news retention period is useful for sentiment trend analysis?
> - Are there specific cycle lengths (earnings quarters, macro cycles) that should inform retention boundaries?

- [ ] **Step 1: Add retention configuration to config.py**

Add to `src/config.py` in the appropriate config section:

```python
# Data retention (days, 0 = keep forever)
RETENTION_ANALYSIS_HISTORY_DAYS: int = int(os.getenv("RETENTION_ANALYSIS_HISTORY_DAYS", "180"))
RETENTION_NEWS_INTEL_DAYS: int = int(os.getenv("RETENTION_NEWS_INTEL_DAYS", "90"))
RETENTION_STOCK_DAILY_DAYS: int = int(os.getenv("RETENTION_STOCK_DAILY_DAYS", "365"))
RETENTION_PROVIDER_CACHE_DAYS: int = int(os.getenv("RETENTION_PROVIDER_CACHE_DAYS", "30"))
```

- [ ] **Step 2: Write failing tests for retention logic**

Create `tests/test_storage_retention.py`:

```python
"""Tests for data retention pruning in DatabaseManager."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from src.storage import DatabaseManager


@pytest.fixture
def db():
    """Fresh in-memory database for each test."""
    DatabaseManager.reset()
    with patch.dict("os.environ", {"DATABASE_URL": "sqlite:///:memory:"}):
        manager = DatabaseManager()
        yield manager
        DatabaseManager.reset()


class TestAnalysisHistoryRetention:
    def test_prune_deletes_records_older_than_threshold(self, db):
        """Records older than retention_days should be deleted."""
        old_date = datetime.now() - timedelta(days=200)
        recent_date = datetime.now() - timedelta(days=10)

        # Insert old and recent analysis records
        db.save_analysis_history(
            result={"summary": "old analysis"},
            query_id="old-query",
            report_type="simple",
            news_content="old news",
        )
        # Manually backdate the old record
        with db.get_session() as session:
            from src.storage import AnalysisHistory
            old_record = session.query(AnalysisHistory).filter_by(query_id="old-query").first()
            old_record.created_at = old_date
            session.commit()

        db.save_analysis_history(
            result={"summary": "recent analysis"},
            query_id="recent-query",
            report_type="simple",
            news_content="recent news",
        )

        deleted = db.prune_analysis_history(retention_days=180)

        assert deleted == 1
        remaining = db.get_analysis_history()
        assert len(remaining) == 1
        assert remaining[0].query_id == "recent-query"

    def test_prune_cascades_to_backtest_results(self, db):
        """Deleting old analysis_history should cascade-delete backtest_results."""
        # Setup: create analysis + linked backtest, backdate, prune
        # Verify backtest_result is also gone
        pass  # Full implementation in step 3

    def test_prune_zero_retention_keeps_everything(self, db):
        """retention_days=0 means keep forever."""
        db.save_analysis_history(
            result={"summary": "old"},
            query_id="q1",
            report_type="simple",
        )
        with db.get_session() as session:
            from src.storage import AnalysisHistory
            record = session.query(AnalysisHistory).filter_by(query_id="q1").first()
            record.created_at = datetime.now() - timedelta(days=9999)
            session.commit()

        deleted = db.prune_analysis_history(retention_days=0)
        assert deleted == 0


class TestNewsIntelRetention:
    def test_prune_deletes_old_news(self, db):
        """News older than retention_days should be pruned."""
        # Insert old and recent news_intel records
        # Prune with retention_days=90
        # Verify only recent news remains
        pass  # Full implementation in step 3

    def test_prune_zero_retention_keeps_everything(self, db):
        """retention_days=0 means keep forever."""
        pass  # Full implementation in step 3


class TestStockDailyRetention:
    def test_prune_deletes_old_daily_data(self, db):
        """Daily data older than retention_days should be pruned."""
        pass  # Full implementation in step 3

    def test_prune_zero_retention_keeps_everything(self, db):
        """retention_days=0 means keep forever."""
        pass  # Full implementation in step 3
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/test_storage_retention.py -v
```

Expected: FAIL — `prune_analysis_history` method doesn't exist yet.

- [ ] **Step 4: Implement retention methods in storage.py**

Add to `DatabaseManager` class in `src/storage.py`:

```python
def prune_analysis_history(self, retention_days: int = 180) -> int:
    """Delete analysis_history records older than retention_days.

    Cascades to backtest_result via foreign key.
    Returns count of deleted records. 0 retention_days = keep forever.
    """
    if retention_days <= 0:
        return 0
    cutoff = datetime.now() - timedelta(days=retention_days)
    with self.get_session() as session:
        count = session.query(AnalysisHistory).filter(
            AnalysisHistory.created_at < cutoff
        ).delete(synchronize_session="fetch")
        session.commit()
        if count:
            logger.info(f"[Retention] Pruned {count} analysis_history records older than {retention_days}d")
        return count

def prune_news_intel(self, retention_days: int = 90) -> int:
    """Delete news_intel records older than retention_days.

    Returns count of deleted records. 0 retention_days = keep forever.
    """
    if retention_days <= 0:
        return 0
    cutoff = datetime.now() - timedelta(days=retention_days)
    with self.get_session() as session:
        count = session.query(NewsIntel).filter(
            NewsIntel.fetched_at < cutoff
        ).delete(synchronize_session="fetch")
        session.commit()
        if count:
            logger.info(f"[Retention] Pruned {count} news_intel records older than {retention_days}d")
        return count

def prune_stock_daily(self, retention_days: int = 365) -> int:
    """Delete stock_daily records older than retention_days.

    Returns count of deleted records. 0 retention_days = keep forever.
    """
    if retention_days <= 0:
        return 0
    cutoff_date = (datetime.now() - timedelta(days=retention_days)).date()
    with self.get_session() as session:
        count = session.query(StockDaily).filter(
            StockDaily.date < cutoff_date
        ).delete(synchronize_session="fetch")
        session.commit()
        if count:
            logger.info(f"[Retention] Pruned {count} stock_daily records older than {retention_days}d")
        return count

def run_retention(self, config=None) -> dict:
    """Run all retention pruning. Returns dict of {table: deleted_count}.

    Reads retention windows from config or uses defaults.
    Designed to be called once at end of each pipeline run.
    """
    from src.config import (
        RETENTION_ANALYSIS_HISTORY_DAYS,
        RETENTION_NEWS_INTEL_DAYS,
        RETENTION_STOCK_DAILY_DAYS,
    )
    if config:
        ah_days = getattr(config, "RETENTION_ANALYSIS_HISTORY_DAYS", RETENTION_ANALYSIS_HISTORY_DAYS)
        ni_days = getattr(config, "RETENTION_NEWS_INTEL_DAYS", RETENTION_NEWS_INTEL_DAYS)
        sd_days = getattr(config, "RETENTION_STOCK_DAILY_DAYS", RETENTION_STOCK_DAILY_DAYS)
    else:
        ah_days = RETENTION_ANALYSIS_HISTORY_DAYS
        ni_days = RETENTION_NEWS_INTEL_DAYS
        sd_days = RETENTION_STOCK_DAILY_DAYS

    results = {
        "analysis_history": self.prune_analysis_history(ah_days),
        "news_intel": self.prune_news_intel(ni_days),
        "stock_daily": self.prune_stock_daily(sd_days),
    }
    total = sum(results.values())
    if total:
        logger.info(f"[Retention] Total pruned: {total} records across {sum(1 for v in results.values() if v)} tables")
    return results
```

- [ ] **Step 5: Complete test stubs and run all tests**

Fill in the `pass` stubs in `tests/test_storage_retention.py` with full implementations following the pattern of `test_prune_deletes_records_older_than_threshold`.

```bash
python -m pytest tests/test_storage_retention.py -v
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add src/storage.py src/config.py tests/test_storage_retention.py
git commit -m "feat: add configurable data retention pruning to DatabaseManager

Adds prune_analysis_history(), prune_news_intel(), prune_stock_daily()
with configurable retention windows (env vars, default 180/90/365 days).
run_retention() convenience method for end-of-pipeline cleanup.
0 = keep forever. Cascades to backtest_result via FK."
```

---

## Task 3: Add TTL eviction to provider cache (Layer 2 — content)

**Files:**
- Modify: `data_provider/shared/cache.py`
- Create: `tests/test_shared_cache_ttl.py`

The provider cache at `data/provider_cache.db` has no eviction. Stale entries accumulate forever. Add TTL-based eviction. Like Task 2, the TTL operates on the row's own `fetched_at` timestamp, not on the GitHub cache entry age.

- [ ] **Step 1: Write failing test for TTL eviction**

Create `tests/test_shared_cache_ttl.py`:

```python
"""Tests for TTL-based eviction in ProviderCache."""
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import patch

from data_provider.shared.cache import ProviderCache


@pytest.fixture
def cache(tmp_path):
    return ProviderCache(cache_dir=str(tmp_path))


class TestTTLEviction:
    def test_evict_removes_entries_older_than_ttl(self, cache):
        """Entries older than ttl_days should be evicted."""
        cache.put("old-key", {"data": "old"}, provider="test")

        # Backdate the entry
        cache._execute(
            "UPDATE cache_entries SET fetched_at = ? WHERE key = ?",
            ((datetime.now() - timedelta(days=45)).isoformat(), "old-key"),
        )

        cache.put("fresh-key", {"data": "fresh"}, provider="test")

        evicted = cache.evict(ttl_days=30)
        assert evicted == 1
        assert cache.get("old-key") is None
        assert cache.get("fresh-key") is not None

    def test_evict_zero_ttl_keeps_everything(self, cache):
        """ttl_days=0 means keep forever."""
        cache.put("key", {"data": "value"}, provider="test")
        cache._execute(
            "UPDATE cache_entries SET fetched_at = ? WHERE key = ?",
            ((datetime.now() - timedelta(days=9999)).isoformat(), "key"),
        )
        evicted = cache.evict(ttl_days=0)
        assert evicted == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_shared_cache_ttl.py -v
```

Expected: FAIL — `evict` method doesn't exist.

- [ ] **Step 3: Implement evict() in ProviderCache**

Add to `ProviderCache` class in `data_provider/shared/cache.py`:

```python
def evict(self, ttl_days: int = 30) -> int:
    """Delete cache entries older than ttl_days. Returns count deleted.

    ttl_days=0 means keep forever.
    """
    if ttl_days <= 0:
        return 0
    cutoff = (datetime.now() - timedelta(days=ttl_days)).isoformat()
    with self._lock:
        cursor = self._execute(
            "DELETE FROM cache_entries WHERE fetched_at < ?", (cutoff,)
        )
        count = cursor.rowcount if cursor else 0
        if count:
            logger.info(f"[ProviderCache] Evicted {count} entries older than {ttl_days}d")
        return count
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_shared_cache_ttl.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add data_provider/shared/cache.py tests/test_shared_cache_ttl.py
git commit -m "feat: add TTL-based eviction to ProviderCache

evict(ttl_days) deletes cache entries older than the threshold.
Default 30 days. 0 = keep forever."
```

---

## Task 4: Wire retention into pipeline end-of-run (connects Layer 2 to pipeline lifecycle)

**Files:**
- Modify: `src/core/pipeline.py` (call `run_retention()` after analysis completes)
- Modify: `.env.example` (document new env vars)
- Modify: `docs/CHANGELOG.md` (unreleased entry)

This task ensures that Layer 2 pruning runs automatically at the end of each pipeline execution, **before** Layer 1 saves the DB snapshot to GitHub cache. This way, the cached snapshot is already pruned — keeping the cache entry size bounded.

- [ ] **Step 1: Add retention call at end of pipeline run**

In `src/core/pipeline.py`, after the analysis loop completes and before the final log message, add:

```python
# Run data retention pruning
try:
    retention_results = self.db.run_retention()
    if sum(retention_results.values()) > 0:
        logger.info(f"[Retention] Cleanup complete: {retention_results}")
except Exception as e:
    logger.warning(f"[Retention] Pruning failed (non-fatal): {e}")
```

Also wire provider cache eviction:

```python
try:
    from data_provider.shared.cache import ProviderCache
    from src.config import RETENTION_PROVIDER_CACHE_DAYS
    provider_cache = ProviderCache()
    provider_cache.evict(ttl_days=RETENTION_PROVIDER_CACHE_DAYS)
except Exception as e:
    logger.warning(f"[Retention] Provider cache eviction failed (non-fatal): {e}")
```

Place both blocks in a `_run_retention()` private method and call it from the main run method.

- [ ] **Step 2: Update .env.example with new config**

Add to `.env.example`:

```bash
# ==========================================
# Data Retention (days, 0 = keep forever)
# These control how long individual data ROWS are kept in the SQLite DB,
# based on each row's own timestamp. Independent of GitHub Actions cache
# entry lifecycle (which is managed automatically by GitHub).
# ==========================================
# RETENTION_ANALYSIS_HISTORY_DAYS=180
# RETENTION_NEWS_INTEL_DAYS=90
# RETENTION_STOCK_DAILY_DAYS=365
# RETENTION_PROVIDER_CACHE_DAYS=30
```

- [ ] **Step 3: Update CHANGELOG**

Add to `docs/CHANGELOG.md` under `[Unreleased]`:

```markdown
- [修复] GitHub Actions 缓存使用动态 key，每次运行保存分析数据供后续运行使用（原静态 key 导致仅首次运行数据被缓存）
- [新功能] 数据库保留策略：analysis_history(180天)、news_intel(90天)、stock_daily(365天)、provider_cache(30天)，可通过环境变量配置，0 表示永久保留
```

- [ ] **Step 4: Commit**

```bash
git add src/core/pipeline.py .env.example docs/CHANGELOG.md
git commit -m "feat: wire data retention into pipeline end-of-run

Calls run_retention() and provider cache eviction after analysis
completes. Non-fatal on failure. Configurable via env vars."
```

---

## Task 5: Verification and documentation

**Files:**
- Modify: `docs/data-provider-api-keys-setup.md` (mention cache behavior)

- [ ] **Step 1: Run full test suite**

```bash
./scripts/ci_gate.sh
```

Expected: All existing tests pass, new tests pass.

- [ ] **Step 2: Verify workflow YAML is valid**

```bash
python -m py_compile src/storage.py
python -m py_compile src/config.py
python -m py_compile data_provider/shared/cache.py
python -m py_compile src/core/pipeline.py
```

- [ ] **Step 3: Commit any final adjustments and create PR**

```bash
git push -u origin feat/cache-architecture-fix
gh pr create --title "fix: cache architecture — dynamic key + data retention" --body "..."
```

---

## Revision Notes for Next Session

> **This plan is designed to be revised.** Before execution, the author plans to study a securities analysis book and incorporate domain knowledge. Key areas likely to change:
>
> 1. **Retention windows** — The defaults (180/90/365/30 days) are engineering estimates. Securities analysis domain knowledge should inform:
>    - How far back agent memory should reach (earnings cycles? macro cycles?)
>    - What news retention supports meaningful sentiment trend analysis
>    - Whether 365 days of daily data is sufficient for long-term pattern recognition (full bull/bear cycles?)
>    - Whether different retention should apply to different stock markets (A-share vs US)
>
> 2. **What to cache** — The plan currently caches everything in `data/`. Domain knowledge may reveal that some data types are more valuable to persist than others, or that the cache should be structured differently (e.g., separate caches for different data categories with different TTLs).
>
> 3. **Agent memory depth** — Currently `limit=3` past analyses are injected. Domain knowledge may suggest a different lookback depth, or that the memory should be structured differently (e.g., include weekly summaries, earnings event markers, regime change signals).
>
> 4. **Backtest evaluation windows** — Currently hardcoded eval windows (5d/20d returns). Domain knowledge may suggest additional windows aligned with trading horizons.
>
> 5. **Data that influences analysis quality** — The investigation found that trend analysis uses a fixed 89-day window. Domain knowledge may suggest this should be configurable per market or analysis type.
