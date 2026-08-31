# News Sentiment System

## Overview

The news sentiment system fetches financial news from Alpha Vantage and enriches flow watchlist entries with relevance-weighted sentiment scores. It runs inline with Flow Monitor — when an alert creates a new `flow_watchlist_daily` entry, news is fetched automatically for that symbol.

**Single file:** `tools/news_sentiment.py` (~340 lines)
**API:** Alpha Vantage NEWS_SENTIMENT endpoint, 25 calls/day (free tier)
**Created:** 2026-02-07

---

## Why This Design

### The Problem

The original news collector (`strategies/news_collector/`, 7 files, 2000+ lines) used a 3-tier rotation system to cover ~800 symbols with 125 API calls/day across 5 API keys. In early 2026, Alpha Vantage began IP-level rate limiting, making multi-key rotation ineffective. With only 25 usable calls/day, the 800-symbol universe would take 30+ days to rotate — far too stale to be useful.

### The Insight

Flow alerts data showed ~20 unique symbols alert per day, and ~78 over a rolling 7-day window. These are the symbols where news context actually matters — you want to know "is there a catalyst driving this flow?" at the moment the alert fires. Covering the other 720 symbols with no active flow is wasted budget.

### The Decision: Alert-Driven Collection

Instead of rotating through a static universe, news is fetched on-demand when Flow Monitor creates new watchlist entries. This means:

- **25 calls/day covers all daily alert symbols** with room to spare (typically 12-28 unique symbols/day)
- **No more tiers, no rotation, no staleness tracking** — the watchlist creation event IS the trigger
- **News arrives at decision time** — when the alert fires, not hours or days later
- **Symbols that alert on consecutive days get fresh pulls each day** — each watchlist entry gets its own sentiment snapshot, making day-over-day comparison easy

### Why 3-Day Lookback

Alpha Vantage's `time_from` parameter controls how far back to search for articles. We chose 3 days because:

- Captures the **current news cycle** — earnings reactions, analyst upgrades, breaking news
- Avoids diluting signal with 2-week-old articles that aren't relevant anymore
- Fewer articles = a more meaningful relevance-weighted average
- The AV API returns up to 50 articles per call; 3 days keeps the payload focused

If a symbol has no news in 3 days, the sentiment columns stay NULL — which itself is information ("this symbol is quiet").

### Why Not Real-Time Reserve + Evening Batch

We considered splitting the budget (10 real-time during market hours + 15 evening batch). The simpler "pull at watchlist creation" approach won because:

- `flow_watchlist_daily` already deduplicates per symbol per day — natural rate limiting
- The daily unique symbol count (~20) fits comfortably under 25 calls
- No need for separate budget tracking, polling loops, or batch schedulers
- If budget exhausts on a heavy day, symbols just don't get sentiment — the watchlist still works fine

---

## Architecture

### Data Flow

```
Flow Monitor detects alert
    |
    v
fm_watchlist.update_daily_watchlist()
    |-- Creates new entry in flow_watchlist_daily
    |-- Returns created_symbols list
    |
    v
fm_main.py (hook, line ~1533)
    |-- try/except: news failure never blocks watchlist
    |
    v
tools.news_sentiment.enrich_watchlist_batch(symbols, storage)
    |-- For each symbol (excluding VIX, SPX, etc.):
    |   |-- Check API budget (25/day cap)
    |   |-- fetch_symbol_news() -> Alpha Vantage API
    |   |-- store_news_data() -> news_articles + news_symbol_sentiment tables
    |   |-- compute_sentiment_summary() -> relevance-weighted score
    |   |-- UPDATE flow_watchlist_daily SET news columns
    |
    v
symbol_dashboard view reads from flow_watchlist_daily
```

### Failure Isolation

News enrichment is completely decoupled from watchlist population:

