# PRD: Performance Tracking Database

**PRD Number:** 0007
**Created:** 2026-02-23
**Status:** Draft
**Origin:** big-to-do-list.txt item 8, performance_tracking_notes.md brainstorming, console output refactor observations

---

## 1. Introduction/Overview

Every strategy and orchestrator step in the Options Scanner computes timing data, contract counts, alert counts, and health metrics — then discards them at end of day. There is no historical record of how long things take, no baselines to detect degradation, and no way for the autofix system to distinguish "this is slow" from "this is normal."

This feature creates a dedicated `data/performance.db` database that persists daily performance metrics from all orchestrator steps, FM per-cycle detail, and strategy-level counts. It becomes a first-class diagnostic resource for the autofix system, trend detection, and development regression analysis.

### Prior Art

- `docs/performance_tracking_enhancement/performance_tracking_notes.md` — extensive brainstorming, schema options, catalogue of measurable metrics, dimensional analysis requirements
- `docs/performance_tracking_enhancement/performance_db_schema.md` — definitive schema reference (13 tables, typed columns, example queries)
- `logs/daily_state.json` — currently stores orchestrator results (bool), FM session stats, and sync performance (added 2026-02-23)
- `FMSessionStats` — in-memory accumulator with save/restore via daily_state.json
- `FMPerformanceTracker` — older in-memory-only tracker (to be consolidated and deprecated)
- `main.py` `step_durations` dict — already captures wall-clock for all steps, only used for day-end summary display

---

## 2. Goals

1. **Persist daily performance data** for all orchestrator steps and FM cycles in `data/performance.db`
2. **Enable autofix diagnostics** by providing queryable historical baselines (the autofix agent queries the DB itself — error context provides only a thin pointer)
3. **Propagate strategy return dicts** through `run_*()` methods so the orchestrator has access to rich metrics (contract counts, alert counts, health status), not just bool
4. **Track FM per-cycle detail** with per-cycle rows (~15-20/day) to enable time-of-day and intra-day degradation analysis
5. **Consolidate FM tracking** by merging useful FMPerformanceTracker features into FMSessionStats and deprecating the tracker
6. **Detect degradation trends** over weeks/months (collection time creeping up, INSERT performance degrading, DB size growth rate)

---

## 3. User Stories

- **As the autofix system**, when I spawn a Claude session to diagnose an error, I want to query `performance.db` for 30-day baselines so I can determine whether today's timing is abnormal and when degradation started.
- **As a developer (Ben)**, I want to query `performance.db` to see if a code change caused a performance regression (e.g., "did analysis time jump after the Feb 20 PRAGMA tuning?").
- **As the orchestrator**, I want to record how long each step took, how many items were processed, and whether it succeeded — automatically, every trading day.
- **As a developer**, I want FM per-cycle data so I can answer "are 2 PM cycles consistently slower than 10 AM?" and "is INSERT time growing across cycles today?"
- **As the autofix system**, when I receive an error with `performance_db_path` in the context, I want to query it independently rather than having full metrics embedded in the error queue entry.

---

## 4. Functional Requirements

### 4.1 Database and Schema

1. Create `data/performance.db` as a dedicated SQLite database (separate from datalake.db).
2. Create 13 tables — one per orchestrator step or step category. Every table has typed columns mapped to the step's actual return dict or parsed subprocess output. No generic catch-all table.

**Full schema reference:** `docs/performance_tracking_enhancement/performance_db_schema.md`

**Summary of tables:**

| # | Table | Source | Rows/day |
|---|-------|--------|----------|
| 1 | `daily_context` | market_daily_summary, FM stats, AV budget | 1 |
| 2 | `op_pipeline_performance` | OP run_pipeline() return dict | 2 |
| 3 | `ei_pipeline_performance` | EI return dicts (3 run types, one table with NULLs) | 1-3 |
| 4 | `fm_pre_market_performance` | FM run_pre_market() return dict | 1 |
| 5 | `fm_cycle_performance` | FMSessionStats per-cycle lists | ~15-20 |
| 6 | `fm_post_market_performance` | FM run_post_market() return dict | 1 |
| 7 | `sync_performance` | daily_state.json + FMSessionStats | ~20 |
| 8 | `metadata_performance` | subprocess stdout parsing | 1 |
| 9 | `morning_views_performance` | subprocess stdout parsing | 1 |
| 10 | `backup_performance` | subprocess stdout parsing | 1 |
| 11 | `batch_mode_performance` | error queue return dict | 1 |
| 12 | `airline_play_performance` | return dicts | 1 |
| 13 | `sector_archive_performance` | subprocess stdout parsing | 0-1 |

