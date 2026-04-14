# Earnings Intelligence Refactor — Plan

**Created**: 2026-02-25
**Status**: Approved outline, ready for PRD generation
**Supporting docs**: `RESEARCH_AND_FINDINGS.md` (audit), `earnings_intel_notes.md` (strategy vision + design decisions)

---

## Current State

Earnings Intelligence has solid infrastructure — a weekly calendar refresh from YFinance, a daily pipeline that computes expected moves and relative underpricing signals, and a signal classification system (WATCH/BUY/STRONG BUY) validated by the TOST case study. The underlying math works: coverage is 96-100% in the actionable 0-30 day window, and the straddle playbook strategy is well-defined.

What's broken is the last mile. The pipeline runs at 5 PM and prints results to the console, which scrolls away. There's no mechanism to surface actionable earnings opportunities in the morning when Ben can act on them. Stale past-due earnings poison the signal calculations with absurd underpricing values. All `earnings_time` values are "Unknown" (YFinance limitation), so BMO vs AMC timing — which determines whether to enter today or tomorrow — is unavailable. The arbitrage scanner is a no-op (empty correlation data). And there's no dedicated earnings watchlist — earnings signals live in `earnings_upcoming` but never reach the investor-facing layer of the system.

Recent progress: `earnings_snapshots` was revived (Session 6, 2026-02-25) by fixing 4 bugs in the collector. Data will begin accumulating on the next pipeline run. This unblocks future IV buildup curve analysis and begins feeding the downstream price move calculations that have been producing NULLs.

## Target State

**What "done" looks like from Ben's chair at 6:30 AM:**

Ben sits down and sees a concise morning display showing earnings opportunities for the next 10 trading days. Each entry shows: the symbol, its lifecycle status, current price, when earnings are (and whether BMO or AMC), what the expected move is, how much the market is underpricing it, the signal classification, whether IV is currently cheap or expensive, the put/call OI balance, recent flow alert activity, and news sentiment. Separately, his flow watchlist still shows flow-driven opportunities, enriched with earnings context.

The system has two investor-facing watchlist tables:

| Table | Detects | Analogy |
|-------|---------|---------|
| `flow_watchlist_daily` | Someone is betting (unusual options volume) | Reactive — event happened |
| `earnings_watchlist` | Market is mispricing (cheap options near earnings) | Proactive — event approaching |

Both are checked each morning. Together they answer: "What should I be looking at today?"

Behind the scenes, the pipeline runs every morning using the freshest available data, populates the earnings watchlist, captures IV snapshots for buildup analysis, and accumulates `move_vs_expected_pct` data for ongoing threshold calibration. The weekly refresh on Fridays keeps the calendar current.

---

## Orchestration: Morning-First Design

**Key change:** Move the entire EI daily pipeline from the evening (old Step 3.3, ~5:30 PM) to the morning (new Step 1.2, ~7:00 AM). Everything earnings-related runs in one morning sequence, using the freshest data, right when Ben needs it.

### Current State (Split Across Day)

| Step | When | What |
|------|------|------|
| 1.2 | ~6:35 AM | Arbitrage scanner (no-op) |
| 3.3 | ~5:30 PM | Full pipeline: snapshots, post-earnings calc, signals |
| 5.2 | Friday PM | Weekly calendar refresh |

**Problem:** Signals computed at 5 PM are 13+ hours stale by morning. The morning slot runs a no-op. The data is there but not when Ben needs it.

### Target State (All Morning)

| Step | What | Duration | Depends On |
|------|------|----------|-----------|
| **1.1** | Morning Option Pipeline | ~25 min | — |
| **1.2** | **Earnings Intelligence** (full pipeline + watchlist + display) | ~15 min | 1.1 (fresh IV/options data) |
| 1.3 | Metadata Collection | ~5 min | — |
| 1.4 | Query DB Sync | ~5 min | 1.1, 1.2, 1.3 (captures all writes) |
| 1.5 | Morning Views | ~5 min | 1.4 (needs synced query DB) |

**Step 3.3 is eliminated.** Evening phase becomes: OP → Sync → Airline → Sync. Cleaner.

**Step 5.2 stays on Fridays.** The weekly YFinance refresh (5-10 min for 800 symbols) is a bulk calendar operation that doesn't need to be daily. Earnings dates rarely change mid-week. Finnhub (Phase 2) will add a lightweight daily BMO/AMC update (1-2 API calls, seconds) to the morning pipeline when ready.