- The hook in `fm_main.py` is wrapped in `try/except` — if the news module can't import, crashes, or the API is down, the watchlist populates normally
- Budget exhaustion is expected behavior (heavy alert days) — not treated as an error
- Transient network failures (read/connect timeouts, dropped connections) get one automatic retry inside `AlphaVantageAPI._make_request()` — see `TRANSIENT_RETRY_ATTEMPTS` / `TRANSIENT_RETRY_BACKOFF_SEC` in `core/alphavantage_api.py`. Each attempt spends a daily-budget slot, so the retry count is deliberately 1. Rate-limit responses (`Information`/`Note`) are *not* retried.
- Two autofix error types for persistent issues:
  - `news_enrichment_module_error` (WARNING): import failure, crash — something is broken in the code
  - `news_enrichment_all_failed` (WARNING): a batch failed in a way that looks *systemic* — AV API down, IP-throttled, or bad key

#### `news_enrichment_all_failed` thresholds

An all-failed batch alone is not enough to alarm. FM cycles usually enrich exactly one symbol, so a 1-symbol batch hitting one timeout is a "100% failure rate" carrying no information — that pattern produced false-positive batch-fix sessions on 2026-02-09, 2026-04-01 and 2026-07-28. Two independent triggers now gate the alarm (constants in `tools/news_sentiment.py`):

| Trigger | Constant | Meaning |
|---------|----------|---------|
| Large batch wiped out | `AUTOFIX_MIN_ATTEMPTED = 2` | One batch of ≥2 symbols failed entirely — a sample big enough to stand on its own |
| Sustained failure | `AUTOFIX_MAX_CONSECUTIVE_ALL_FAILED = 3` | 3 all-failed batches in a row, any size — catches a real outage across FM's 1-symbol cycles |

The consecutive counter is process-local (FM runs as one process for the trading day), resets on any successful enrichment, and is reported in the error payload as `consecutive_all_failed_batches`. Below-threshold all-failed batches still emit a `WARNING` to the orchestrator log — they are suppressed from the alarm, never silenced.

**Keep both triggers.** The size trigger alone (tried 2026-02-09) stops the false positives but goes blind to a genuine all-day outage during 1-symbol cycles.

### Excluded Symbols

Symbols without meaningful Alpha Vantage news endpoints:

```python
NEWS_EXCLUDED_SYMBOLS = {'VIX', 'SPX', 'NDX', 'RUT', 'DJX', 'VIXW',
                         'SPY', 'QQQ', 'IWM', 'DIA'}
```

VIX is the most common flow alert symbol (~38 alerts in 7 days) but has no stock-specific news. Excluding it saves significant budget.

---

## Relevance-Weighted Sentiment

### The Problem with Simple Averages

Alpha Vantage returns per-symbol sentiment for each article, along with a `relevance_score` (0.0 to 1.0) indicating how central the symbol is to that article. A simple `AVG(sentiment_score)` treats all articles equally — a deep NVDA analysis (relevance 0.95) counts the same as a market roundup that mentions NVDA in one sentence (relevance 0.30).

### The Solution

Weight each article's sentiment by its relevance:

```
weighted_score = sum(score_i * relevance_i) / sum(relevance_i)
```

### Worked Example

| Article | Sentiment | Relevance | Weighted Contribution |
|---------|-----------|-----------|----------------------|
| "NVDA beats earnings expectations" | +0.40 | 0.95 | 0.380 |
| "Broad market selloff hits tech" | -0.10 | 0.30 | -0.030 |
| "NVDA gets price target upgrade" | +0.35 | 0.92 | 0.322 |

```
weighted = (0.380 + -0.030 + 0.322) / (0.95 + 0.30 + 0.92)
         = 0.672 / 2.17
         = +0.31  (Bullish, dominated by focused articles)

simple avg = (0.40 + -0.10 + 0.35) / 3 = +0.22  (diluted by low-relevance article)
```

### Sentiment Label

Instead of a single word like "Somewhat-Bullish", the label shows the distribution:

```
"Bullish 2/Neutral 1"
```

Alpha Vantage's 5 labels (Bullish, Somewhat-Bullish, Neutral, Somewhat-Bearish, Bearish) are collapsed to 3 categories for readability. This tells you at a glance whether sentiment is one-sided or mixed.

---

## Database Schema

### Columns on `flow_watchlist_daily` (and `_archive`)

| Column | Type | Description |
|--------|------|-------------|
| `news_sentiment_score` | REAL | Relevance-weighted average sentiment (-1.0 to +1.0) |
| `news_sentiment_label` | TEXT | Distribution string, e.g. "Bullish 3/Bearish 1/Neutral 2" |
| `news_article_count` | INTEGER | Number of articles with sentiment for this symbol |

