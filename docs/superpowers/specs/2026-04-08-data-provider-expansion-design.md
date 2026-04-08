# Data Provider Expansion — Design Spec

**Date:** 2026-04-08

**Status:** Draft

**Scope:** Extend data provider layer with professional-grade fundamental, news, and macro data sources for US stock market analysis

## 1. Problem Statement

The current data provider layer is price-centric: `DataFetcherManager` orchestrates OHLCV and realtime quote fetchers (YfinanceFetcher, LongbridgeFetcher, Stooq). After the US market migration (`d46e7a2`), the system lacks:

- **Fundamental data** — PE, EPS, earnings, balance sheets, insider trades, institutional holdings are mostly `None` in `UnifiedRealtimeQuote`
- **Financial-grade news** — current `search_service.py` uses generic web search ("AAPL stock news"), not ticker-tagged financial events
- **Macro context** — the LLM cannot distinguish "AAPL fell on bad earnings" from "AAPL fell because the whole market sold off on a hot CPI print"
- **Cross-run memory** — the existing `AgentMemory`, `HistoryComparisonService`, and `AnalysisHistory` infrastructure is operationally inert on GitHub Actions because the SQLite DB is destroyed after each ephemeral run

## 2. Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Architecture | Category Managers | Fundamentals, news, and prices have different schemas, update frequencies, and query patterns. Separate managers with independent failover chains. |
| Budget | Freemium tiers only | FMP (250 req/day), Finnhub (60 req/min), Alpha Vantage (25 req/day), FRED (120 req/min), SEC EDGAR (10 req/sec, no key) |
| Priority focus | Fundamentals first, then news & macro | Biggest data gap in current US market setup |
| Existing code | Fully preserved | Zero changes to price pipeline, search_service.py, or SocialSentimentService |
| Cache strategy | Disk-persisted via `actions/cache` + semantic refresh | Ephemeral GHA VMs require explicit persistence; cache only skips provably-unchanged data |
| Degradation | All new managers optional | Failures return `None`; pipeline continues with available data |

## 3. Step 0 — Enable Cross-Run Persistence (Prerequisite)

### 3.1 Problem

The daily analysis workflow (`daily_analysis.yml`) runs on `ubuntu-latest` — a fresh VM every run. The SQLite database at `./data/stock_analysis.db` is created empty each time (`mkdir -p data`). This means:

- `AgentMemory` cannot accumulate prediction history or calibrate confidence
- `HistoryComparisonService` cannot detect signal changes across days
- `AnalysisHistory` records from previous runs are lost
- `StockDaily` price history must be re-fetched from scratch
- Any new provider cache would also be destroyed

### 3.2 Solution

Add `actions/cache@v4` to `daily_analysis.yml` to persist the `data/` directory between runs:

```yaml
# Add BEFORE "执行股票分析" step:
- name: Restore analysis data cache
  uses: actions/cache@v4
  with:
    path: data/
    key: analysis-data-${{ runner.os }}
```

### 3.3 What This Enables

- **AgentMemory**: Past predictions accumulate → confidence calibration activates after 30+ samples → agents learn from track record
- **HistoryComparisonService**: Detects multi-day signal shifts ("AAPL bearish 3 days → turning neutral today")
- **StockDaily**: Technical analysis gets growing lookback windows without re-fetching months of OHLCV each run
- **New provider cache**: Quarterly financial statements and FRED macro data persist between runs

### 3.4 Size & Safety

- 20-stock portfolio: DB grows ~1-3 MB/month
- GitHub cache limit: 10 GB per repo (years of headroom)
- Cache miss (first run, eviction): system works normally — just starts fresh
- Periodic pruning: drop records older than 1 year to keep bounded

## 4. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Pipeline Orchestrator                      │
│                 (src/core/pipeline.py)                        │
└───┬──────────┬──────────┬──────────┬──────────┬─────────────┘
    │          │          │          │          │
┌───▼───┐ ┌───▼────┐ ┌───▼───┐ ┌───▼────┐ ┌───▼─────┐
│ Price │ │Fundmtl │ │ News  │ │ Macro  │ │Sentiment│
│Manager│ │Manager │ │Manager│ │Manager │ │Service  │
│(exist)│ │ (NEW)  │ │ (NEW) │ │ (NEW)  │ │(exists) │
└───┬───┘ └───┬────┘ └───┬───┘ └───┬────┘ └────┬────┘
    │         │          │         │            │
 yfinance   FMP       Finnhub    FRED       adanos.org
 longbridge Finnhub   FMP        Finnhub
 stooq      AlphaVant EDGAR      FMP
            EDGAR     search_svc