### Why This Works

- **OP just ran in Step 1.1** — `option_symbol_summary` (IV, IV percentile) and `option_contracts` (straddle pricing) are maximally fresh
- **Historical prices from last evening** — price data for post-earnings calcs was written by yesterday's evening pipeline, already in the database
- **One clean sequence** — compute signals → build watchlist → print display → sync to query DB. No split across two phases, no stale data gap.
- **Time budget is generous** — OP finishes ~7:00 AM, Flow Monitor starts ~9:15 AM. Over 2 hours of runway. EI pipeline takes 10-15 minutes.

### What Step 1.2 Does (Sub-Steps)

1. **Snapshot collection** — Capture today's IV data for events in the T-7 to T+3 window (uses freshly-written `option_symbol_summary`)
2. **Post-earnings calc** — For events at T+3: calculate price moves, IV changes, crush severity, move_vs_expected (uses `historical_prices` from yesterday)
3. **Expected moves + signal recalculation** — Update all `earnings_upcoming` rows with current expected moves, relative underpricing, and signal classifications (uses morning OP data)
4. **Populate `earnings_watchlist`** — Query `earnings_upcoming` for qualifying symbols (WATCH+, 10 trading days, OI >= 4000), pull supplemental data from `option_symbol_summary` and `flow_symbol_summary`, write/update watchlist rows, clean up past-earnings rows
5. **News enrichment** — Fetch news for new watchlist entries and T-1 entries (coordinates with FM via `news_articles` table)
6. **Arbitrage scan** — Lightweight check against `earnings_sector_effects` (currently a no-op, will become useful as correlation data accumulates)
7. **Print morning earnings display** — Read `earnings_watchlist`, format as compact console table

The console display is not a pipeline sub-step — it runs in the orchestrator layer (`main_runners.py`) after `run_daily_pipeline()` returns, using the `watchlist_symbols` data from the return dict.

---

## Phases

### Phase 0: Stop the Bleeding — DONE
**Effort**: Small (1 session, under an hour)
**Dependencies**: None
**Completed**: 2026-02-25

1. **Fix stale data poisoning** — Added `WHERE earnings_date >= today` filter to `ei_moves_upcoming.py` `get_symbols_to_process()`. Stale rows remain in table but are never recalculated with garbage data.

2. **Delete dead Thursday task** — Removed `scheduled_tasks/run_yfinance_earnings_upcoming.bat` and stale log `data/logs/yfinance_earnings_calendar.log`.

3. **Improve weekly refresh logging** — Added summary line to `ei_fetch_upcoming.py`: symbols attempted, earnings found, no data, errors. Fixed double-counting bug where error symbols counted in both errors AND no_data.

### Phase 1: The Earnings Watchlist + Morning Pipeline Move
**Effort**: PRD-level (2-3 sessions, touches 5+ files)
**Dependencies**: Phase 0 (need clean signal data)
**This is the core deliverable of the refactor.**

#### 1A: Unify and Move EI Pipeline to Morning

Relocate the full daily pipeline from evening Step 3.3 to morning (after OP). Remove Step 3.3 from the evening phase. Renumber morning steps: 1.1 OP → 1.2 EI → 1.3 Metadata → 1.4 Sync → 1.5 Morning Views. Update all step key references in `main.py`, `main_runners.py`, and `performance_writer.py`.

**Runner architecture** (follows Option Pipeline model):
- **Strategy layer** (`ei_main.py`): Unified `run_daily_pipeline()` replaces both old `run_daily_pipeline()` and `run_morning_scan()`. Runs 6 sub-steps internally, returns one structured result dict.
- **Orchestrator layer** (`main_runners.py`): New `run_earnings_intelligence()` replaces both `run_earnings_pipeline()` and `run_earnings_morning_scan()`. Creates mission box, calls `run_daily_pipeline()`, renders the earnings watchlist table, builds completion box, handles errors.
- Old function signatures can remain for standalone CLI use (`--daily-pipeline`, `--morning-scan`).

**Pipeline sub-steps (inside `run_daily_pipeline()`):**