These are NULL when:
- The symbol is in the exclusion list (VIX, etc.)
- The API budget was exhausted before this symbol was processed
- Alpha Vantage returned no articles for the 3-day window
- The API was down or rate-limiting

### Raw Storage Tables (unchanged)

- **`news_articles`**: One row per unique article (keyed by URL, `INSERT OR IGNORE`)
- **`news_symbol_sentiment`**: One row per (article, symbol) pair with per-symbol sentiment and relevance scores

These tables accumulate raw data over time. The watchlist columns are point-in-time snapshots computed from the API response at alert time.

### `symbol_dashboard` View

Pulls the most recent watchlist entry's sentiment per symbol:

```sql
watchlist_news AS (
    SELECT symbol, news_sentiment_score, news_sentiment_label, news_article_count,
           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY entry_date DESC) as rn
    FROM flow_watchlist_daily
    WHERE news_sentiment_score IS NOT NULL
)
-- JOIN WHERE rn = 1
```

Only symbols with active (non-expired) watchlist entries show sentiment in the dashboard.

---

## CLI Usage

```bash
# Ad-hoc symbol query (stores articles + shows sentiment summary)
python tools/news_sentiment.py --symbol NVDA

# Multiple symbols
python tools/news_sentiment.py --symbols NVDA,GOOG,MSTR

# Topic research (earnings, technology, economy_macro, etc.)
python tools/news_sentiment.py --topic technology

# Custom lookback
python tools/news_sentiment.py --symbol NVDA --lookback 7

# Date range
python tools/news_sentiment.py --symbol NVDA --from 2026-01-30 --to 2026-02-06

# Check API budget
python tools/news_sentiment.py --budget

# Fetch without storing
python tools/news_sentiment.py --symbol NVDA --no-store

# Dry run (no API calls)
python tools/news_sentiment.py --symbol NVDA --dry-run
```

---

## API Budget

- **Free tier:** 25 calls/day per API key
- **Rate limiter:** `AlphaVantageRateLimiter` in `core/alphavantage_api.py` — persists daily count to disk, auto-resets at midnight Eastern
- **Typical usage:** 12-28 calls/day (matching unique alerting symbols)
- **Heavy day risk:** If 25+ unique symbols alert, later ones skip news enrichment. Watchlist still populates normally.

### Known Issue (as of 2026-02-06)

Alpha Vantage appears to enforce IP-level rate limiting beyond the per-key daily cap. The API sometimes returns a rate-limit message (`"Information": "...subscribe to premium..."`) even when the key has budget remaining. This is intermittent and may resolve on its own. The system handles it gracefully — `fetch_symbol_news()` returns None, sentiment stays NULL, autofix logs it if persistent.

---

## What Was Deprecated

The following files were moved to `Deprecated/` directories on 2026-02-07:

| File | Was | Location |
|------|-----|----------|
| `nc_main.py` | 3-tier orchestrator entry point | `strategies/news_collector/Deprecated/` |
| `nc_collector.py` | CTI pipeline with tier logic + multi-key rotation | `strategies/news_collector/Deprecated/` |
| `nc_config.py` | Multi-key config, tier quota allocation | `strategies/news_collector/Deprecated/` |
| `nc_storage.py` | DB operations + staleness tracking | `strategies/news_collector/Deprecated/` |
| `nc_health_reporter.py` | Tier performance metrics | `strategies/news_collector/Deprecated/` |
| `news_collector.py` | Manual CLI tool (replaced by news_sentiment.py) | `Deprecated/` |
| `av_news_symbol.py` | Weekend backfill script (referenced dead table) | `Deprecated/` |
| `test_nc_fix.py` | Old test file for nc imports | `Deprecated/` |

### Orchestrator Changes

- `main.py`: Step 3 (News Collection Pipeline) removed from morning sequence; `--news-collection` CLI arg removed
- `main_runners.py`: `run_news_collection()` replaced with deprecation stub; import of `nc_main` removed
- `strategies/news_collector/__init__.py`: Updated to point to new location
