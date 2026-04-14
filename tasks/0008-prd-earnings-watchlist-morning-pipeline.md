# PRD: Earnings Watchlist & Morning Pipeline

**PRD Number:** 0008
**Created:** 2026-02-26
**Status:** Draft
**Origin:** Earnings Intelligence refactor — `docs/earnings_strategy_refactor/REFACTOR_PLAN.md` (Phase 1), `docs/earnings_strategy_refactor/earnings_intel_notes.md` (strategy vision), `docs/earnings_strategy_refactor/RESEARCH_AND_FINDINGS.md` (6-session audit)

---

## 1. Introduction/Overview

The Earnings Intelligence system has solid analytical infrastructure — signal classification (WATCH/BUY/STRONG BUY), relative underpricing metrics, expected move calculations — but the results never reach the investor when they matter. The pipeline runs at 5 PM, prints to a console that scrolls away, and by 6:30 AM the next morning, the data is 13+ hours stale. There is no dedicated earnings watchlist — signals live in `earnings_upcoming` and never reach an investor-facing layer.

This PRD covers Phase 1 of the EI refactor: moving the entire pipeline to morning (Step 1.2, after Option Pipeline), building an `earnings_watchlist` table that surfaces actionable earnings opportunities as first-class alerts, rendering them as a morning console display, and enriching the existing flow watchlist with earnings signal context.

### Prior Art

- `docs/earnings_strategy_refactor/REFACTOR_PLAN.md` — master plan with full schema spec (section 1E), architecture decisions, orchestration layout
- `docs/earnings_strategy_refactor/RESEARCH_AND_FINDINGS.md` — 6 sessions of code audit, data analysis, and gap identification
- `docs/earnings_strategy_refactor/earnings_intel_notes.md` — Ben's strategy vision, workflow goals, and Q&A answers
- Phase 0 completed 2026-02-25: stale data filter, dead batch file cleanup, logging improvements

---

## 2. Goals

1. **Surface earnings opportunities at decision time** — earnings watchlist displayed every morning at ~7:00 AM, using data computed minutes earlier from the freshest OP output
2. **Create `earnings_watchlist` table** — a lean, investor-facing table with 24 columns that tracks symbols from 14 calendar days before earnings through T+3 after, enriched with cross-strategy context (IV percentile, OI balance, flow alert count, news sentiment)
3. **Unify the EI pipeline into a single morning step** — replace the split architecture (morning arbitrage no-op + evening pipeline) with one consolidated Step 1.2 that runs 6 sub-steps and returns a structured result dict
4. **Enrich the flow watchlist with earnings signals** — add `earnings_play_signal` and `relative_underpricing_pct` to `flow_watchlist_daily` so flow-driven alerts near earnings show signal context
5. **Update IV crush severity scale** — replace the current 4-tier scale (40/25/10% thresholds) with a 5-tier scale centered around ~45% as typical, producing more useful labels for post-earnings analysis
6. **Renumber all orchestrator step keys** — insert EI as Step 1.2, bump downstream steps, and update all references in `main.py`, `main_runners.py`, and `performance_writer.py`

---

## 3. User Stories

- **As a swing trader (Ben)**, I want to sit down at 6:30 AM and see a concise table of earnings opportunities for the next 14 days, showing signal strength, IV cheapness, expected moves, and news sentiment, so I can identify entry candidates before market open.
- **As a swing trader**, I want post-earnings symbols (T+1 through T+3) to remain on the watchlist showing actual move data, so I can evaluate outcomes and learn from each event.
- **As a swing trader**, when I see a flow alert on `flow_watchlist_daily`, I want to know whether that symbol has an earnings signal (and what strength), so I can judge whether the flow activity is earnings-related.
- **As a swing trader**, I want earnings opportunities surfaced proactively (market is mispricing) separately from flow alerts (someone is betting), because earnings signals can fire days before flow activity appears.
- **As the orchestrator**, I want EI to run in the morning using fresh OP data, not 13-hour-old evening data, so signals are maximally accurate when displayed.
- **As the performance tracking system**, I want the new Step 1.2 to produce a structured return dict with sub-task timings, so the performance writer can record EI pipeline metrics alongside all other steps.
- **As the autofix system**, I want EI pipeline failures queued via `queue_error()` with context, so batch mode can diagnose failures.