| Sub-step | What | Source |
|----------|------|--------|
| 1 | Snapshot collection (IV/price for T-7 to T+3 window) | Existing `ei_snapshot_collector.py` |
| 2 | Post-earnings calc (T+3 events: price moves, IV changes) | Existing `ei_post_earnings_calc.py` |
| 3 | Expected moves + signal recalculation | Existing `ei_moves_upcoming.py` |
| 4 | Watchlist population (build/update `earnings_watchlist`) | New `ei_watchlist.py` |
| 5 | News enrichment (new entries + T-1 entries) | Existing `tools/news_sentiment.py` |
| 6 | Arbitrage scan | Existing `ei_arbitrage_scanner.py` |

**Return dict structure:**
```python
{
    'success': True,
    'duration_seconds': 842.5,
    'errors': 0,
    'sub_tasks': {
        'snapshots': { ... },
        'calculations': { ... },
        'expected_moves': { ... },
        'watchlist': { ... },
        'news_enrichment': { ... },
        'arbitrage': { ... },
    },
    # Top-level summary for completion box
    'snapshots_created': 12,
    'moves_calculated': 3,
    'signals_updated': 287,
    'watchlist_count': 8,
    'watchlist_new': 2,
    'watchlist_breakdown': {'STRONG BUY': 3, 'BUY': 2, 'WATCH': 3},
    'watchlist_symbols': [ ... ],  # Full data for table display
    'arbitrage_opportunities': 0,
    'alerts_triggered': 8,
    'alert_details': [ ... ],
}
```

#### 1B: Build `earnings_watchlist`

New investor-facing table. One row per symbol (PK: `symbol`), updated in place daily, lean and present-focused.