**Key schema decisions:**

3. `daily_context` contains market conditions (regime, direction, VIX, SPY), universe size, and news API budget. DB file sizes are excluded — a single end-of-day snapshot is misleading since datalake.db grows ~1-2 GB during FM hours. DB size is tracked via `sync_performance.size_mb` on full syncs (3x/day), and DB health is visible through timing proxies in other tables.

4. `fm_cycle_performance` uses `PRIMARY KEY (trade_date, scan_timestamp)` instead of `(trade_date, cycle_number)`. Cycle numbers reset if the system is stopped and restarted mid-day (common during maintenance), which would cause overwrites. `scan_timestamp` matches `flow_options_scans.scan_timestamp` for potential cross-table joins. `cycle_number` is kept as a convenience column (not part of PK).

5. `sync_performance` includes `size_mb REAL` (numeric, parsed from stdout) alongside `size_display TEXT` (human-readable). This is the primary source for DB size trending, with 3 measurements/day on full syncs.

6. `ei_pipeline_performance` uses a single table for 3 run types with NULL columns for non-applicable fields. At most 3 rows/day; the NULL blocks make run types visually obvious.

### 4.2 Return Dict Propagation

7. Change all `run_*()` methods in `main_runners.py` to return the strategy's result dict instead of `True`/`False`. The orchestrator already holds these dicts in local variables — the change is replacing `return True` with `return result_dict`. Methods that run subprocesses should return a standardized dict with at minimum `{'success': bool, 'duration_seconds': float}`.
8. The OP pipeline already returns a comprehensive dict from `OPOrchestrator.run_pipeline()` with nested collection/rollup/timing/health sub-dicts. Pass it through.
9. The EI system already returns rich dicts from `run_daily_pipeline()`, `run_weekly_refresh()`, `run_morning_scan()` with sub_tasks breakdowns. Pass them through.
10. FM phases (`run_pre_market`, `run_market_hours`, `run_post_market`) already return dicts. Pass them through.
11. For subprocess-based steps (metadata, morning views, backup, sync, archive), construct a result dict from subprocess output parsing and wall-clock timing.
12. `main.py` must handle both the new dict returns and backward compatibility — `results[step_name]` should store the dict, while `_save_orchestrator_result()` continues to work (it can store the full dict or just the success bool).

### 4.3 End-of-Day Collection — Phase 6: System Maintenance

13. Performance data collection runs as **Phase 6: System Maintenance** in the orchestrator — the final phase before closing. Runs after Phase 5 (Friday ops) on Fridays, after Phase 4 (evening ops) Mon-Thu. Phase 5 is skipped on non-Fridays, so the schedule jumps from Phase 4 to Phase 6 — this is by design (categorical numbering).
14. Create a collection function (in `main_runners.py` or a new `tools/performance_writer.py`) that reads all accumulated data and writes to `performance.db`.
15. The collection function reads:
    - `step_durations` dict from `main.py` (wall-clock for all steps)
    - Return dicts from each `run_*()` method (contract counts, alert counts, health status)
    - FM session stats from `daily_state.json` or in-memory (per-cycle timing lists)
    - Sync performance entries from `daily_state.json`
16. Writes rows to all 13 tables in a single transaction:
    - `daily_context` — 1 row from market_daily_summary + FM stats + AV budget
    - `op_pipeline_performance` — 2 rows (morning + evening) from OP return dicts
    - `ei_pipeline_performance` — 1-3 rows from EI return dicts
    - `fm_pre_market_performance` — 1 row from FM pre-market return dict
    - `fm_cycle_performance` — ~15-20 rows from FMSessionStats timing lists
    - `fm_post_market_performance` — 1 row from FM post-market return dict
    - `sync_performance` — ~20 rows from daily_state.json
    - `metadata_performance` — 1 row from parsed subprocess stdout
    - `morning_views_performance` — 1 row from parsed subprocess stdout
    - `backup_performance` — 1 row from parsed subprocess stdout
    - `batch_mode_performance` — 1 row from error queue return dict
    - `airline_play_performance` — 1 row from return dicts
    - `sector_archive_performance` — 0-1 rows (Fridays only) from parsed subprocess stdout
