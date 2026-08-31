# Earnings Intelligence System — Technical Guide

**System:** Options Scanner — Earnings Intelligence Strategy
**Location:** `strategies/earnings_intel/`
**Authors:** Ben and Claude
**Last updated:** 2026-02-26
**Status:** Production. Phases 0-3 of the February 2026 refactor are complete. Signal thresholds are provisional (calibration pending ~March 2026).

---

## 1. System Purpose & Philosophy

The Earnings Intelligence (EI) system identifies **mispriced options around earnings events** by comparing what the market expects a stock to move versus what it has historically moved. When the market systematically underprices a stock's typical earnings move, EI flags the opportunity.

EI operates on a **proactive** model: it scans the entire KLMN 800 universe and surfaces opportunities *before* earnings, rather than reacting to flow or price signals after the fact. This distinguishes it from the Flow Monitor, which is reactive — detecting unusual options activity as it happens.

The system produces two investor-facing outputs:

1. **`earnings_upcoming`** — the full universe of upcoming earnings with expected moves, signals, and timing data. Updated daily (expected moves recalculation) and weekly (Finnhub calendar refresh).
2. **`earnings_watchlist`** — a filtered, enriched view of the best opportunities. Only stocks meeting the signal threshold and liquidity gate appear here. This is the "action list."

Design principles:
- **Morning-first**: The pipeline runs as Step 1.2 in the daily orchestrator, before market open. Signals are fresh when the trading day begins.
- **Fail gracefully**: Each of the 6 pipeline sub-steps runs in its own `try/except`. A failure in news enrichment does not block watchlist population. A failure in snapshots does not block post-earnings calculations.
- **Two-source resilience**: Finnhub is the primary earnings calendar, YFinance is the fallback. Earnings snapshots are the primary IV/price source for post-earnings analysis, `historical_prices` is the fallback.
- **No fake data**: Every metric is measured from actual database state. If a calculation can't be performed (missing price data, empty snapshots), the column is NULL — never estimated or assumed.

---

## 2. Data Sources & External APIs

### Finnhub (Primary Earnings Calendar)
- **Endpoint:** `GET https://finnhub.io/api/v1/calendar/earnings`
- **Rate limit:** 60 requests/minute (free tier)
- **Usage:** 3-4 API calls per Friday refresh (date-range scan, 30-day chunks, 90 days ahead)
- **Provides:** `earnings_date`, `earnings_time` (bmo/amc/dmh), `eps_estimate`, `revenue_estimate`
- **Config:** `config.json` → `finnhub` section
- **Client:** `core/finnhub_api.py` — `FinnhubAPI` (low-level HTTP + rate limiter) + `FinnhubEarningsClient` (high-level wrapper with chunked fetching)

### YFinance (Fallback Calendar)
- **Usage:** Per-symbol calls for KLMN 800 symbols not returned by Finnhub
- **Provides:** `earnings_date` (timing data is unreliable — returns analyst call times, not results release)
- **Typical coverage gap:** ~440 symbols fall through to YFinance after Finnhub's 280-290 symbol results

### Tradier (Options & IV Data — via Option Pipeline)
- **Not called directly by EI.** EI reads from `option_symbol_summary`, which is populated by the Option Pipeline strategy using the Tradier API.
- **Data consumed:** `front_month_iv`, `iv_30dte`, `iv_45dte`, `total_call_oi`, `total_put_oi`, daily close prices via `historical_prices`

### Alpha Vantage (News Sentiment)
- **Endpoint:** News sentiment API
- **Rate limit:** 25 calls/day (single API key)
- **Usage:** Enriches watchlist entries with relevance-weighted sentiment scores
- **Budget exhaustion is not an error** — the pipeline continues; unenriched symbols retain NULL sentiment columns

---

## 3. Pipeline Architecture

EI has two operational modes, both orchestrated by `ei_main.py`:

### Daily Pipeline (`run_daily_pipeline()`)
Runs as **Step 1.2** in the morning orchestrator (before market open). Six sub-steps execute sequentially:

| # | Sub-step | Function | What It Does |
|---|----------|----------|--------------|
| 1 | Snapshot Collection | `SnapshotCollector.collect_daily_snapshots()` | Captures IV, price, OI, and put/call ratio for stocks within T-7 to T+3 of their earnings date. Writes to `earnings_snapshots`. |
| 2 | Post-Earnings Calculation | `PostEarningsCalculator.calculate_post_earnings_metrics()` | For stocks that reported earnings yesterday/recently: calculates price moves (1-day through 5-day), IV crush metrics, and move-vs-expected. Writes to `earnings_moves`. |
| 3 | Expected Moves Update | `update_expected_moves()` | Recalculates `expected_move_pct`, `straddle_expected_move_pct`, `historical_avg_move_pct`, `relative_underpricing_pct`, and `earnings_play_signal` for all upcoming earnings. Updates `earnings_upcoming`. |
| 4 | Watchlist Population | `populate_watchlist()` | Filters `earnings_upcoming` to stocks meeting signal + liquidity criteria. Writes/updates `earnings_watchlist`. Manages the UPCOMING→TODAY→T+3→deleted lifecycle. |
| 5 | News Enrichment | Inline (no separate module) | Fetches Alpha Vantage news sentiment for new watchlist entries and T-1 symbols. Updates `news_sentiment_score`, `news_sentiment_label`, `news_article_count` on `earnings_watchlist`. |
| 6 | Arbitrage Scan | `ArbitrageScanner.scan_morning_opportunities()` | Finds sector sympathy plays — peers with cheap IV relative to today's earnings reporters. Writes to `earnings_sector_effects`. |

**Failure cascading:** Sub-step 5 depends on sub-step 4 (needs watchlist entries to enrich). All other sub-steps are independent. The top-level `success` field is True if the pipeline completed without crashing; individual sub-step failures are logged but don't halt the pipeline.

### Weekly Refresh (`run_weekly_refresh()`)
Runs as **Step 5.2** on Fridays. Three tasks:

1. **Fetch upcoming earnings** — Finnhub bulk fetch (primary) + YFinance fallback. Populates `earnings_upcoming` with ON CONFLICT upsert that preserves analysis columns.
2. **Archive past earnings** — Moves expired entries from `earnings_upcoming` to `earnings_events`, preserving 7 signal/estimate columns.
3. **Cleanup** — Deletes entries from `earnings_upcoming` older than 7 days past their earnings date.

### Return Dict Contract
Both modes return structured dicts (not bools) consumed by the orchestrator for console output and performance tracking. Key fields:
- `success` (bool), `duration_seconds` (float), `errors` (int)
- `sub_tasks` (dict of per-step results with individual `success`, `duration`, and metrics)
- Mode-specific: `snapshots_created`, `moves_calculated`, `alerts_triggered`, `watchlist_count`, `watchlist_new`, `news_enriched`, `arb_opportunities` (daily) or `earnings_found`, `events_archived`, `records_cleaned` (weekly)

---

## 4. Signal Classification System

### The Core Metric: Relative Underpricing

The primary signal metric is **`relative_underpricing_pct`**, which answers: *"By what percentage is the market underpricing this stock's typical earnings move?"*

**Formula:**
```
relative_underpricing_pct = (historical_avg_move_pct - straddle_expected_move_pct) / straddle_expected_move_pct * 100
```

If straddle data is unavailable, the IV-based `expected_move_pct` is used as the denominator instead. If neither is available, the signal is `UNKNOWN`.

**Why relative, not absolute:** A 3% absolute difference on a 10% expected move (30% relative underpricing) is far more interesting than a 3% difference on a 50% expected move (6% relative). The absolute metric (`move_difference_pct`) is still calculated and stored for backward compatibility, but it does not drive signals.

**Coverage note:** Within 0-30 days of earnings, 96-100% of symbols have at least one expected move method populated. Beyond 30 days, ~48% lack data — these receive `UNKNOWN` signals, which is correct (insufficient data to form a recommendation).

### Signal Tiers

Calculated in `ei_moves_upcoming.py:determine_earnings_play_signal()` (line 333):

| Signal | Relative Underpricing | Meaning |
|--------|----------------------|---------|
| **AVOID** | < 0% | Market *overprices* the typical move. Options are expensive relative to history. |
| **NEUTRAL** | 0% to < 15% | Slight underpricing, not enough to act on. |
| **WATCH** | 15% to < 30% | Meaningful underpricing. Worth monitoring. |
| **BUY** | 30% to < 50% | Significant underpricing. Actionable opportunity. |
| **STRONG BUY** | >= 50% | Market is substantially underpricing this stock's earnings move. |
| **UNKNOWN** | N/A (missing data) | Insufficient IV/price data to compute a signal. |