---

## 4. Functional Requirements

### 4.1 Pipeline Relocation and Step Renumbering

1. Move the EI daily pipeline from evening Phase 3 (old Step 3.3) to morning Phase 1 (new Step 1.2), running immediately after the Morning Option Pipeline (Step 1.1).
2. Remove the standalone morning arbitrage scanner call (old Step 1.2). Arbitrage scanning becomes sub-step 6 inside the unified pipeline.
3. Renumber all morning steps after OP:

   | Old Key | New Key | What |
   |---------|---------|------|
   | `1.1 Morning Option Pipeline` | `1.1 Morning Option Pipeline` | Unchanged |
   | `1.2 Arbitrage Scanner` | *(eliminated — absorbed into 1.2)* | |
   | *(new)* | `1.2 Earnings Intelligence` | Full EI pipeline + watchlist + display |
   | `1.3 Metadata Collection` | `1.3 Metadata Collection` | Unchanged |
   | `1.4 Query Sync (Morning)` | `1.4 Query Sync (Morning)` | Unchanged |
   | `1.5 Morning Views` | `1.5 Morning Views` | Unchanged |

4. Renumber evening steps to remove the old earnings slot:

   | Old Key | New Key | What |
   |---------|---------|------|
   | `3.1 Evening Option Pipeline` | `3.1 Evening Option Pipeline` | Unchanged |
   | `3.2 Query Sync (Evening)` | `3.2 Query Sync (Evening)` | Unchanged |
   | `3.3 Earnings Pipeline` | *(eliminated)* | |
   | `3.4 Airline Play` | `3.3 Airline Play` | Renumbered |
   | `3.5 Query Sync (Final)` | `3.4 Query Sync (Final)` | Renumbered |

5. Update all step key references in:
   - `main.py`: `step_durations` dict keys, `results` dict keys, `phase_header` calls, `STEP_SEQUENCE` list (lines ~154-174), and all `coffee_break(after_step=...)` calls — remove entries for `'Earnings Arbitrage Scanner'` and `'Earnings Pipeline'`, add entry for the new EI step
   - `main.py`: `--earnings-intel` CLI flag (line ~718) — update to call `run_earnings_intelligence()` instead of the old `run_earnings_pipeline()`
   - `main_runners.py`: any step key references in log messages or result handling
   - `tools/performance_writer.py`: `ei_mapping` dict (line ~635), any other step key lookups

6. The Friday weekly refresh (Step 5.2) is unchanged.

### 4.2 Runner Architecture

7. **Strategy layer** — In `strategies/earnings_intel/ei_main.py`, create a unified `run_daily_pipeline()` that replaces both the old `run_daily_pipeline()` and `run_morning_scan()`. This function runs 6 sub-steps internally and returns one structured result dict. Old function signatures may remain for standalone CLI use (`--daily-pipeline`, `--morning-scan`) but route internally to the same pipeline.

8. **Orchestrator layer** — In `main_runners.py`, create `run_earnings_intelligence()` that replaces both `run_earnings_pipeline()` and `run_earnings_morning_scan()`. This function:
   - Creates a mission box (status box with description of what EI is about to do)
   - Calls `run_daily_pipeline()` from `ei_main.py`
   - If successful, renders the earnings watchlist as a console table (section 4.5)
   - Builds completion box from the return dict
   - On failure, queues error via `queue_error()` and shows failure box
   - Returns the result dict

9. The 6 pipeline sub-steps inside `run_daily_pipeline()`:

   | Sub-step | What | Module |
   |----------|------|--------|
   | 1 | Snapshot collection (IV/price for T-7 to T+3 window) | Existing `ei_snapshot_collector.py` |
   | 2 | Post-earnings calc (T+3 events: price moves, IV changes) | Existing `ei_post_earnings_calc.py` |
   | 3 | Expected moves + signal recalculation | Existing `ei_moves_upcoming.py` |
   | 4 | Watchlist population (build/update `earnings_watchlist`) | New `ei_watchlist.py` |
   | 5 | News enrichment (new entries + T-1 entries) | Existing `tools/news_sentiment.py` |
   | 6 | Arbitrage scan | Existing `ei_arbitrage_scanner.py` |