```

Pipeline integration (parallel data collection):

```python
price_data    = price_manager.get_daily_data(stock_code)        # existing
fundamentals  = fundamental_manager.get_fundamentals(stock_code) # NEW
news          = news_manager.get_financial_news(stock_code)      # NEW
macro         = macro_manager.get_snapshot()                     # NEW (shared)
sentiment     = sentiment_service.get_sentiment(stock_code)      # existing
```

All five run in parallel. Each new manager returns `None` on total failure — pipeline continues with available data.

## 5. FundamentalManager

### 5.1 Provider Chain

| Priority | Provider | Free Tier | Covers |
|---|---|---|---|
| 0 (primary) | FMP | 250 req/day | Earnings, financials, ratios, insider trades, 13F holdings |
| 1 (secondary) | Finnhub | 60 req/min | Earnings calendar, basic financials, insider sentiment, ownership |
| 2 (fallback) | Alpha Vantage | 25 req/day | Income statements, balance sheets, company overview |
| 3 (last resort) | SEC EDGAR | 10 req/sec, no key | Raw XBRL filings, Form 4 (insider), 13F-HR |

### 5.2 Unified Schema

```python
@dataclass
class UnifiedFundamentalData:
    code: str
    source: str

    # Valuation (fetch fresh daily — price-dependent)
    pe_ratio: Optional[float]           # P/E (TTM)
    forward_pe: Optional[float]         # Forward P/E
    pb_ratio: Optional[float]           # Price/Book
    ps_ratio: Optional[float]           # Price/Sales
    peg_ratio: Optional[float]          # PEG ratio
    ev_ebitda: Optional[float]          # EV/EBITDA

    # Earnings (estimates: fetch fresh daily; actuals: cacheable quarterly)
    eps_ttm: Optional[float]            # EPS trailing 12mo
    eps_estimate: Optional[float]       # Next quarter EPS estimate
    revenue_ttm: Optional[float]        # Revenue trailing 12mo
    earnings_date: Optional[str]        # Next earnings date
    earnings_surprise: Optional[float]  # Last quarter surprise %

    # Profitability (cacheable — derived from quarterly filings)
    profit_margin: Optional[float]      # Net margin %
    operating_margin: Optional[float]
    roe: Optional[float]                # Return on Equity %
    roa: Optional[float]                # Return on Assets %

    # Balance Sheet (cacheable — quarterly filings)
    debt_to_equity: Optional[float]
    current_ratio: Optional[float]
    free_cash_flow: Optional[float]

    # Dividends (cacheable — declared with known dates)
    dividend_yield: Optional[float]
    payout_ratio: Optional[float]

    # Ownership Signals (fetch fresh daily — can change any day)
    insider_buy_count_90d: Optional[int]
    insider_sell_count_90d: Optional[int]
    institutional_ownership_pct: Optional[float]
    short_interest_pct: Optional[float]