Thresholds are configurable in `config.json` under `earnings_play.signal_thresholds` (keys: `watch`, `buy`, `strong_buy`).

**Provisional status:** These thresholds were set based on distribution analysis of the KLMN 800 universe on 2026-02-10. They have not yet been validated against outcomes. Calibration requires ~100 events with `move_vs_expected_pct` data to determine whether WATCH/BUY/STRONG BUY signals correlate with profitable trades. Expected: early March 2026.

### Alert Gate

An earnings alert fires (logging + potential email notification) when *both* conditions are met:
- `relative_underpricing_pct >= 15%` (aligned with WATCH threshold)
- `total_open_interest >= 4,000` (liquidity gate — sum of call + put OI from `option_symbol_summary`)

This is computed in `ei_moves_upcoming.py:should_trigger_earnings_alert()` (line 370).

### The 0.85 Slippage Multiplier

The `straddle_expected_move_pct` includes an industry-standard **0.85 multiplier** applied to the raw at-the-money straddle price. This accounts for bid-ask spread slippage and execution costs — the *tradeable* expected move is lower than the theoretical straddle price. This makes relative underpricing values slightly higher than they would be using raw straddle prices, which is intentional: we are comparing historical moves against what a trader would actually pay.

---

## 5. Tables & Data Lifecycle

### Data Flow

```
Finnhub/YFinance ──→ earnings_upcoming ──→ earnings_watchlist (investor-facing)
                           │                       │
                           │                       ├── news_symbol_sentiment (Alpha Vantage)
                           │                       │
                     (Friday archive)         (T+4 cleanup)
                           │
                           ▼
                     earnings_events ──→ sector archives (Tier 3, 90-day COPY)
                           │
                           ▼
                     earnings_moves (post-earnings metrics)
                           │
                     earnings_snapshots (IV/price time series)
                           │
                     earnings_sector_effects (sympathy plays)
```

### Table Reference

**`earnings_upcoming`** — The universe of upcoming earnings events.
- **PK:** `symbol` (one entry per stock)
- **Written by:** `ei_fetch_upcoming.py` (weekly), `ei_moves_upcoming.py` (daily expected moves update)
- **Read by:** `ei_watchlist.py`, `ei_snapshot_collector.py`, `ei_post_earnings_calc.py`, `ei_arbitrage_scanner.py`
- **Key columns:** `earnings_date`, `earnings_time` (bmo/amc/dmh/Unknown), `expected_move_pct`, `straddle_expected_move_pct`, `historical_avg_move_pct`, `relative_underpricing_pct`, `earnings_play_signal`, `move_difference_pct`, `earnings_alert`, `eps_estimate`, `revenue_estimate`
- **Upsert pattern:** `ON CONFLICT(symbol) DO UPDATE` preserving analysis columns. `earnings_time` uses `COALESCE(NULLIF(excluded, 'Unknown'), existing)` so Finnhub timing is never overwritten by YFinance's "Unknown."

**`earnings_watchlist`** — The action list: filtered, enriched, investor-facing. 24 columns.
- **PK:** `symbol` (one entry per stock)
- **Written by:** `ei_watchlist.py:populate_watchlist()` (daily)
- **Read by:** Orchestrator (console display), Morning View TUI
- **Entry criteria:** Signal in (WATCH, BUY, STRONG BUY) AND earnings within 14 calendar days AND total OI >= 4,000
- **Lifecycle:** See Section 6

**`earnings_events`** — The archive: every earnings event after it passes.
- **PK:** `event_id` (auto-increment)
- **Written by:** `ei_main.py:run_weekly_refresh()` (Friday archive query)
- **Archived to:** Sector databases via Tier 3 (90-day COPY)
- **Signal preservation (added Feb 2026):** 7 columns copied from `earnings_upcoming` during archive: `earnings_play_signal`, `relative_underpricing_pct`, `expected_move_pct`, `straddle_expected_move_pct`, `historical_avg_move_pct`, `eps_estimate`, `revenue_estimate`