10. **Return dict structure** from `run_daily_pipeline()`:

    ```python
    {
        'success': True,
        'duration_seconds': 842.5,
        'errors': 0,
        'sub_tasks': {
            'snapshots': { 'duration_seconds': ..., 'success': ..., ... },
            'calculations': { 'duration_seconds': ..., 'success': ..., ... },
            'expected_moves': { 'duration_seconds': ..., 'success': ..., ... },
            'watchlist': { 'duration_seconds': ..., 'success': ..., ... },
            'news_enrichment': { 'duration_seconds': ..., 'success': ..., ... },
            'arbitrage': { 'duration_seconds': ..., 'success': ..., ... },
        },
        # Top-level summary for completion box
        'snapshots_created': 12,
        'moves_calculated': 3,
        'signals_updated': 287,
        'watchlist_count': 8,
        'watchlist_new': 2,
        'watchlist_breakdown': {'STRONG BUY': 3, 'BUY': 2, 'WATCH': 3},
        'watchlist_symbols': [ ... ],  # Full row data for table display
        'arbitrage_opportunities': 0,
        'alerts_triggered': 8,
        'alert_details': [ ... ],
    }
    ```

### 4.3 `earnings_watchlist` Table

11. Create the `earnings_watchlist` table in `data/datalake.db` with the following schema (24 columns, ordered for display priority):

    | # | Column | Type | Nullable | Source | Population Logic |
    |---|--------|------|----------|--------|-----------------|
    | 1 | `symbol` | TEXT | NO (PK) | `earnings_upcoming.symbol` | Direct copy. One row per symbol. |
    | 2 | `status` | TEXT | NO | Calculated | `UPCOMING`, `TODAY`, `T+1`, `T+2`, `T+3`. Determined by comparing today to `earnings_date`. Row deleted at T+4 morning. |
    | 3 | `current_price` | REAL | YES | `option_symbol_summary.close_price` | Previous trading day's close. Matched by symbol, most recent `trade_date`. |
    | 4 | `days_to_earnings` | INTEGER | NO | Calculated | **Calendar days** to `earnings_date`. 0 on earnings day. Not negative — `status` tracks post-earnings. Consistent with `flow_watchlist_daily.days_to_earnings` and `earnings_upcoming.earnings_days_ahead` — all use calendar days. |
    | 5 | `earnings_date` | TEXT | NO | `earnings_upcoming.earnings_date` | Direct copy. Updated daily (dates can shift after Friday refresh). |
    | 6 | `earnings_time` | TEXT | YES | `earnings_upcoming.earnings_time` | Direct copy. Currently "Unknown". Will show `bmo`/`amc`/`dmh` after Phase 2 (Finnhub). |
    | 7 | `earnings_play_signal` | TEXT | YES | `earnings_upcoming.earnings_play_signal` | Direct copy. Values: `STRONG BUY`, `BUY`, `WATCH`, `NEUTRAL`, `AVOID`, `UNKNOWN`. Updated daily. |
    | 8 | `iv_percentile_30d` | REAL | YES | `option_symbol_summary.symbol_iv_percentile_30d` | Pulled fresh each morning. Requires 20+ days history. 0-100 scale. |
    | 9 | `relative_underpricing_pct` | REAL | YES | `earnings_upcoming.relative_underpricing_pct` | Direct copy. Formula: `(hist_avg - expected) / expected * 100`. |
    | 10 | `expected_move_pct` | REAL | YES | `earnings_upcoming.expected_move_pct` | Direct copy. IV-based expected move. |
    | 11 | `historical_avg_move_pct` | REAL | YES | `earnings_upcoming.historical_avg_move_pct` | Direct copy. AVG of `earnings_moves.move_1day_pct` by symbol. |
    | 12 | `straddle_expected_move_pct` | REAL | YES | `earnings_upcoming.straddle_expected_move_pct` | Direct copy. Formula: `(ATM Call + ATM Put) * 0.85 / Price * 100`. |
    | 13 | `oi_balance_text` | TEXT | YES | `option_symbol_summary.oi_balance_text` | Direct copy. Values: `Clear Call Bias`, `Heavy Call`, `Balanced`, `Leans Put`, `Heavy Put`, `Clear Put Bias`. |
    | 14 | `alert_count_5d` | INTEGER | YES | `flow_symbol_summary.alert_count_5d` | Pre-computed rolling 5-day flow alert count. NULL if no row exists. |
    | 15 | `news_sentiment_label` | TEXT | YES | `tools/news_sentiment.py` | Values: `Bullish`, `Somewhat-Bullish`, `Neutral`, `Somewhat-Bearish`, `Bearish`. |
    | 16 | `news_sentiment_score` | REAL | YES | `tools/news_sentiment.py` | Fetched on first appearance and at T-1. NULL if budget exhausted. |
    | 17 | `news_article_count` | INTEGER | YES | `tools/news_sentiment.py` | Relevant articles above relevance threshold. |
    | 18 | `actual_move_pct` | REAL | YES | `historical_prices.close_price` / `earnings_moves.move_3day_pct` | T+1/T+2: `(most_recent_close - pre_earnings_close) / pre_earnings_close * 100` where `pre_earnings_close` = `historical_prices.close_price` for the trading day before `earnings_date`, and `most_recent_close` = `historical_prices.close_price` for the most recent `trade_date` available. **Data lag note:** at 7 AM, `historical_prices` contains through yesterday's close. So at T+1 morning, the most recent close IS the earnings-day close, meaning the move reflects only the earnings-day reaction (close-to-close from day before → day of). At T+2 morning, the move reflects through T+1's close. T+3: direct copy from `earnings_moves.move_3day_pct`. NULL while UPCOMING or TODAY. |
    | 19 | `move_direction` | TEXT | YES | Derived | `UP` if `actual_move_pct` > 0, `DOWN` if < 0. NULL before earnings. |
    | 20 | `iv_collapse_pct` | REAL | YES | `earnings_moves.iv_collapse_pct` | T+3 only. Formula: `(IV_after - IV_before) / IV_before * 100`. |
    | 21 | `iv_crush_severity` | TEXT | YES | `earnings_moves.iv_crush_severity` | T+3 only. New 5-tier scale (see req 21). |
    | 22 | `first_appeared_date` | TEXT | NO | Calculated | Today's date (Eastern) on INSERT. Never updated. |
    | 23 | `created_at` | TEXT | NO | Calculated | ISO datetime on INSERT. Never updated. |
    | 24 | `last_updated` | TEXT | NO | Calculated | ISO datetime on every INSERT or UPDATE. |