**Entry criteria**: Symbol has WATCH+ signal, earnings within 10 trading days, total OI >= 4000. Symbols stay on the watchlist even if signal downgrades (implicit understanding: if it's there, it was WATCH+ at some point). Rows removed on T+4 morning (after post-earnings data is complete through T+3).

**Pre-earnings columns** (populated when symbol first qualifies, updated daily):
- `symbol` (PK), `status`, `current_price`, `trading_days_to_earnings`, `earnings_date`, `earnings_time`
- `earnings_play_signal`, `iv_percentile_30d`, `relative_underpricing_pct`, `expected_move_pct`, `historical_avg_move_pct`
- `straddle_expected_move_pct` (the tradeable number)
- `oi_balance_text` (put/call OI direction from `option_symbol_summary`)
- `alert_count_5d` (rolling flow alert count from `flow_symbol_summary`)
- `news_sentiment_label`, `news_sentiment_score`, `news_article_count`
- `first_appeared_date`, `created_at`, `last_updated`

**Post-earnings columns** (populated from T+1 onward, enriched at T+3):
- `actual_move_pct` — price change since earnings day. T+1/T+2: calculated from `historical_prices.close_price`. T+3: from `earnings_moves.move_3day_pct`.
- `move_direction` — UP / DOWN, derived from sign of `actual_move_pct`
- `iv_collapse_pct` — from `earnings_moves` (available at T+3 only)
- `iv_crush_severity` — severe/high/normal/mild/minimal, oriented around ~45% as typical (available at T+3 only, scale provisional)

**Writer**: New module `ei_watchlist.py`:
- Queries `earnings_upcoming` for qualifying symbols
- Pulls `iv_percentile_30d`, `current_price`, `oi_balance_text` from `option_symbol_summary` (matched by symbol, most recent `trade_date`)
- Pulls `alert_count_5d` from `flow_symbol_summary` (matched by symbol)
- For post-earnings symbols: calculates interim move from `historical_prices.close_price` (T+1, T+2) or pulls from `earnings_moves` (T+3)
- Updates `status` based on date arithmetic
- Cleans up rows at T+4

**The watchlist is lean and present-focused.** It reflects today's state only. Past signal data is preserved via `earnings_events` archival (see Phase 3), not by accumulating watchlist rows.

#### 1C: Morning Console Display

Render the earnings watchlist as a formatted ASCII table with box-drawing characters inside the Step 1.2 completion output. Sorted by `trading_days_to_earnings`. Pre-earnings and post-earnings symbols shown together with the `status` column distinguishing them. The table renderer consumes the `watchlist_symbols` list from the return dict.

#### 1D: News Enrichment Strategy

News sentiment is fetched via `tools/news_sentiment.py` (Alpha Vantage, 25 calls/day budget).

**When to fetch:**
- When a symbol **first appears** on the watchlist (`first_appeared_date` = today)
- At **T-1** (day before earnings) — sentiment can shift in final days, this is the most decision-critical moment

**Coordination with Flow Monitor:**
- EI runs before FM in the daily schedule. Both check `news_articles` table before fetching: `SELECT COUNT(*) FROM news_articles WHERE symbol=? AND DATE(time_collected) = DATE('now')`. If news already exists for today, skip the API call.
- If EI exhausts the budget, FM will see the same exhaustion and handle gracefully.

**Budget exhaustion handling:**
- Log clearly: `"NEWS API BUDGET EXHAUSTED (25/25 calls used). Skipped news for: AAPL, GOOG"`
- Non-fatal, non-autofix — this is a budget limit, not an error
- Symbols that failed to get news are still on the watchlist, just without sentiment data

#### 1E: `earnings_watchlist` Schema Specification

Definitive column reference for the `earnings_watchlist` table. All column names, types, sources, and population logic are specified here to prevent mismatches between the writer, reader, and display components.

**Table**: `earnings_watchlist`
**Database**: `data/datalake.db`
**Primary Key**: `symbol`
**One row per symbol**, updated in place daily. Rows removed at T+4 morning.

| # | Column | Type | Nullable | Source Table.Column | Population Logic |
|---|--------|------|----------|-------------------|-----------------|
| 1 | `symbol` | TEXT | NO (PK) | `earnings_upcoming.symbol` | Direct copy. One row per symbol. |
| 2 | `status` | TEXT | NO | Calculated | Lifecycle position. Determined by comparing today to `earnings_date`: `UPCOMING` (future), `TODAY` (same day), `T+1`, `T+2`, `T+3`. Row deleted at T+4 morning. |
| 3 | `current_price` | REAL | YES | `option_symbol_summary.close_price` | Previous trading day's close. Pulled fresh each morning, matched by symbol and most recent `trade_date`. Gives a quick sense of option cost without needing real-time data. |
| 4 | `trading_days_to_earnings` | INTEGER | NO | Calculated | **Trading days** (not calendar days) between today and `earnings_date`, via new `count_trading_days_between()` utility. 0 on earnings day. Not negative — `status` tracks post-earnings lifecycle. Named differently from `days_to_earnings` on other tables (which use calendar days) to prevent confusion. |
| 5 | `earnings_date` | TEXT | NO | `earnings_upcoming.earnings_date` | Direct copy. Updated daily (dates can change after Friday refresh). |
| 6 | `earnings_time` | TEXT | YES | `earnings_upcoming.earnings_time` | Direct copy. Currently "Unknown". Will show `bmo`/`amc`/`dmh` after Phase 2 (Finnhub). |
| 7 | `earnings_play_signal` | TEXT | YES | `earnings_upcoming.earnings_play_signal` | Direct copy. Values: `STRONG BUY`, `BUY`, `WATCH`, `NEUTRAL`, `AVOID`, `UNKNOWN`. Updated daily. |
| 8 | `iv_percentile_30d` | REAL | YES | `option_symbol_summary.symbol_iv_percentile_30d` | Pulled fresh each morning. Matched by symbol, most recent `trade_date`. Requires 20+ days history. 0-100 scale. |
| 9 | `relative_underpricing_pct` | REAL | YES | `earnings_upcoming.relative_underpricing_pct` | Direct copy. Formula: `(historical_avg_move - expected_move) / expected_move * 100`. |
| 10 | `expected_move_pct` | REAL | YES | `earnings_upcoming.expected_move_pct` | Direct copy. IV-based expected move calculation. |
| 11 | `historical_avg_move_pct` | REAL | YES | `earnings_upcoming.historical_avg_move_pct` | Direct copy. AVG of `earnings_moves.move_1day_pct` grouped by symbol. |
| 12 | `straddle_expected_move_pct` | REAL | YES | `earnings_upcoming.straddle_expected_move_pct` | Direct copy. Formula: `(ATM Call + ATM Put) * 0.85 / Stock Price * 100`. |
| 13 | `oi_balance_text` | TEXT | YES | `option_symbol_summary.oi_balance_text` | Direct copy. Frames the direction of the current option market. Values: `Clear Call Bias`, `Heavy Call`, `Balanced`, `Leans Put`, `Heavy Put`, `Clear Put Bias`. |
| 14 | `alert_count_5d` | INTEGER | YES | `flow_symbol_summary.alert_count_5d` | Pre-computed rolling 5-day flow alert count. Matched by symbol. Shows whether flow activity is picking up around this name. NULL if no `flow_symbol_summary` row exists. |
| 15 | `news_sentiment_label` | TEXT | YES | `tools/news_sentiment.py` output | Derived from score. Values: `Bullish`, `Somewhat-Bullish`, `Neutral`, `Somewhat-Bearish`, `Bearish`. |
| 16 | `news_sentiment_score` | REAL | YES | `tools/news_sentiment.py` output | Fetched on first appearance and at T-1. Checks `news_articles` for same-day data before calling API. NULL if budget exhausted. |
| 17 | `news_article_count` | INTEGER | YES | `tools/news_sentiment.py` output | Count of relevant articles above relevance threshold. |
| 18 | `actual_move_pct` | REAL | YES | T+1/T+2: `historical_prices`. T+3: `earnings_moves.move_3day_pct` | T+1/T+2: `(most_recent_close - pre_earnings_close) / pre_earnings_close * 100` where `pre_earnings_close` = close on the trading day before `earnings_date`, `most_recent_close` = most recent available close in `historical_prices`. Data lag: at 7 AM, `historical_prices` contains through yesterday's close. T+3: direct copy from `earnings_moves`. NULL while UPCOMING or TODAY. |
| 19 | `move_direction` | TEXT | YES | Derived from `actual_move_pct` | `UP` if > 0, `DOWN` if < 0. NULL before earnings. |
| 20 | `iv_collapse_pct` | REAL | YES | `earnings_moves.iv_collapse_pct` | Available at T+3 only. Formula: `(IV_after - IV_before) / IV_before * 100`. NULL before T+3. |
| 21 | `iv_crush_severity` | TEXT | YES | `earnings_moves.iv_crush_severity` | Available at T+3 only. Oriented around ~45% as typical post-earnings crush. Values: `severe` (>65% drop), `high` (50-65%), `normal` (40-50%), `mild` (25-40%), `minimal` (<25%). Scale is provisional — will be evidence-based after ~100 events accumulate. NULL before T+3. **NOTE:** `ei_post_earnings_calc.py` currently uses the old 4-tier scale (severe/moderate/mild/minimal at 40/25/10%). Must be updated to produce the new 5-tier labels. |
| 22 | `first_appeared_date` | TEXT | NO | Calculated | Set to today's date (Eastern) on INSERT. Never updated after creation. |
| 23 | `created_at` | TEXT | NO | Calculated | ISO datetime, set on INSERT, never updated. |
| 24 | `last_updated` | TEXT | NO | Calculated | ISO datetime, set on every INSERT or UPDATE. |

**Entry criteria** (row is created when ALL are true):
- `earnings_play_signal` is WATCH, BUY, or STRONG BUY
- `trading_days_to_earnings` <= 10
- Total open interest >= 4000 (from `earnings_upcoming` qualification)

**Update behavior**: Existing rows are updated daily with current values from source tables. Signal downgrades (e.g., WATCH → NEUTRAL) update the signal but do NOT delete the row.

**Cleanup**: Rows where `status` would be T+4 or beyond are deleted at the start of each morning pipeline run.

**Indexes**:
- `idx_ew_earnings_date` on `earnings_date` (for cleanup queries)
- `idx_ew_status` on `status` (for display filtering)

#### 1F: Flow Watchlist Enrichment

The existing `earnings_date`/`days_to_earnings`/`earnings_time` columns on `flow_watchlist_daily` are already populated by `fm_watchlist.py`. Add `earnings_play_signal` and `relative_underpricing_pct` to this enrichment so flow alerts near earnings show the signal context.

### Phase 2: BMO/AMC Timing via Finnhub — DONE
**Effort**: Medium (1 session)
**Dependencies**: None (independent of Phase 1)
**Task list**: `tasks/0009-tasks-finnhub-bmo-amc.md`
**Status**: COMPLETE (2026-02-26). Commit 6a2aa7f.

Integrate Finnhub earnings calendar API as the **primary** earnings calendar source, replacing YFinance for dates + adding BMO/AMC timing. YFinance becomes a fallback for any coverage gaps.

**Why Finnhub as primary (not supplemental):**
- 4-6 API calls (date-range scan) vs 800 per-symbol YFinance calls — dramatically faster
- REST API vs web scraping — more reliable
- BMO/AMC timing included for free — the core deliverable
- `epsEstimate` and `revenueEstimate` available in same response — bonus data

**Implementation** (researched in Session 3 of RESEARCH_AND_FINDINGS.md):
- New `core/finnhub_api.py` following `core/tradier_api.py` pattern (RateLimiter, requests.Session, _handle_response)
- API key in `config.json` under `finnhub` section (already stored)
- Date-range scan: `GET /calendar/earnings?from=X&to=Y` — 90 days ahead in ~30-day chunks = 3-4 API calls
- Filter results to KLMN 800 symbols
- Rate limit: 60 calls/min (generous for our usage)
- **Friday only** (Step 5.2) — no daily scan. Earnings dates rarely change mid-week. Daily scan deferred until a real edge case is encountered.
- YFinance fallback: after Finnhub fetch, check for KLMN symbols with no Finnhub result. Call YFinance for those only. Run both in parallel for 2-3 weeks to validate coverage, then drop YFinance if Finnhub covers everything.
- Normalize Finnhub `hour` field: `""` → `"Unknown"`, pass through `bmo`/`amc`/`dmh`

**Schema changes:**
- `earnings_upcoming`: ADD `eps_estimate REAL`, `revenue_estimate REAL` (new columns for Finnhub bonus data)
- `earnings_time` column already exists — just needs data populated (was always "Unknown")
- No new tables

**Data cascade:**
- `earnings_time` populated on `earnings_upcoming` → cascades to `earnings_watchlist` (Phase 1 daily pipeline) and `flow_watchlist_daily` (FM enrichment)
- `eps_estimate`/`revenue_estimate` populated on `earnings_upcoming` → cascade to `earnings_events` via Friday archive (Phase 3 adds the columns)

**Post-earnings actual results** (follow-up, not in this phase): Finnhub provides `epsActual`/`revenueActual` after earnings report. Could populate the currently-NULL `actual_eps`/`eps_surprise_pct` on `earnings_events`. This is a distinct data flow — defer until Phase 3 is complete and the archive pipeline is enriched.

### Phase 3: Close the Data Loops — DONE (Task 5 deferred)
**Effort**: Medium (1-2 sessions)
**Dependencies**: Phase 0 (complete). Benefits from snapshot data accumulating (started 2026-02-25, Session 6).
**Task list**: `tasks/0010-tasks-close-data-loops.md`
**Status**: Tasks 1-4 COMPLETE (2026-02-26). Commits 4813c75, 849fad9, 1039736, 9e4fe29. Task 5 (snapshot wiring verification) deferred ~2 weeks.

The EI system has structural gaps leaving critical analytical columns permanently NULL across 9,324 `earnings_moves` rows. This phase adds fallback calculations, denormalizes key columns, preserves signal data during archival, and backfills historical gaps.

**Root cause analysis:** All 9,324 `earnings_moves` rows have NULL price moves (`move_1day_pct` through `move_vs_expected_pct`) because `_calculate_price_moves()` queries `earnings_snapshots`, which was empty until Session 6 (2026-02-25). The IV fallback (`_get_iv_from_option_summary()`) was implemented in Feb 2026 — but no equivalent fallback exists for price moves. This phase adds the symmetric fallback.

**Architecture: snapshots vs historical_prices:**
- `earnings_snapshots` = **primary** (long-term). Captures IV data at specific days relative to earnings — richer than `historical_prices`. The collector was fixed in Session 6 and is now running as pipeline sub-step 1. Data will accumulate over ~2 weeks.
- `historical_prices` = **fallback**. Always available for price data (daily OHLC). Used by the new `_get_price_moves_from_historical()` for the 9,324 historical rows where snapshots never existed, and during the ~2 week ramp-up period.
- **NOT deprecating `earnings_snapshots`** — it's correctly designed and will be the primary data source once populated.

**Four deliverables:**

1. **Price moves fallback** — Add `_get_price_moves_from_historical()` to `ei_post_earnings_calc.py`. Query `historical_prices.close_price` at T-1, T0, T+1, T+2, T+3, T+5. Calculate all price move columns. Called when `_calculate_price_moves()` returns empty (no snapshots). This also unblocks `move_vs_expected_pct` — the formula already exists (line 182-186), it just needs non-NULL `move_1day_pct` as input. **Critical for Phase 1:** The `earnings_watchlist` T+3 `actual_move_pct` pulls from `earnings_moves.move_3day_pct`, which is NULL until this fix runs.

2. **Denormalize `earnings_date` onto `earnings_moves`** — ALTER TABLE ADD COLUMN + populate at INSERT time. Makes the 9,324 rows self-contained without JOINing to `earnings_events` (where 99.7% of parent rows are archived to sector DBs). Index for direct date-range queries.

3. **Archive signal data to `earnings_events`** — Add 7 columns: `earnings_play_signal`, `relative_underpricing_pct`, `expected_move_pct`, `straddle_expected_move_pct`, `historical_avg_move_pct`, `eps_estimate`, `revenue_estimate`. Update archive query in `ei_main.py:132-142` to include these in the SELECT. Preserves pre-earnings signal context for backtesting — "was the STRONG BUY signal accurate?" Currently lost during archival.

4. **Backfill migration** — Three-pass script: (a) denormalize `earnings_date` from production `earnings_events` (177 rows) + cross-archive queries to sector DBs (~9,147 rows), (b) calculate price moves for all 9,324 rows using `_get_price_moves_from_historical()`, (c) validate results. **Test with airlines.db first**, then all sectors.

**Snapshot wiring** (verify, likely no changes): The collector was fixed in Session 6 and now writes `(event_id, symbol, earnings_date)` to `earnings_snapshots`. The existing lookup in `_calculate_price_moves()` uses `(event_id, symbol, is_primary_symbol)`. After ~2 weeks of accumulation, the primary path should fire automatically. Verify and log which path was used.

---

## What We're NOT Doing

- **Scenario calculator** — The proposal (`earnings-scenario-calculator-proposal.md`) is solid but depends on clean `move_vs_expected_pct` data and IV crush history. Phase 3 builds that foundation. Calculator is a future phase.

- **Arbitrage scanner overhaul** — The scanner is a no-op because `earnings_sector_effects` has 0 correlation history. With snapshots now capturing peer data, this will populate naturally over time. No code changes needed — just patience and data accumulation.

- **Morning View earnings screen** — The TUI integration is a rich experience but not the priority. Console output from Phase 1 delivers the same information with far less effort. Morning View screen is a future enhancement.

- **Agent evaluation layer** — The infrastructure to feed agents is what we're building. The agents themselves are a separate project that was paused to build this foundation.

- **Signal threshold recalibration** — Current thresholds (WATCH=15%, BUY=30%, STRONG BUY=50%) are provisional. Recalibration requires ~100 events with `move_vs_expected_pct` data. Phase 3 unblocks this data. Recalibration happens organically after ~2 months of accumulation.

- **EPS/revenue enrichment of `earnings_events`** — ~~Deferred~~ Now included: `eps_estimate` and `revenue_estimate` stored on `earnings_upcoming` (Phase 2) and archived to `earnings_events` (Phase 3). Post-earnings actuals (`eps_actual`, `revenue_actual`) from Finnhub are a follow-up feature.

- **Redesigning signal calculations** — The relative underpricing metric is sound. The straddle method is correctly implemented. Coverage is 96%+ in the actionable window. No changes needed.

- **More frequent calendar refresh** — Weekly refresh is sufficient. Earnings dates rarely change mid-week. Daily Finnhub scan was considered and deferred — will address if a real edge case is encountered.

---

## Key Design Decisions (Settled)

| # | Decision | Answer | Source |
|---|----------|--------|--------|
| Q4 | Stale data fix | Filter (don't delete) — WHERE clause in signal calc | earnings_intel_notes.md |
| Q2 | Watchlist architecture | New `earnings_watchlist` table, separate from flow | earnings_intel_notes.md |
| Q5 | Lookahead window | 10 trading days | earnings_intel_notes.md (revised) |
| Q3 | IV assessment | Use existing `symbol_iv_percentile_30d` from `option_symbol_summary` | earnings_intel_notes.md |
| Q8 | Earnings snapshots | Revived (4 bugs fixed, rewired to `earnings_upcoming`) | Session 6, RESEARCH_AND_FINDINGS.md |
| Q2 | BMO/AMC data source | Finnhub API (free tier, REST) — **primary source**, YFinance = fallback | Session 3 + Discussion 2026-02-26 |
| — | Finnhub collection frequency | Weekly only (Friday Step 5.2). Daily scan deferred — rare edge case. | Discussion 2026-02-26 |
| — | Finnhub hour normalization | `""` → `"Unknown"`, pass through `bmo`/`amc`/`dmh` | Discussion 2026-02-26 |
| — | Finnhub bonus fields | Store `eps_estimate`, `revenue_estimate` on `earnings_upcoming`. Cascade to `earnings_events` via archive. | Discussion 2026-02-26 |
| — | Snapshots vs historical_prices | Snapshots = primary (long-term), historical_prices = fallback. NOT deprecating snapshots. | Discussion 2026-02-26 |
| — | Price moves backfill | Full backfill of 9,324 rows including cross-archive queries. Airlines.db = test target. | Discussion 2026-02-26 |
| — | earnings_date denormalization | Add to `earnings_moves`. Backfill from production + sector archives. | Discussion 2026-02-26 |
| — | Signal archival columns | 5 signal + 2 estimate = 7 new columns on `earnings_events` | Discussion 2026-02-26 |
| — | Agent scope | Not in scope — build infrastructure to feed them, not the agents | earnings_intel_notes.md |
| E | Table name | `earnings_watchlist` (not `_daily` — PK is symbol, one row per symbol) | Q&A 2026-02-25 |
| F | Signal downgrades | Keep row, update signal. Implicit: if on watchlist, was WATCH+ at some point. | Q&A 2026-02-25 |
| G | Post-earnings lifecycle | Rows kept through T+3 with status tracking + post-earnings data columns. Removed at T+4 morning. | Q&A 2026-02-25 |
| G | Post-earnings data | T+1/T+2: interim move from `historical_prices`. T+3: full data from `earnings_moves`. | Q&A 2026-02-25 |
| H | Runner architecture | Follows OP model. `run_daily_pipeline()` in ei_main.py (6 sub-steps). `run_earnings_intelligence()` in main_runners.py. | Q&A 2026-02-25 |
| H | Pipeline timing | All EI runs in morning (after OP). Evening Step 3.3 eliminated. | Discussion 2026-02-25 |
| I | Return dict | Unified dict with sub_tasks, top-level summary, and watchlist_symbols list for table display | Q&A 2026-02-25 |
| J | News enrichment | Fetch at first appearance + T-1. Coordinate via `news_articles` table. Budget exhaustion is loud but non-autofix. | Q&A 2026-02-25 |
| — | Watchlist is lean | Present-state only, no historical accumulation. Past signals archived to `earnings_events`. | Discussion 2026-02-25 |
| — | Weekly refresh frequency | Weekly (Fridays) is sufficient for calendar. Finnhub daily scan for BMO/AMC only. | Discussion 2026-02-25 |
| — | Signal archival | Add signal columns to `earnings_events`, populated during Friday archive | Discussion 2026-02-25 |
| C/D | Step renumbering | Full renumber of all step keys, log messages, and performance writer references | Q&A 2026-02-25 |

---

## File Impact Estimate

| Phase | Files Modified | Files Created | Tables Modified | Tables Created |
|-------|---------------|---------------|-----------------|----------------|
| 0 | `ei_moves_upcoming.py`, `ei_fetch_upcoming.py` | — | — | — |
| 1 | `ei_main.py`, `main.py`, `main_runners.py`, `main_ui.py`, `fm_watchlist.py`, `performance_writer.py` | `ei_watchlist.py` | `flow_watchlist_daily` (add signal columns) | `earnings_watchlist` |
| 2 | `ei_fetch_upcoming.py` | `core/finnhub_api.py` | `earnings_upcoming` (add eps_estimate, revenue_estimate) | — |
| 3 | `ei_post_earnings_calc.py`, `ei_main.py` (archive step) | `ei_backfill_price_moves.py` | `earnings_moves` (add earnings_date), `earnings_events` (add 7 columns) | — |