17. Logs confirmation: `beautiful_log("Performance data saved: N rows across 13 tables", 'success')`
18. On failure, log a warning and continue — performance tracking must never block the orchestrator.

### 4.4 FM Per-Cycle Data Collection

19. During FM market hours, each cycle's timing breakdown is already accumulated in `FMSessionStats` lists. The end-of-day collection reads these lists and writes one `fm_cycle_performance` row per cycle, keyed by `scan_timestamp`.
20. Add `scan_timestamps` list to `FMSessionStats` — record the scan timestamp at the start of each cycle. This becomes the PK for `fm_cycle_performance`.
21. Add quick sync timing (`sync_seconds`, `sync_rows`) to `FMSessionStats` accumulation — currently tracked in the cycle loop but not persisted. Add `sync_times` and `sync_row_counts` lists.
22. Add `contracts_collected` and `alerts_generated` per-cycle tracking to `FMSessionStats` — these counts exist in the cycle loop but are not accumulated.
23. Add `symbols_attempted` and `symbols_with_data` per-cycle tracking.

### 4.5 FMPerformanceTracker Deprecation

**Audit result (2026-02-23):** FMPerformanceTracker is 83% dead code. 2 of 12 methods are called (`track_cycle_performance` and `track_error`, both in `fm_main.py`). FMHealthReporter has zero references to it — the reporter maintains its own independent duplicate data structures. FMSessionStats already tracks the same timing data with persistence.

24. Remove the two `performance_tracker` call sites in `fm_main.py` (lines ~1409 and ~1417). FMSessionStats already captures the same cycle timing data with persistence — these calls feed data into a non-persistent black hole.
25. Remove the `FMPerformanceTracker` import and both instantiations in `fm_main.py` (lines ~1102 and ~1537).
26. Move `fm_performance_tracker.py` to `strategies/flow_monitor/Deprecated/`. No migration needed — nothing useful to migrate.
27. Verify FMHealthReporter continues to work unchanged (it has zero dependency on the tracker).

### 4.6 Autofix Integration

28. Add `performance_db_path` to the context dict in `queue_error()` and `handle_error()` calls at orchestrator-level call sites (the ~22 calls in `main_runners.py`). This is a thin pointer — just the file path string — so the autofix agent knows where to query.
29. Add a `health_status` field to the context dict at orchestrator-level call sites where it's available (OP pipeline health, FM health reporter status). One string field, not embedded metrics.
30. Do NOT embed full performance summaries in error context. The autofix agent has database query tools and can independently query `performance.db` for baselines when needed.
31. Update `autofix/reference/AUTOFIX_CHEAT_SHEET.md` to document the `performance_db_path` context field and provide example queries the agent can run against all 13 tables. Include examples like:
    - `SELECT avg(duration_seconds) FROM op_pipeline_performance WHERE run_type = 'morning' AND trade_date >= date('now', '-30 days')`
    - `SELECT scan_timestamp, cycle_number, storage_seconds, sync_seconds FROM fm_cycle_performance WHERE trade_date = ? ORDER BY scan_timestamp`
    - `SELECT trade_date, MAX(size_mb) AS eod_size_mb FROM sync_performance WHERE sync_type = 'full' GROUP BY trade_date ORDER BY trade_date DESC LIMIT 14`

### 4.7 Orchestrator Step Name Registry and Table Routing

32. Define a canonical registry that maps orchestrator steps to their target performance table and key values. This ensures the end-of-day collector routes each step's data to the correct table.

**Routes to `daily_context`** (1 row, assembled from multiple sources):
- Market conditions from FM post-market / `market_daily_summary`
- Universe size from `get_symbols_klmn800()`
- `symbols_with_data` from FMSessionStats
- `news_api_calls_used` from Alpha Vantage budget tracker

**Routes to `op_pipeline_performance`:**
- `'1.1 Morning Option Pipeline'` → `run_type='morning'`
- `'3.1 Evening Option Pipeline'` → `run_type='evening'`

**Routes to `ei_pipeline_performance`:**
- `'1.2 Arbitrage Scanner'` → `run_type='morning_scan'`
- `'3.3 Earnings Daily Pipeline'` → `run_type='daily_pipeline'`
- `'3.6 Earnings Weekly Refresh'` → `run_type='weekly_refresh'` (Fridays only)