12. **Entry criteria** — a row is created when ALL of these are true:
    - `earnings_play_signal` is WATCH, BUY, or STRONG BUY
    - `days_to_earnings` <= 14
    - Total open interest >= 4000 (from `earnings_upcoming` qualification)

13. **Update behavior** — existing rows are updated daily with current values from source tables. Signal downgrades (e.g., WATCH → NEUTRAL) update the signal column but do NOT delete the row.

14. **Cleanup** — rows where `status` would be T+4 or beyond are deleted at the start of each morning pipeline run.

15. **Indexes**:
    - `idx_ew_earnings_date` on `earnings_date` (for cleanup queries)
    - `idx_ew_status` on `status` (for display filtering)

### 4.4 `ei_watchlist.py` Module

16. Create `strategies/earnings_intel/ei_watchlist.py` as the writer module for the `earnings_watchlist` table. This module:
    - Creates the table if it doesn't exist (DDL in the module, like other EI modules)
    - Queries `earnings_upcoming` for symbols meeting entry criteria
    - Pulls `iv_percentile_30d`, `current_price` (`close_price`), `oi_balance_text` from `option_symbol_summary` — matched by symbol, most recent `trade_date`
    - Pulls `alert_count_5d` from `flow_symbol_summary` — matched by symbol
    - For post-earnings symbols (T+1, T+2): calculates interim `actual_move_pct` from `historical_prices.close_price` — reference price is the close on the trading day BEFORE `earnings_date` (pre-earnings close), compared to the most recent available close. At 7 AM, `historical_prices` contains through yesterday's close.
    - For T+3 symbols: pulls `actual_move_pct` from `earnings_moves.move_3day_pct`, `iv_collapse_pct`, `iv_crush_severity`
    - Computes `status` based on calendar day arithmetic (today vs `earnings_date`)
    - Computes `days_to_earnings` as calendar days between today and `earnings_date`
    - Uses `INSERT ... ON CONFLICT(symbol) DO UPDATE SET ...` for upserts. The UPDATE SET clause must list all columns EXCEPT `symbol`, `first_appeared_date`, and `created_at` — these three are preserved from the original INSERT. (Note: `INSERT OR REPLACE` would delete and re-insert, destroying those values.)
    - Deletes T+4+ rows at the start of each run
    - Returns a dict with: `watchlist_count`, `watchlist_new`, `watchlist_breakdown` (by signal), `watchlist_symbols` (full row data list for display), `removed_count`
    - All numeric values must pass through `clean_database_row()` from `tools/decimal_formatter.py` before INSERT