**`earnings_moves`** — Post-earnings price moves, IV changes, and move-vs-expected analysis.
- **PK:** `move_id` (auto-increment), unique on `(event_id, symbol)`
- **Written by:** `ei_post_earnings_calc.py:PostEarningsCalculator`
- **9,324 rows** as of Feb 2026 (all with price moves after the Phase 3 backfill)
- **Key columns:** `move_1day_pct` through `move_5day_pct`, `move_direction`, `max_intraday_move_pct`, `move_vs_expected_pct`, `iv_buildup_pct`, `iv_collapse_pct`, `iv_crush_severity`, `expected_move_pct`, `earnings_date` (denormalized)
- **Not archived** — stays in production indefinitely (backtest reference data)

**`earnings_snapshots`** — IV/price time series captured T-7 through T+3 around each earnings event.
- **Unique on:** `(symbol, earnings_date, snapshot_date)`
- **Written by:** `ei_snapshot_collector.py:SnapshotCollector`
- **Status:** Table redesigned Feb 2025. Collector fixed Feb 25, 2026. Data accumulating since then. Will become the primary source for post-earnings calculations once ~2 weeks of data exists (~March 11).
- **Schema:** `snapshot_id`, `symbol`, `earnings_date`, `event_id` (nullable), `snapshot_date`, `days_from_earnings`, `snapshot_type` (pre_earnings/earnings_day/post_earnings), `close_price`, `volume`, `iv_30dte`, `iv_front_month`, `iv_45dte`, `total_open_interest`, `put_call_ratio`, `is_primary_symbol`

**`earnings_sector_effects`** — Sector sympathy and arbitrage opportunities.
- **Written by:** `ei_arbitrage_scanner.py:ArbitrageScanner` and `ei_post_earnings_calc.py` sector effects calculation
- **Status:** Functionally a no-op until the arbitrage scanner finds same-day earnings reporters with populated peer mappings. The infrastructure is in place; meaningful data will accumulate as the watchlist matures.

**`news_symbol_sentiment`** — Per-symbol news sentiment from Alpha Vantage.
- **Written by:** `tools/news_sentiment.py` (called inline during sub-step 5)
- **Dedup key:** Checked by `(symbol, DATE(time_collected))` — one fetch per symbol per day

---

## 6. The Earnings Watchlist

### Schema (24 columns)

```sql
CREATE TABLE earnings_watchlist (
    symbol TEXT PRIMARY KEY,          -- Stock ticker
    status TEXT NOT NULL,             -- UPCOMING, TODAY, T+1, T+2, T+3
    current_price REAL,               -- Latest price from historical_prices
    days_to_earnings INTEGER NOT NULL,-- Positive = future, 0 = today, negative = past
    earnings_date TEXT NOT NULL,       -- YYYY-MM-DD
    earnings_time TEXT,               -- bmo, amc, dmh, Unknown
    earnings_play_signal TEXT,        -- AVOID, NEUTRAL, WATCH, BUY, STRONG BUY, UNKNOWN
    iv_percentile_30d REAL,           -- Current IV vs 30-day range
    relative_underpricing_pct REAL,   -- The signal metric
    expected_move_pct REAL,           -- Market-implied expected move
    historical_avg_move_pct REAL,     -- What the stock actually does historically
    straddle_expected_move_pct REAL,  -- ATM straddle-derived expected move (with 0.85 multiplier)
    oi_balance_text TEXT,             -- "Call-heavy", "Put-heavy", "Balanced"
    alert_count_5d INTEGER,           -- Flow alerts in last 5 days (cross-strategy)
    news_sentiment_label TEXT,        -- Bearish, Somewhat-Bearish, Neutral, Somewhat-Bullish, Bullish
    news_sentiment_score REAL,        -- Relevance-weighted sentiment (-1 to +1)
    news_article_count INTEGER,       -- Number of recent articles analyzed
    actual_move_pct REAL,             -- Populated at T+3 from earnings_moves.move_3day_pct
    move_direction TEXT,              -- "up" or "down" (T+3 enrichment)
    iv_collapse_pct REAL,             -- Post-earnings IV drop (T+3 enrichment)
    iv_crush_severity TEXT,           -- severe/high/normal/mild/minimal (T+3 enrichment)
    first_appeared_date TEXT NOT NULL, -- When the symbol first entered the watchlist
    created_at TEXT NOT NULL,         -- Row creation timestamp
    last_updated TEXT NOT NULL        -- Last modification timestamp
)
```