**Routes to FM tables:**
- `'2.0 Flow Monitor (pre-market)'` → `fm_pre_market_performance`
- `'2.0 Flow Monitor (market hours)'` → `fm_cycle_performance` (per-cycle rows from FMSessionStats)
- `'2.0 Flow Monitor (post-market)'` → `fm_post_market_performance`

**Routes to per-step tables:**
- `'1.3 Metadata Collection'` → `metadata_performance`
- `'1.5 Morning Views'` → `morning_views_performance`
- `'3.4 Airline Play Phase'` → `airline_play_performance`
- `'4.1 Database Backup'` → `backup_performance`
- `'4.2 Batch Mode Review'` → `batch_mode_performance`
- `'5.3 Sector Archive'` → `sector_archive_performance` (Fridays only)

**Routes to `sync_performance`:**
- `'1.4 Query Sync (Morning)'` → `sync_type='full'`
- `'3.2 Query Sync (Evening)'` → `sync_type='full'`
- `'3.5 Query Sync (Final)'` → `sync_type='full'`
- FM quick syncs → `sync_type='quick'` (from FMSessionStats)

---

## 5. Non-Goals (Out of Scope)

1. **API-level instrumentation** — Tradier call counts, per-call response times, Alpha Vantage budget tracking beyond daily total. These require changes inside `tradier_api.py` and `alphavantage_api.py`. Future phase.
2. **Morning View integration** — A "system health" panel in the TUI. Future phase (depends on this database existing first).
3. **Automated alerting/thresholds** — Automatically triggering autofix when performance exceeds N standard deviations. Future phase (requires baseline data to exist first).
4. **Real-time monitoring** — This is end-of-day persistence. The existing health JSON files (`flow_monitor_health.json`, etc.) continue to serve real-time needs.
5. **Per-symbol performance tracking** — Which symbols are slowest to collect, which have the most errors. Useful but too granular for phase 1.
6. **Migrating existing daily_state.json** — The sync_performance data already landing in daily_state.json will be migrated to sync_performance table by the end-of-day collection. We don't need to change `_save_sync_performance()` — it continues to write to daily_state.json as the intra-day buffer, and the collector reads it at end-of-day.
7. **DB file size snapshots** — Single-point-in-time DB size measurements are misleading (datalake.db grows ~1-2 GB intra-day, WAL fluctuates). DB size is tracked via `sync_performance.size_mb` on full syncs (3x/day); DB health is visible through timing proxies in FM cycle and sync tables.
8. **Memory (RAM) tracking** — psutil-based readings don't capture SQLite page cache (256MB), and every performance issue we've diagnosed was visible through timing data, not memory usage.

---

## 6. Design Considerations

### Database Location
`data/performance.db` — sits alongside `datalake.db` and `datalake_query.db` as an operational database. Not in `data/health/` (which contains scripts, not databases) or `autofix/` (which is a consumer, not the owner).

### Schema Choice
One table per orchestrator step. Every step with structured output gets its own table with typed columns mapped directly to the step's return dict or parsed subprocess output. No generic `step_performance` catch-all — tables are cheap, and typed columns enable direct SQL queries without JSON parsing, which is critical for autofix usability. See `docs/performance_tracking_enhancement/performance_db_schema.md` for complete DDL.

### Orchestrator Placement
Phase 6: System Maintenance — the final orchestrator phase. Runs after Phase 5 (Friday ops) on Fridays, after Phase 4 (evening ops) Mon-Thu. Phase 5 is Friday-only, so non-Friday days jump from Phase 4 to Phase 6.

### Write Pattern
Single end-of-day write in Phase 6. No per-cycle writes to performance.db during market hours — all FM data accumulates in memory (FMSessionStats) and gets flushed once. This avoids lock contention and keeps the hot path clean.

### Retention
Keep forever. Daily row counts by table:
- `daily_context`: 1 row
- `op_pipeline_performance`: 2 rows (morning + evening)
- `ei_pipeline_performance`: 1-3 rows (daily + morning scan + weekly on Fridays)
- `fm_pre_market_performance`: 1 row
- `fm_cycle_performance`: ~15-20 rows
- `fm_post_market_performance`: 1 row
- `sync_performance`: ~20 rows (3 full + ~15-17 quick)
- `metadata_performance`: 1 row
- `morning_views_performance`: 1 row
- `backup_performance`: 1 row
- `batch_mode_performance`: 1 row
- `airline_play_performance`: 1 row
- `sector_archive_performance`: 0-1 rows (Fridays)