### 4.5 Morning Console Display

17. After `run_daily_pipeline()` returns successfully, `run_earnings_intelligence()` in `main_runners.py` renders the earnings watchlist as a formatted ASCII table with box-drawing characters.
    - Sorted by `days_to_earnings` (ascending — nearest earnings first)
    - Pre-earnings (`UPCOMING`, `TODAY`) and post-earnings (`T+1`, `T+2`, `T+3`) symbols shown together, distinguished by the `status` column
    - The table consumes the `watchlist_symbols` list from the return dict
    - Column selection for display should prioritize: `symbol`, `status`, `current_price`, `days_to_earnings`, `earnings_time`, `earnings_play_signal`, `iv_percentile_30d`, `relative_underpricing_pct`, `expected_move_pct`, `oi_balance_text`, `news_sentiment_label`. Post-earnings columns (`actual_move_pct`, `move_direction`, `iv_crush_severity`) shown for T+1/T+2/T+3 rows.
    - Use `tools/log_utils.py` output functions so the table reaches both console and `.log` file
    - If watchlist is empty, display a one-line note ("No earnings watchlist entries") instead of an empty table
    - The table renderer is part of the orchestrator layer, not the strategy layer

18. **Completion box** contents (after the table):
    - Snapshots collected: N
    - Moves calculated: N
    - Signals updated: N
    - Watchlist: N symbols (X new) — breakdown by signal
    - Arbitrage opportunities: N
    - Earnings alerts: N (with signal breakdown and top symbols, same format as current `run_earnings_pipeline()`)

### 4.6 News Enrichment

19. News sentiment is fetched via `tools/news_sentiment.py` (Alpha Vantage, 25 calls/day) as pipeline sub-step 5.
    - Fetch for symbols where `first_appeared_date` = today (new entries)
    - Fetch for symbols at T-1 (day before earnings — decision-critical refresh)
    - Before each API call, check `news_symbol_sentiment` table: `SELECT COUNT(*) FROM news_symbol_sentiment WHERE symbol=? AND DATE(fetched_at) = DATE('now')`. Skip if news already exists for today.
    - This coordination prevents double-fetching when FM runs later and encounters the same symbol.
    - On budget exhaustion: log clearly (`"NEWS API BUDGET EXHAUSTED (25/25 calls used). Skipped news for: AAPL, GOOG"`), continue pipeline — this is a budget limit, not an error. Do NOT queue to autofix.
    - Symbols that don't get news are still on the watchlist, just with NULL sentiment columns.

### 4.7 IV Crush Severity Scale Update

20. Update `strategies/earnings_intel/ei_post_earnings_calc.py` to use the new 5-tier IV crush severity scale, centered around ~45% as typical post-earnings crush:

    | Label | Collapse Range | Meaning |
    |-------|---------------|---------|
    | `severe` | > 65% drop | Well above typical |
    | `high` | 50-65% drop | Above typical |
    | `normal` | 40-50% drop | Around the expected ~45% |
    | `mild` | 25-40% drop | Below typical |
    | `minimal` | < 25% drop | Unusually low crush |

    This replaces the current 4-tier scale (`severe` >= 40%, `moderate` >= 25%, `mild` >= 10%, `minimal` < 10%). The old scale labeled nearly everything as "severe" since 45% is typical.

    The scale is provisional — thresholds will be evidence-based after ~100 events accumulate with `iv_collapse_pct` data (~early March 2026).

21. The new labels apply to both new `earnings_moves` rows going forward AND are used when displaying `iv_crush_severity` on the `earnings_watchlist`. Existing `earnings_moves` rows with old labels are NOT backfilled — the old labels remain in historical data.