### Entry Criteria

A stock enters the watchlist when ALL of:
1. `earnings_play_signal` IN ('WATCH', 'BUY', 'STRONG BUY')
2. `earnings_date` is within 14 calendar days
3. `total_call_oi + total_put_oi >= 4,000` (from `option_symbol_summary`)

### Status Lifecycle

```
UPCOMING ──→ TODAY ──→ T+1 ──→ T+2 ──→ T+3 ──→ (deleted)
                                          │
                                    T+3 enrichment:
                                    actual_move_pct,
                                    move_direction,
                                    iv_collapse_pct,
                                    iv_crush_severity
```

- **UPCOMING:** `days_to_earnings > 0`. Stock hasn't reported yet.
- **TODAY:** `days_to_earnings = 0`. Earnings day.
- **T+1, T+2, T+3:** 1-3 days after earnings. Allows monitoring of the post-earnings move.
- **At T+3:** The watchlist entry is enriched with actual outcomes from `earnings_moves` (price move, direction, IV crush). This is the "was the signal right?" data point.
- **At T+4:** Row is deleted. The data lives on in `earnings_events` and `earnings_moves`.

### Upsert Pattern

`populate_watchlist()` uses `INSERT ... ON CONFLICT(symbol) DO UPDATE SET ...` with the following ownership rules:
- **INSERT** owns: all 24 columns (NULLs for post-earnings columns on first insert)
- **UPDATE** owns: `status`, `current_price`, `days_to_earnings`, and all pre-earnings analytical columns
- **T+3 enrichment UPDATE** owns: `actual_move_pct`, `move_direction`, `iv_collapse_pct`, `iv_crush_severity`
- **News enrichment UPDATE** owns: `news_sentiment_score`, `news_sentiment_label`, `news_article_count`
- **`first_appeared_date`** is set *after* `clean_database_row()` runs (because the formatter nullifies date-looking strings). Never overwritten on UPDATE.

---

## 7. IV Crush Severity Scale

Post-earnings IV typically drops as the uncertainty that justified the elevated premium resolves. The system classifies the magnitude of this drop on a 5-tier scale.

**Measurement:** `iv_collapse_pct = (post_iv - pre_iv) / pre_iv * 100` — this is a negative number (IV drops). The classification uses the absolute value.

| Tier | |IV Collapse| | Interpretation |
|------|-------------|----------------|
| **severe** | > 65% | Exceptionally large IV crush. Common in high-IV names (biotech, meme stocks). |
| **high** | 50% - 65% | Above-average crush. Expected for volatile earnings reporters. |
| **normal** | 40% - 50% | Typical post-earnings crush. ~45% is the observed center. |
| **mild** | 25% - 40% | Below-average crush. May indicate lingering uncertainty. |
| **minimal** | < 25% | Very little IV reduction. Could signal an ongoing catalyst beyond earnings. |

**Code location:** `ei_post_earnings_calc.py`, lines 529-541 (option_summary path) and lines 441-452 (snapshots path — identical thresholds).

**IV source hierarchy:**
1. `earnings_snapshots` — T-1 and T+1 IV from the snapshot time series (primary, once data accumulates)
2. `option_symbol_summary` — `front_month_iv` on the day before and day after earnings (fallback, currently the active path)

**Provisional status:** The 5-tier scale was set based on observed distributions (Feb 2026). The ~45% center for "normal" aligns with industry literature on post-earnings IV behavior. Will be refined as more data accumulates.

---

## 8. Orchestration & Scheduling

### Daily Cycle (Step 1.2)

The EI daily pipeline runs as the **second step** in the morning pre-market phase:

```
Step 1.1: Morning Option Pipeline
Step 1.2: Earnings Intelligence ← HERE (6 sub-steps)
Step 1.3: Symbol Metadata Update
Step 1.4: Database Sync (pre-market)
Step 1.5: Morning Views Generation
```

Orchestrator method: `main_runners.py:run_earnings_intelligence()` (line 1006). This replaced the former `run_earnings_pipeline()` + `run_earnings_morning_scan()` split.

**CLI shortcut:** `python main.py --earnings-intel` starts the daily cycle from this step.

### Friday Cycle (Step 5.2)

The weekly refresh runs on Fridays as part of the weekly operations phase:

```
Step 5.1: Weekly Database Backup
Step 5.2: Earnings Weekly Refresh ← HERE (Finnhub + YFinance + archive + cleanup)
Step 5.3: Sector-Based Archive
```

### Console Output

The orchestrator displays a **mission box** before the pipeline starts (listing the 6 sub-steps) and a **completion box** when it finishes (showing key metrics). The strategy layer (`ei_main.py`) owns progress lines (sub-step status, counts) but does not produce boxes or banners — that's the orchestrator's responsibility per the console output architecture.

Completion box example content:
- Snapshots collected: 12
- Moves calculated: 3
- Watchlist: 8 symbols (2 new) (3 STRONG BUY, 2 BUY, 3 WATCH)
- News enriched: 2 symbols
- Earnings alerts: 5 (1 STRONG BUY, 2 BUY, 2 WATCH)

---

## 9. Post-Earnings Analysis: Two-Source Architecture

The post-earnings calculation engine (`ei_post_earnings_calc.py`) computes metrics for each stock after it reports earnings. The calculation has a deliberate **two-source architecture** for resilience:

### Price Moves

**Primary path:** Query `earnings_snapshots` for pre-earnings and post-earnings close prices. Compute `move_1day_pct` through `move_5day_pct` as percentage changes from T0 (earnings day close).

**Fallback path:** If snapshots are empty (which they were for all events before Feb 25, 2026), query `historical_prices` for daily close prices at T-1, T0, T+1, T+2, T+3, T+5. Uses `on_or_after` date lookups to handle weekends and holidays. `max_intraday_move_pct` is approximated from T+1 OHLC as `max(|high - open|, |low - open|) / open * 100`.

### IV Changes

**Primary path:** Query `earnings_snapshots` for T-7, T-1, T+1, T+3 IV snapshots. Compute `iv_buildup_pct` (T-7 to T-1), `iv_collapse_pct` (T-1 to T+1), `iv_recovery_pct` (T+1 to T+3).

**Fallback path:** Query `option_symbol_summary` directly for `front_month_iv` on the relevant dates. This is the active path for all current data. Same IV crush severity classification applies.

### Move vs Expected

After price moves and IV are computed, the engine calculates:
```
move_vs_expected_pct = (abs(move_1day_pct) / expected_move_pct) * 100
```
Where `expected_move_pct` is the 1-day IV-based expected move as of the earnings date. A value >100 means the stock moved *more* than implied; <100 means it moved *less*. This metric is central to signal threshold calibration.

---

## 10. Performance Tracking

EI pipeline performance is written to `data/performance.db` in the `ei_pipeline_performance` table by `tools/performance_writer.py` during Phase 6 (end-of-day system maintenance).

### Tracked Metrics

| Column | Source |
|--------|--------|
| `duration_seconds` | Total pipeline wall-clock time |
| `snapshots_created` | Count of new snapshot rows written |
| `moves_calculated` | Count of post-earnings moves computed |
| `alerts_triggered` | Count of earnings alerts fired |
| `snapshot_seconds` | Sub-step 1 duration |
| `calculation_seconds` | Sub-step 2 duration |
| `expected_move_seconds` | Sub-step 3 duration |
| `watchlist_count` | Total symbols on watchlist |
| `watchlist_new` | Symbols added this run |
| `watchlist_seconds` | Sub-step 4 duration |
| `news_enriched` | Symbols that received news sentiment |
| `news_seconds` | Sub-step 5 duration |
| `earnings_found` | (Weekly) Symbols returned by Finnhub + YFinance |
| `events_archived` | (Weekly) Events moved to earnings_events |
| `records_cleaned` | (Weekly) Old entries deleted from earnings_upcoming |
| `fetch_seconds` / `archive_seconds` / `cleanup_seconds` | (Weekly) Sub-task durations |

The `run_type` column distinguishes `'daily_pipeline'` from `'weekly_refresh'` rows.

---

## 11. Known Limitations & Deferred Work

### Active Limitations

1. **Snapshot ramp-up period.** The `earnings_snapshots` collector was fixed on Feb 25, 2026. The primary price moves path (from snapshots) will not have meaningful data until ~March 11, 2026. Until then, the `historical_prices` fallback handles all post-earnings calculations. This is working correctly — it's a data accumulation gap, not a code issue.