Total: ~50-55 rows/day, ~13,000 rows/year. Negligible size.

### Failure Isolation
Performance tracking must never crash the orchestrator. All writes wrapped in try/except with warning-level logging on failure. If performance.db is locked or corrupted, the trading day continues normally.

---

## 7. Technical Considerations

### Dependencies
- `main_runners.py` — every `run_*()` method needs return type change (bool → dict)
- `main.py` — `results` dict, `_print_day_summary()`, Phase 6 step addition
- `main_ui.py` — `_save_orchestrator_result()` may need to handle dicts; banner update for Phase 6
- `fm_session_stats.py` — add scan_timestamps, sync timing, contract counts, symbols_attempted/with_data
- `fm_performance_tracker.py` — deprecation target
- `fm_health_reporter.py` — rewire from tracker to session stats
- `fm_main.py` — pass additional per-cycle metrics to session stats
- `tools/autofix.py` — no changes needed (context dict is already flexible)
- `autofix/reference/AUTOFIX_CHEAT_SHEET.md` — documentation update with 13-table query examples

### Existing queue_error/handle_error Call Sites
71 total call sites across the codebase (48 queue_error, 23 handle_error). Only the ~22 orchestrator-level calls in `main_runners.py` need the `performance_db_path` enrichment. Strategy-internal and infrastructure calls can be enriched later.

### Backward Compatibility
- `_save_orchestrator_result()` currently stores bool. After propagation, it will store dicts. `_load_daily_state()` and `_print_day_summary()` must handle both formats gracefully (check `isinstance(result, dict)` and extract success bool).
- FM code that checks `if run_pre_market():` must handle dict truthiness (non-empty dict is truthy, so this works naturally, but explicit `result.get('success')` is clearer).

### Existing Infrastructure to Leverage
- `step_durations` dict in `main.py` already wraps every `run_*()` call with `time.time()`. This is the wall-clock source for all `duration_seconds` fields.
- `daily_state.json` fm_session already has per-cycle timing lists. The end-of-day collector reads these.
- `daily_state.json` sync_performance already has full/quick sync entries (added 2026-02-23).
- OP pipeline `run_pipeline()` returns a comprehensive dict with collection/rollup/timing/health sub-dicts.
- EI functions return rich dicts with sub_tasks breakdowns.
- FM phases return structured dicts with sub_tasks breakdowns.

---

## 8. Success Metrics

1. **Data accumulation** — After 1 week of trading, `performance.db` contains rows in all 13 tables with typed, queryable columns.
2. **Autofix queryability** — A spawned autofix session can query `SELECT avg(collection_seconds), avg(total_contracts) FROM op_pipeline_performance WHERE run_type = 'morning' AND trade_date >= date('now', '-30 days')` and get meaningful, typed results without JSON parsing.
3. **DB size trending** — Can answer "how fast is the database growing?" from `SELECT trade_date, MAX(size_mb) FROM sync_performance WHERE sync_type='full' GROUP BY trade_date`.
4. **Degradation detection** — Can identify the WAL bloat issue (2026-02-22) and INSERT degradation issue (2026-02-20) retroactively from the data: cycle-over-cycle timing growth within a single day via `fm_cycle_performance` ordered by `scan_timestamp`.
5. **FM consolidation** — `FMPerformanceTracker` deprecated, `FMSessionStats` is the single source of truth for FM metrics, health reporter works correctly with new source.
6. **No orchestrator impact** — Performance tracking failures never prevent trading operations from running. Phase 6 failure = warning log only.

---

## 9. Resolved Questions

1. **Quick sync cycle correlation** — Both. `fm_cycle_performance.sync_seconds` captures the quick sync for that cycle (enables "why was this cycle slow?" without a JOIN). `sync_performance` also has it for sync-specific trending. ~15-20 extra REAL values/day — trivial cost.
2. **Weekend/holiday handling** — `day_of_week` is sufficient. The system only runs on trading days (market calendar aware). No `is_post_holiday` flag needed.
3. **FMPerformanceTracker callers** — Audited 2026-02-23. Only 2 of 12 methods called (both in `fm_main.py`). FMHealthReporter has zero references. No migration needed — straight deprecation. See Section 4.5.
4. **EI table design** — Single table with NULLs for 3 run types. At most 3 rows/day; NULL blocks make run types obvious. Simpler than 3 separate tables for the same queryability.