### 4.8 Flow Watchlist Enrichment

22. In `strategies/flow_monitor/fm_watchlist.py`, add two columns to the earnings enrichment that already populates `earnings_date`, `days_to_earnings`, and `earnings_time`:
    - `earnings_play_signal` — from `earnings_upcoming.earnings_play_signal`
    - `relative_underpricing_pct` — from `earnings_upcoming.relative_underpricing_pct`

23. These columns must be added to the `flow_watchlist_daily` table. Use `ALTER TABLE ADD COLUMN` with a try/except for "duplicate column name" (standard SQLite pattern for idempotent schema evolution). Run the ALTER at module initialization or table-creation time, same as other EI modules. The columns are REAL and TEXT respectively, both nullable, defaulting to NULL for existing rows.

### 4.9 Performance Writer Update

24. Update `tools/performance_writer.py` `ei_mapping` dict to reflect the new step keys:

    | Old Mapping | New Mapping |
    |-------------|-------------|
    | `'1.2 Arbitrage Scanner': 'morning_scan'` | *(remove)* |
    | `'3.3 Earnings Pipeline': 'daily_pipeline'` | `'1.2 Earnings Intelligence': 'daily_pipeline'` |
    | `'5.2 Earnings Refresh': 'weekly_refresh'` | `'5.2 Earnings Refresh': 'weekly_refresh'` (unchanged) |

25. Add watchlist-related columns to `ei_pipeline_performance` table for the `daily_pipeline` run type:
    - `watchlist_count` (INTEGER) — total symbols on watchlist after this run
    - `watchlist_new` (INTEGER) — new symbols added this run
    - `news_enriched` (INTEGER) — symbols that received news sentiment this run
    - `watchlist_seconds` (REAL) — duration of the watchlist sub-step
    - `news_seconds` (REAL) — duration of the news enrichment sub-step

    These map to `sub_tasks.watchlist.duration_seconds`, `sub_tasks.news_enrichment.duration_seconds`, and the top-level `watchlist_count`/`watchlist_new` fields in the return dict.

26. Update the evening step key mappings wherever `3.4 Airline Play` and `3.5 Query Sync (Final)` are referenced to use the new `3.3` and `3.4` keys.

### 4.10 Error Handling

27. The new `ei_watchlist.py` module must integrate with the autofix system:
    - Failures that prevent watchlist population (e.g., `earnings_upcoming` query fails, `option_symbol_summary` unavailable): queue via `queue_error()` with severity `ERROR`, include context dict with `failed_step`, `error_message`, and `performance_db` path.
    - Non-fatal issues (e.g., missing IV percentile for one symbol, no `flow_symbol_summary` row): log as warning, continue processing other symbols. Do NOT queue to autofix.
    - Individual symbol failures should not abort the entire watchlist population.

28. **Sub-step failure cascading**: Each of the 6 sub-steps runs inside its own try/except. If a sub-step fails, its `sub_tasks` entry records `success: False` and the error, but subsequent sub-steps still attempt to run. The dependency chain is:
    - Sub-steps 1-3 (snapshots, post-earnings calc, signals) are independent of each other and independent of sub-steps 4-6. Each can fail without affecting the others.
    - Sub-step 4 (watchlist) does NOT depend on sub-steps 1-3 completing — it reads from `earnings_upcoming` (written by sub-step 3) but can use existing data if sub-step 3 fails.
    - Sub-step 5 (news) depends on sub-step 4 having created/updated watchlist rows. If sub-step 4 fails entirely (no rows), sub-step 5 logs "no watchlist entries to enrich" and returns cleanly.
    - Sub-step 6 (arbitrage) is fully independent.
    - The top-level `success` field is `True` if the pipeline completed (even with individual sub-step failures). It is `False` only if the pipeline itself crashes or cannot start.

29. The orchestrator-level `run_earnings_intelligence()` wraps the entire pipeline call in try/except. On unhandled exception, it creates a failure result dict and queues via `queue_error()`, matching the pattern in the current `run_earnings_pipeline()`.

### 4.11 Performance Writer Schema Migration