2. **Signal thresholds are provisional.** The WATCH (15%), BUY (30%), STRONG BUY (50%) thresholds were set from universe distribution analysis, not outcome validation. Calibration requires ~100 events with `move_vs_expected_pct` data (~early March 2026). The thresholds may shift once we can answer "did STRONG BUY signals actually correspond to profitable trades?"

3. **Arbitrage scanner produces sparse output.** The sector sympathy scanner requires same-day earnings reporters with populated `industry_peer_mappings`. On most days this yields 0 opportunities. The infrastructure is sound; the feature will grow in value as the peer mapping table expands.

4. **News budget constraint.** Alpha Vantage allows 25 API calls per day across the entire system (EI + Flow Monitor). On days with many new watchlist entries, some symbols will not receive news enrichment. Budget exhaustion is treated as a non-error condition.

5. **`earnings_time` coverage.** Finnhub provides BMO/AMC timing for ~26% of the KLMN 800 universe (189 of 728 symbols as of Feb 2026). The remaining 74% show "Unknown." This is a data availability limitation of the free Finnhub tier, not a bug.

### Deferred Features

| Feature | Status | Notes |
|---------|--------|-------|
| **Snapshot wiring verification** | Deferred to ~March 11 | Verify snapshots accumulating and primary calc path fires |
| **Signal threshold recalibration** | Pending ~100 events | Will validate WATCH/BUY/STRONG BUY against actual outcomes |
| **Post-earnings Finnhub actuals** | Planned | `eps_actual` / `revenue_actual` → populate NULL `actual_eps` on `earnings_events` |
| **Scenario calculator** | Proposal written | See `docs/_local/earnings-scenario-calculator-proposal.md` (parked) |
| **YFinance deprecation** | Evaluate after 2-3 weeks | If Finnhub covers all needed symbols, drop YFinance entirely |
| **Daily Finnhub scan** | Not planned | Address only if mid-week earnings date shifts become a problem |
| **Morning View TUI screen** | Console output covers it | Dedicated TUI screen for earnings watchlist display |

---

## File Reference

| File | Role |
|------|------|
| `strategies/earnings_intel/ei_main.py` | Pipeline orchestrator (daily + weekly modes) |
| `strategies/earnings_intel/ei_fetch_upcoming.py` | Finnhub (primary) + YFinance (fallback) calendar refresh |
| `strategies/earnings_intel/ei_moves_upcoming.py` | Expected move calculation, signal classification, alert logic |
| `strategies/earnings_intel/ei_watchlist.py` | Earnings watchlist population and lifecycle management |
| `strategies/earnings_intel/ei_post_earnings_calc.py` | Post-earnings price moves, IV changes, crush severity |
| `strategies/earnings_intel/ei_snapshot_collector.py` | Daily IV/price snapshot collection (T-7 to T+3) |
| `strategies/earnings_intel/ei_arbitrage_scanner.py` | Sector sympathy / IV arbitrage opportunity scanner |
| `strategies/earnings_intel/ei_health_reporter.py` | EI-specific health status reporting |
| `strategies/earnings_intel/ei_backfill_price_moves.py` | One-time migration script (3-pass backfill, Feb 2026) |
| `core/finnhub_api.py` | Finnhub API client (rate limiter + earnings calendar) |
| `tools/news_sentiment.py` | Alpha Vantage news sentiment (shared with Flow Monitor) |
| `tools/performance_writer.py` | End-of-day performance metrics writer |
| `main_runners.py` | Orchestrator runner: `run_earnings_intelligence()` (line 1006) |

---

## Revision History

| Date | Change |
|------|--------|
| 2025-10-10 | Initial Earnings Intelligence system (PRD 0003) |
| 2026-02-10 | Signal recalibration: `relative_underpricing_pct` replaces `move_difference_pct` as primary metric |
| 2026-02-25 | Phase 0: Stale data filter, snapshot collector fix, logging cleanup |
| 2026-02-26 | Phase 1 (PRD 0008): Earnings watchlist, 6-step morning pipeline, step renumbering |
| 2026-02-26 | Phase 2 (0009): Finnhub integration — primary calendar source, BMO/AMC timing |
| 2026-02-26 | Phase 3 (0010): Price moves fallback, earnings_date denormalization, signal archival, historical backfill |