```

### 5.3 Two-Phase Fetch Strategy

Each stock's fundamentals are fetched in two phases per run:

```
FundamentalManager.get_fundamentals("AAPL"):

  Phase 1 — Always fresh (every run, every stock):
    ├─ Valuation ratios (PE, PB, EV/EBITDA — price-dependent)
    ├─ Earnings estimates (forward PE, EPS estimate — analysts revise daily)
    ├─ Earnings calendar (next_earnings_date — may be rescheduled)
    ├─ Insider transactions (Form 4 — filed within 2 business days)
    ├─ Short interest
    └─ Analyst ratings (upgrades/downgrades)

  Phase 2 — Per-stock cache decision (uses Phase 1's fresh earnings date):
    ├─ Compare today vs. freshly fetched next_earnings_date for THIS stock
    ├─ If earnings date has passed → REFRESH financial statements
    │   (new quarterly data available: income, balance sheet, margins, ROE)
    └─ If not passed → USE CACHE (quarterly filings haven't changed)
```

This means in a single run analyzing 20 stocks, only the 1-2 stocks that just reported earnings get their financial statements refreshed. The other 18-19 use cached quarterly data, saving ~5-6 FMP calls each.

The refresh decision always uses the **freshly fetched** earnings date from Phase 1, not stale cache metadata. This handles rescheduled earnings correctly.

### 5.4 Failover

```
FMP ──fail──▶ Finnhub ──fail──▶ Alpha Vantage ──fail──▶ SEC EDGAR
(best coverage)  (good)        (core financials)     (raw, always available)
```

Each provider uses the existing `CircuitBreaker` pattern (3 failures → 5min cooldown → half-open probe).

## 6. NewsManager

### 6.1 Provider Chain

| Priority | Provider | Free Tier | Covers |
|---|---|---|---|
| 0 (primary) | Finnhub | 60 req/min | Ticker-tagged company news, analyst upgrades/downgrades, SEC filings list |
| 1 (secondary) | FMP | 250 req/day (shared) | Stock news, analyst estimates, earnings transcripts (limited) |
| 2 (filings) | SEC EDGAR | 10 req/sec, no key | Full-text 8-K, 10-K, 10-Q filings |
| 3 (fallback) | Existing search_service.py | Varies by engine | Generic web search — Bocha, Tavily, Brave, SerpAPI, SearXNG |

### 6.2 Unified Schema

```python
class NewsEventType(Enum):
    EARNINGS = "earnings"
    ANALYST_RATING = "analyst_rating"
    SEC_FILING = "sec_filing"
    INSIDER = "insider"
    M_AND_A = "m_and_a"
    GENERAL = "general"

@dataclass
class UnifiedNewsItem:
    title: str
    url: str
    published_at: datetime
    source_name: str                  # "finnhub", "fmp", "edgar", "tavily"
    tickers: List[str]                # Related tickers ["AAPL", "MSFT"]
    event_type: NewsEventType
    sentiment: Optional[float]        # -1.0 to 1.0 (provider-supplied)
    summary: Optional[str]
    body: Optional[str]               # Full article body (if fetched)
    relevance_score: float = 0.0      # 0-1, computed by NewsManager
```

### 6.3 Processing Pipeline

```
NewsManager.get_financial_news("AAPL", days=7)
  ├─▶ Finnhub: /company-news + /stock/recommendation
  ├─▶ FMP: /stock_news
  ├─▶ SEC EDGAR: /submissions (recent 8-K filings)
  ├─▶ search_service (existing): "AAPL news" fallback
  ▼
  Deduplication (URL match + title similarity)
  ▼
  Relevance scoring (recency × source authority × event type)
  ▼
  Sorted List[UnifiedNewsItem]
```

News is always fetched fresh (inherently time-sensitive). Cached previous-day items are used only for deduplication.

## 7. MacroManager

### 7.1 Provider Chain

| Priority | Provider | Free Tier | Covers |
|---|---|---|---|
| 0 (primary) | FRED | 120 req/min, free key | Fed funds rate, CPI/PPI/PCE, treasury yields, unemployment |
| 1 (calendar) | Finnhub | 60 req/min (shared) | Forward-looking economic calendar, sector performance |
| 2 (fallback) | FMP | 250 req/day (shared) | Treasury rates, economic indicators, sector data |

### 7.2 Pre-configured FRED Series

```python
MACRO_SERIES = {
    "fed_funds_rate":   "FEDFUNDS",
    "fed_funds_upper":  "DFEDTARU",
    "cpi_yoy":          "CPIAUCSL",
    "core_cpi_yoy":     "CPILFESL",
    "pce_yoy":          "PCEPI",
    "ppi_yoy":          "PPIACO",
    "treasury_2y":      "DGS2",
    "treasury_10y":     "DGS10",
    "treasury_30y":     "DGS30",
    "yield_spread":     "T10Y2Y",       # 10Y-2Y spread (inversion signal)
    "unemployment":     "UNRATE",
    "nonfarm_payrolls": "PAYEMS",
    "vix":              "VIXCLS",
}
```

### 7.3 Unified Schema

```python
@dataclass
class MacroIndicator:
    name: str                          # "fed_funds_rate"
    display_name: str                  # "Federal Funds Rate"
    value: float                       # 5.33
    previous_value: Optional[float]    # 5.50
    change: Optional[float]            # -0.17
    unit: str                          # "%"
    as_of_date: str                    # "2026-03-01"
    source: str                        # "fred"

@dataclass
class EconEvent:
    event: str                         # "FOMC Meeting"
    date: str                          # "2026-04-15"
    impact: str                        # "high" | "medium" | "low"
    estimate: Optional[float]
    previous: Optional[float]

@dataclass
class UnifiedMacroSnapshot:
    timestamp: datetime
    indicators: Dict[str, MacroIndicator]
    upcoming_events: List[EconEvent]
    market_regime: str                 # "risk_on" | "risk_off" | "neutral"
                                       # computed from yield curve + VIX
```

### 7.4 Shared Across Stocks

`macro_manager.get_snapshot()` is called once per daily run, not per stock. The same `UnifiedMacroSnapshot` is passed to all stock analyses — macro context is market-wide.

### 7.5 Market Review vs. Per-Stock Analysis

The pipeline supports two modes (see `daily_analysis.yml`):
- **Market review** (`--market-review`): Uses MacroManager snapshot + index data from existing price pipeline. No per-stock fundamental/news data needed.
- **Per-stock analysis**: Uses all five data sources. FundamentalManager and NewsManager operate per-stock with independent cache decisions per ticker. MacroManager snapshot is shared.

In a `full` run (the default), both modes execute. The macro snapshot is fetched once and shared across the market review and all per-stock analyses.

## 8. Cache Layer — Persistent Smart Cache

### 8.1 Design Principle

**"Every field is either fetched fresh today, or provably unchanged at the source."**

The cache exists to avoid wasting limited free-tier API calls on data that provably has not changed — NOT to skip fetching data that "probably" hasn't changed.

### 8.2 Refresh Strategy

**Always fetch fresh** (changes unpredictably, affects today's decision):
- Valuation ratios (PE, PB — price-dependent)
- Earnings estimates, forward PE (analysts revise daily)
- Insider transactions (Form 4 filings appear daily)
- Short interest
- Analyst ratings (upgrades/downgrades)
- News (inherently time-sensitive)
- Economic calendar (today's events matter)

**Cache OK** (provably unchanged, verified before use):
- Financial statements — reported numbers don't change until next quarterly filing; cache until `next_earnings_date` passes
- Profitability & balance sheet ratios — derived from the same fixed quarterly filings
- Dividends — declared with known dates; cache until ex-dividend date passes
- Institutional holdings (13F) — quarterly filing, cache between filing windows
- FRED macro series — verified unchanged via FRED's metadata API (`last_updated` field)

### 8.3 Storage

SQLite at `./data/provider_cache.db` (colocated with the main DB under `data/`, so both are covered by the single `actions/cache` path):

```sql
CREATE TABLE cache_entries (
    key         TEXT PRIMARY KEY,   -- "fund:AAPL:financials"
    data        TEXT NOT NULL,      -- JSON-serialized payload
    meta        TEXT,               -- JSON: earnings dates, FRED timestamps
    fetched_at  TEXT NOT NULL,      -- ISO timestamp
    provider    TEXT,               -- "fmp", "finnhub", etc.
    hits        INTEGER DEFAULT 0
);
```

### 8.4 Fallback on Provider Failure

If a "fetch fresh" call fails after exhausting the failover chain, the cache serves last-known data with a staleness marker: `{ data: {...}, stale: true, as_of: "2026-04-07" }`. The LLM prompt includes the staleness warning so it can factor that into confidence. Stale data with a warning beats no data.

### 8.5 GitHub Actions Persistence

Persisted via `actions/cache@v4` as part of the `data/` directory (see Step 0). Cache miss = full fetch, not an error. The system works correctly with or without the cache.

## 9. Shared Infrastructure

### 9.1 Shared Rate Limiter

Multiple managers share providers (e.g., FMP used by FundamentalManager + NewsManager). A shared per-provider token-bucket rate limiter prevents exceeding free-tier quotas:

```python
RATE_LIMITS = {
    "fmp":           RateLimit(max_calls=250, period="day"),
    "finnhub":       RateLimit(max_calls=60,  period="minute"),
    "alpha_vantage": RateLimit(max_calls=25,  period="day"),
    "fred":          RateLimit(max_calls=120, period="minute"),
    "sec_edgar":     RateLimit(max_calls=10,  period="second"),
}
```

When a provider's budget is exhausted, managers automatically fall to the next provider in their chain.

### 9.2 Circuit Breaker

Reuse the existing `CircuitBreaker` class from `data_provider/realtime_types.py`. Each new fetcher gets its own circuit breaker instance.

## 10. API Budget Analysis

For a 20-stock portfolio, daily run without cache:

| Provider | Budget | Estimated calls | Status |
|---|---|---|---|
| FMP | 250/day | ~170 (fundamentals + news) | OK (80 headroom) |
| Finnhub | 60/min | ~105 (spread over ~10 min) | OK |
| Alpha Vantage | 25/day | 0 (failover only) | Reserved |
| FRED | 120/min | ~15 series | Trivial |
| SEC EDGAR | 10/sec | ~20 | Trivial |

With cache (quarterly data hits): FMP drops to ~100 calls, freeing headroom for scaling to 30+ stocks.

## 11. Directory Structure

```
data_provider/
├── base.py                        # existing (untouched)
├── yfinance_fetcher.py            # existing (untouched)
├── longbridge_fetcher.py          # existing (untouched)
├── tickflow_fetcher.py            # existing (untouched)
├── realtime_types.py              # existing (untouched)
├── fundamental_adapter.py         # existing (untouched)
│
├── shared/                        # NEW
│   ├── rate_limiter.py            # Token-bucket per-provider rate limiter
│   └── cache.py                   # TTL cache (SQLite-backed)
│
├── fundamental/                   # NEW
│   ├── __init__.py
│   ├── base.py                    # BaseFundamentalFetcher ABC
│   ├── manager.py                 # FundamentalManager
│   ├── types.py                   # UnifiedFundamentalData
│   ├── fmp_fetcher.py
│   ├── finnhub_fetcher.py
│   ├── alpha_vantage_fetcher.py
│   └── edgar_fetcher.py
│
├── news/                          # NEW
│   ├── __init__.py
│   ├── base.py                    # BaseNewsFetcher ABC
│   ├── manager.py                 # NewsManager (dedup + scoring)
│   ├── types.py                   # UnifiedNewsItem, NewsEventType
│   ├── finnhub_fetcher.py
│   ├── fmp_fetcher.py
│   ├── edgar_fetcher.py
│   └── search_adapter.py          # Wraps existing search_service.py
│
└── macro/                         # NEW
    ├── __init__.py
    ├── base.py                    # BaseMacroFetcher ABC
    ├── manager.py                 # MacroManager
    ├── types.py                   # MacroIndicator, UnifiedMacroSnapshot, EconEvent
    ├── fred_fetcher.py
    └── finnhub_fetcher.py
```

## 12. Configuration

New environment variables (all optional — system works without them):

```env
# FMP (Financial Modeling Prep)
FMP_API_KEY=

# Finnhub
FINNHUB_API_KEY=

# Alpha Vantage
ALPHA_VANTAGE_API_KEY=

# FRED (Federal Reserve Economic Data)
FRED_API_KEY=

# SEC EDGAR requires a User-Agent email, not a key
SEC_EDGAR_USER_AGENT=your-email@example.com

# Provider cache (optional)
PROVIDER_CACHE_ENABLED=true
PROVIDER_CACHE_DIR=./data/provider_cache.db
```

`.env.example` and docs must be updated per AGENTS.md rules.

### 12.1 Minimum Required Keys for Full Functionality

While all keys are technically optional (graceful degradation), the following **must** be configured in GitHub Actions Secrets to deliver the data this initiative is designed to provide:

| Secret | Provider | What breaks without it |
|---|---|---|
| `FMP_API_KEY` | FMP | No fundamental data (earnings, financials, ratios, insider, institutional) |
| `FINNHUB_API_KEY` | Finnhub | No financial-grade news, no analyst ratings, no economic calendar |
| `FRED_API_KEY` | FRED | No macro context (Fed rate, CPI, treasury yields, yield curve) |

SEC EDGAR requires only `SEC_EDGAR_USER_AGENT` (a contact email, not a key) set as a GitHub Actions Variable.

Without these 3 keys, all new managers fall back to existing providers and the initiative delivers no new data. Configuring them is a deployment prerequisite, not an optional enhancement.

## 13. Graceful Degradation

- No API keys configured → managers skip gracefully, pipeline uses existing data only
- Single provider down → failover chain activates
- All providers down → return `None`, pipeline continues without that data category
- Cache miss (first run) → full fetch, no error
- Rate limit exhausted mid-batch → serve cached data with staleness warning for remaining stocks

## 14. Out of Scope

- Real-time streaming / WebSocket feeds
- Options data (greeks, chain, unusual activity)
- Intraday data (sub-daily OHLCV)
- Paid provider tiers
- Changes to existing `DataFetcherManager`, `search_service.py`, or `SocialSentimentService`
- LLM prompt template changes (separate task — consuming the new data)