31. The `ei_pipeline_performance` table in `data/performance.db` already exists with 25 columns. Adding the 5 new columns (Req 25) requires:
    - Update the `CREATE TABLE IF NOT EXISTS` DDL in `performance_writer.py` to include the new columns (for fresh installs or new databases)
    - Add `ALTER TABLE ADD COLUMN` statements with try/except for "duplicate column name" (for existing databases), run at writer initialization time — same idempotent pattern specified for `flow_watchlist_daily` in Req 23

### 4.12 Flow Watchlist Enrichment Timing

32. The `earnings_play_signal` and `relative_underpricing_pct` columns added to `flow_watchlist_daily` (Req 22) are enriched at INSERT time only — when a new watchlist entry is created by FM. They are NOT refreshed on subsequent intra-day scans. This is acceptable because:
    - EI runs once in the morning; signals don't change intra-day
    - FM creates watchlist entries once per symbol per day
    - The signal value at creation time reflects the morning's computation

### 4.13 IV Crush Label Compatibility

33. After the severity scale update (Req 20), `earnings_moves.iv_crush_severity` will contain 6 possible values across old and new rows: `severe`, `moderate` (old), `high`, `normal` (new), `mild`, `minimal` (both). Any code that queries or displays this field must handle all 6 values. The `earnings_watchlist` will only ever show T+3 data, so it will only contain rows written after this update — but direct queries against `earnings_moves` will encounter both old and new labels.

---

## 5. Non-Goals (Out of Scope)

- **Finnhub BMO/AMC integration** — Phase 2, separate PRD. `earnings_time` will show "Unknown" until then.
- **Morning View TUI earnings screen** — future enhancement. Console output is the delivery mechanism for this PRD.
- **Signal threshold recalibration** — current thresholds (WATCH=15%, BUY=30%, STRONG BUY=50%) are provisional. Recalibration requires ~100 events with `move_vs_expected_pct` data, which Phase 3 unblocks.
- **Agent evaluation layer** — this PRD builds the infrastructure to feed agents. The agents themselves are a separate project.
- **Scenario calculator** — depends on Phase 3 data loops. Future phase.
- **Arbitrage scanner overhaul** — the scanner runs as sub-step 6 but remains a no-op until `earnings_sector_effects` accumulates correlation data. No code changes to the scanner itself.
- **Redesigning signal calculations** — the relative underpricing metric and straddle method are sound. No changes.
- **Backfilling old `iv_crush_severity` labels** — existing `earnings_moves` rows keep old labels. Only new rows use the 5-tier scale.
- **Archive signal data to `earnings_events`** — Phase 3 deliverable. Not in this PRD.
- **`earnings_snapshots` wiring** — Phase 3. Snapshots are accumulating but the calc pipeline still uses `option_symbol_summary` fallback.
- **Quick sync table additions** — `earnings_watchlist` does not need to be in the FM quick sync rotation. It is written in the morning and synced to query DB at Step 1.4.

---

## 6. Design Considerations

### Console Display

The earnings watchlist table uses box-drawing ASCII characters, matching the system's established console output style (see `docs/CONSOLE_DEVELOPER_GUIDE.md`). The table should be compact enough to fit in a standard 120-character terminal width. Column headers should be abbreviated where needed (e.g., "IV%ile", "Underprc%", "ExpMv%", "OI Bal", "Alerts", "Sentiment").

Pre-earnings rows show the signal-analysis columns. Post-earnings rows (T+1/T+2/T+3) shift focus to outcome columns (`actual_move_pct`, `move_direction`, `iv_crush_severity`). The `status` column visually distinguishes the two groups.

### Architecture Pattern

This follows the **Option Pipeline model** established during the console output refactor:
- **Strategy layer** (`ei_main.py`) owns pipeline logic, returns structured dicts, prints only progress lines
- **Orchestrator layer** (`main_runners.py`) owns visual structure — mission boxes, completion boxes, table rendering
- All formatted output flows through `tools/log_utils.py` to reach both console and `.log` files

---

## 7. Technical Considerations

### Dependencies

- `earnings_upcoming` must have clean data (Phase 0 complete — stale data filter in place)
- Step 1.1 (Morning Option Pipeline) must run first — provides fresh `option_symbol_summary` data


### Database Operations

- **Reads**: `earnings_upcoming`, `option_symbol_summary`, `flow_symbol_summary`, `historical_prices`, `earnings_moves`, `news_symbol_sentiment`
- **Writes**: `earnings_watchlist` (new), `flow_watchlist_daily` (add 2 columns)
- All writes are to `data/datalake.db` (production)
- All numeric values must use `clean_database_row()` from `tools/decimal_formatter.py`
- Use `now_eastern()` from `tools/timezone_utils.py` for all timestamps

### Performance

- Expected pipeline duration: 10-15 minutes total (6 sub-steps)
- Watchlist population itself should be fast (< 30 seconds) — it's a few JOINs across small result sets
- News enrichment is the variable: 0-25 API calls at ~2 seconds each = 0-50 seconds
- Time budget: OP finishes ~7:00 AM, FM starts ~9:15 AM — over 2 hours of runway

### Files Created

| File | Purpose |
|------|---------|
| `strategies/earnings_intel/ei_watchlist.py` | Watchlist writer module |

### Files Modified

| File | Changes |
|------|---------|
| `main.py` | Step renumbering (step_durations keys, results keys), replace arbitrage scanner call with EI pipeline call, remove evening Step 3.3 |
| `main_runners.py` | New `run_earnings_intelligence()` replacing `run_earnings_pipeline()` + `run_earnings_morning_scan()`, console table renderer |
| `strategies/earnings_intel/ei_main.py` | Unified `run_daily_pipeline()` with 6 sub-steps, watchlist sub-step integration |
| `strategies/earnings_intel/ei_post_earnings_calc.py` | IV crush severity scale update (4-tier → 5-tier) |
| `strategies/flow_monitor/fm_watchlist.py` | Add `earnings_play_signal` and `relative_underpricing_pct` to earnings enrichment |
| `tools/performance_writer.py` | Update `ei_mapping` step keys, add watchlist columns to `ei_pipeline_performance` |

---

## 8. Success Metrics

1. **Morning delivery**: Earnings watchlist table renders in the console log every trading day morning by ~7:15 AM
2. **Watchlist population**: Qualifying symbols appear on the watchlist with all pre-earnings columns populated (non-NULL for columns with data)
3. **Lifecycle tracking**: Symbols transition correctly through UPCOMING → TODAY → T+1 → T+2 → T+3 → deleted
4. **Post-earnings data**: T+1/T+2 symbols show interim `actual_move_pct` from `historical_prices`; T+3 symbols show full data from `earnings_moves`
5. **Cross-strategy enrichment**: `flow_watchlist_daily` entries near earnings show `earnings_play_signal` and `relative_underpricing_pct`
6. **Performance tracking**: `ei_pipeline_performance` records daily_pipeline runs with watchlist metrics
7. **No regressions**: Evening phase runs cleanly without the old Step 3.3; Friday Step 5.2 is unaffected
8. **Step key consistency**: All step keys in `main.py`, `main_runners.py`, and `performance_writer.py` match (no key mismatches like the PRD 0007 post-launch fix)

---

## 9. Open Questions

1. **Console column widths**: The exact column subset and abbreviations for the console table will be finalized during implementation based on terminal width constraints. The column priority order (req 17) provides guidance. **Fallback strategy**: if all columns don't fit at 120 chars, post-earnings columns (`actual_move_pct`, `move_direction`, `iv_crush_severity`) replace pre-earnings analysis columns (`expected_move_pct`, `historical_avg_move_pct`, `straddle_expected_move_pct`) for T+N rows — the investor cares about outcomes at that point, not predictions.
2. **BMO/AMC ambiguity on earnings day**: When `status` = `TODAY` and `days_to_earnings` = 0, the symbol could be BMO (already reported) or AMC (hasn't happened yet). Until Phase 2 (Finnhub) populates `earnings_time`, all earnings show "Unknown" and this distinction is invisible. No action needed now — but once BMO/AMC is available, the display should eventually distinguish "TODAY (BMO — already reported)" from "TODAY (AMC — reports tonight)."
3. **`alert_count_5d` and `oi_balance_text` staleness**: Both come from tables populated during market hours. At 7 AM display time, this data is from the prior trading session (~14 hours old). This is acceptable — yesterday's flow activity and OI balance are still informative context. No action needed, but column descriptions should not imply real-time data.
