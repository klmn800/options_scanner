# Performance Database Schema — `data/performance.db`

**Created:** 2026-02-23
**PRD:** tasks/0007-prd-performance-tracking-database.md
**Status:** Active — implemented 2026-02-23

---

## Overview

16 tables. Every orchestrator step gets its own table with typed columns. No generic catch-all.
Written once at end-of-day during **Phase 6: System Maintenance** — the final orchestrator
phase, running after Phase 5 (Friday ops) on Fridays or after Phase 4 (evening ops) Mon-Thu.
Data accumulates in-memory and `daily_state.json` throughout the day.

| # | Table | What | Rows/day |
|---|-------|------|----------|
| 1 | `daily_context` | Market conditions, universe size, news budget | 1 |
| 2 | `op_pipeline_performance` | Option Pipeline (morning + evening) | 2 |
| 3 | `ei_pipeline_performance` | Earnings Intelligence (daily/scan/weekly) | 1-3 |
| 4 | `fm_pre_market_performance` | FM pre-market phase | 1 |
| 5 | `fm_cycle_performance` | FM per-cycle detail during market hours | ~15-20 |
| 6 | `fm_post_market_performance` | FM post-market phase | 1 |
| 7 | `sync_performance` | Full and quick database syncs | ~20 |
| 8 | `metadata_performance` | Symbol metadata collection | 1 |
| 9 | `morning_views_performance` | Morning watchlist email | 1 |
| 10 | `backup_performance` | Database backup (daily/weekly) | 1 |
| 11 | `batch_mode_performance` | Autofix batch mode review | 1 |
| 12 | `airline_play_performance` | Airline symbol + options tracking | 1 |
| 13 | `sector_archive_performance` | Friday sector archive | 0-1 |
| 14 | `news_api_usage` | Alpha Vantage news API per-source breakdown | 1 |
| 15 | `earnings_date_sources` | Per-symbol earnings date source tracking | ~780 |
| 16 | `fm_baseline_performance` | FM volume baseline recalculation (Friday) | 0-1 |

**Total:** ~50-55 rows/day (plus ~780 earnings_date_sources rows on collection days). Negligible size.

---

## Table 1: `daily_context`

One row per trading day. Market conditions and system state that contextualizes all other tables.

DB file sizes are intentionally excluded — a single end-of-day snapshot is misleading since
datalake.db grows ~1-2 GB during FM market hours and WAL fluctuates wildly. DB size is
better tracked through `sync_performance.size_mb` on full syncs (3x/day), and DB health
is visible through timing proxies (INSERT degradation in `fm_cycle_performance.storage_seconds`,
WAL bloat in `sync_performance.duration_seconds`).

```sql
CREATE TABLE daily_context (
    trade_date          TEXT NOT NULL PRIMARY KEY,
    day_of_week         INTEGER NOT NULL,            -- 0=Mon through 4=Fri

    -- Market conditions (from market_daily_summary / FM post-market)
    market_regime       TEXT,           -- 'low_vol', 'normal', 'elevated', 'panic'
    market_direction    TEXT,           -- 'Bull', 'Bear', 'Neutral'
    spy_change_pct      REAL,           -- SPY daily % change
    vix_close           REAL,           -- VIX closing value

    -- Symbol universe
    universe_size       INTEGER,        -- Total symbols in KLMN 800
    symbols_with_data   INTEGER,        -- Symbols returning data in at least one FM cycle

    -- News sentiment budget
    news_api_calls_used INTEGER,        -- Alpha Vantage calls consumed (out of 25)

    recorded_at         TEXT NOT NULL
);
```

**Sources:** `market_daily_summary` table, FM collector stats (symbols_with_data accumulated across cycles), Alpha Vantage budget tracker

---

## Table 2: `op_pipeline_performance`

Option Pipeline. 2 rows/day (morning + evening). Columns from `OPOrchestrator.run_pipeline()` return dict.

```sql
CREATE TABLE op_pipeline_performance (
    trade_date          TEXT NOT NULL,
    run_type            TEXT NOT NULL,   -- 'morning' or 'evening'
    day_of_week         INTEGER NOT NULL,
    duration_seconds    REAL,            -- total_execution_time
    success             INTEGER NOT NULL,

    -- Collection phase
    collection_seconds  REAL,            -- collection.execution_time
    symbols_collected   INTEGER,         -- collection.symbols_collected
    symbols_failed      INTEGER,         -- collection.symbols_failed
    total_contracts     INTEGER,         -- collection.total_contracts
    api_calls           INTEGER,         -- collection.api_calls

    -- Rollup phase
    rollup_seconds      REAL,            -- rollup.execution_time
    symbols_processed   INTEGER,         -- rollup.symbols_processed
    summaries_created   INTEGER,         -- rollup.summaries_created

    -- OI Timing phase
    timing_seconds      REAL,            -- timing.execution_time
    contracts_updated   INTEGER,         -- timing.contracts_updated
    contracts_skipped   INTEGER,         -- timing.contracts_skipped

    -- Health
    health_status       TEXT,            -- HEALTHY / DEGRADED / CRITICAL / UNKNOWN
    collection_rate     REAL,            -- collection_phase.collection_rate (percent)

    -- Data quality (added 2026-03-17)
    no_contract_count   INTEGER,         -- symbols with 0 contracts after OI filter
    total_options_seen  INTEGER,         -- total options returned by Tradier API (before OI filter)
    total_options_filtered INTEGER,      -- options filtered out due to OI=0 or OI=null

    error_count         INTEGER DEFAULT 0,
    details             TEXT,            -- JSON: failed_symbols list, error messages

    recorded_at         TEXT NOT NULL,
    PRIMARY KEY (trade_date, run_type)
);
```

---

## Table 3: `ei_pipeline_performance`

Earnings Intelligence. 1-3 rows/day. One table for all 3 run types — columns that don't apply are NULL.

```sql
CREATE TABLE ei_pipeline_performance (
    trade_date          TEXT NOT NULL,
    run_type            TEXT NOT NULL,   -- 'daily_pipeline', 'morning_scan', 'weekly_refresh'
    day_of_week         INTEGER NOT NULL,
    duration_seconds    REAL,
    success             INTEGER NOT NULL,
    error_count         INTEGER DEFAULT 0,

    -- daily_pipeline fields (NULL for other run types)
    snapshots_created   INTEGER,
    moves_calculated    INTEGER,
    alerts_triggered    INTEGER,
    snapshot_seconds    REAL,            -- sub_tasks.snapshots.duration_seconds
    calculation_seconds REAL,            -- sub_tasks.calculations.duration_seconds
    expected_move_seconds REAL,          -- sub_tasks.expected_moves.duration_seconds

    -- morning_scan fields (NULL for other run types)
    earnings_today      INTEGER,
    opportunities_found INTEGER,
    high_quality        INTEGER,
    medium_quality      INTEGER,
    low_quality         INTEGER,
    persisted           INTEGER,

    -- weekly_refresh fields (NULL for other run types)
    earnings_found      INTEGER,
    events_archived     INTEGER,
    records_cleaned     INTEGER,
    upcoming_count      INTEGER,
    fetch_seconds       REAL,            -- sub_tasks.fetch.duration_seconds
    archive_seconds     REAL,            -- sub_tasks.archive.duration_seconds
    cleanup_seconds     REAL,            -- sub_tasks.cleanup.duration_seconds

    details             TEXT,            -- JSON: alert_details, sub-task specifics
    recorded_at         TEXT NOT NULL,
    PRIMARY KEY (trade_date, run_type)
);
```

---

## Table 4: `fm_pre_market_performance`

FM pre-market phase. 1 row/day. From `run_pre_market()` return dict.

```sql
CREATE TABLE fm_pre_market_performance (
    trade_date          TEXT NOT NULL PRIMARY KEY,
    day_of_week         INTEGER NOT NULL,
    duration_seconds    REAL,
    success             INTEGER NOT NULL,

    -- Alert resolution (sub_tasks.alert_resolution)
    alerts_resolved     INTEGER,
    alerts_building     INTEGER,         -- building state
    alerts_closing      INTEGER,         -- closing state
    alerts_neutral      INTEGER,         -- neutral state
    alerts_not_found    INTEGER,         -- contracts missing from today's OI data

    -- Sentiment update (sub_tasks.sentiment_update)
    sentiment_updated   INTEGER,         -- symbols_updated
    sentiment_building  INTEGER,
    sentiment_closing   INTEGER,
    sentiment_neutral   INTEGER,

    -- Pre-market sync (sub_tasks.sync)
    sync_success        INTEGER,         -- 0 or 1
    alerts_synced       INTEGER,
    watchlist_synced    INTEGER,

    recorded_at         TEXT NOT NULL
);
```

---

## Table 5: `fm_cycle_performance`

FM per-cycle detail during market hours. ~15-20 rows/day. From FMSessionStats timing lists.

`scan_timestamp` is the primary key (with `trade_date`) instead of `cycle_number` because
cycle numbers reset if the system is stopped and restarted mid-day — a common scenario
during maintenance. Timestamps are naturally unique and avoid overwrite/conflict.
The column name matches `flow_options_scans.scan_timestamp` for potential cross-table joins.

```sql
CREATE TABLE fm_cycle_performance (
    trade_date          TEXT NOT NULL,
    scan_timestamp      TEXT NOT NULL,   -- ISO timestamp, matches flow_options_scans.scan_timestamp
    cycle_number        INTEGER,         -- convenience column (list index), NOT part of PK
    day_of_week         INTEGER NOT NULL,
    success             INTEGER NOT NULL,

    -- Timing breakdown (seconds)
    cycle_seconds       REAL,
    collection_seconds  REAL,            -- API data collection
    storage_seconds     REAL,            -- DB write (subset of collection)
    analysis_seconds    REAL,            -- full analysis phase
    analysis_query_seconds   REAL,       -- DB reads within analysis
    analysis_scoring_seconds REAL,       -- CPU scoring within analysis
    analysis_db_write_seconds REAL,      -- DB writes within analysis
    alert_seconds       REAL,

    -- Quick sync (runs after each cycle)
    sync_seconds        REAL,
    sync_rows           INTEGER,

    -- Throughput
    contracts_collected INTEGER,         -- options contracts stored
    alerts_generated    INTEGER,         -- alerts created
    symbols_attempted   INTEGER,         -- symbols sent to API
    symbols_with_data   INTEGER,         -- symbols that returned data

    recorded_at         TEXT NOT NULL,
    PRIMARY KEY (trade_date, scan_timestamp)
);
```

**Example queries:**
```sql
-- Morning vs afternoon performance
SELECT CASE WHEN strftime('%H', scan_timestamp) < '12' THEN 'AM' ELSE 'PM' END AS session,
       AVG(cycle_seconds), AVG(storage_seconds), AVG(analysis_seconds)
FROM fm_cycle_performance GROUP BY session;

-- INSERT degradation across cycles (the bug we caught 2026-02-20)
SELECT cycle_number, storage_seconds
FROM fm_cycle_performance WHERE trade_date = '2026-02-20'
ORDER BY scan_timestamp;

-- 30-day baseline for autofix
SELECT AVG(cycle_seconds), AVG(collection_seconds)
FROM fm_cycle_performance WHERE trade_date >= date('now', '-30 days');

-- Join to actual scan data for a specific cycle
SELECT p.cycle_seconds, p.contracts_collected, COUNT(s.id) AS scan_rows
FROM fm_cycle_performance p
JOIN flow_options_scans s ON s.scan_timestamp = p.scan_timestamp
WHERE p.trade_date = '2026-02-20' AND p.cycle_number = 5;
```

---

## Table 6: `fm_post_market_performance`

FM post-market phase. 1 row/day. From `run_post_market()` return dict.

```sql
CREATE TABLE fm_post_market_performance (
    trade_date          TEXT NOT NULL PRIMARY KEY,
    day_of_week         INTEGER NOT NULL,
    duration_seconds    REAL,
    success             INTEGER NOT NULL,
    tasks_successful    INTEGER,         -- out of 5 total
    error_count         INTEGER DEFAULT 0,

    -- Backfill (sub_tasks.backfill)
    backfill_seconds    REAL,
    backfill_symbols_updated INTEGER,
    backfill_symbols_total   INTEGER,

    -- Market regime (sub_tasks.market_regime)
    regime_seconds      REAL,
    -- NOTE: actual regime/VIX/SPY values go in daily_context
    -- This table tracks the PERFORMANCE of computing them

    -- Symbol rollup (sub_tasks.symbol_rollup)
    rollup_seconds      REAL,
    rollup_symbols_processed INTEGER,
    rollup_summaries_created INTEGER,
    rollup_errors       INTEGER,

    -- Daily evaluation (sub_tasks.evaluation)
    evaluation_seconds  REAL,

    -- Watchlist cleanup (sub_tasks.watchlist_cleanup)
    cleanup_seconds     REAL,
    entries_archived    INTEGER,
    entries_deleted     INTEGER,

    recorded_at         TEXT NOT NULL
);
```

---

## Table 7: `sync_performance`

All database syncs — full (orchestrator, 3x/day) and quick (FM, ~15-20x/day).

DB size is tracked here rather than `daily_context` because full syncs provide 3 natural
measurement points per day (morning, evening, final), which is more useful for tracking
intra-day growth than a single snapshot.

```sql
CREATE TABLE sync_performance (
    trade_date          TEXT NOT NULL,
    sync_type           TEXT NOT NULL,    -- 'full' or 'quick'
    sync_timestamp      TEXT NOT NULL,    -- ISO timestamp
    duration_seconds    REAL,
    success             INTEGER NOT NULL,

    -- Full sync fields (NULL for quick)
    pages               INTEGER,          -- SQLite pages copied
    size_mb             REAL,             -- datalake.db size in MB (parsed from stdout)
    size_display        TEXT,             -- e.g. '7.16 GB' (human-readable, kept for logs)
    tables              INTEGER,          -- table count

    -- Quick sync fields (NULL for full)
    rows_synced         INTEGER,          -- new rows added

    recorded_at         TEXT NOT NULL,
    PRIMARY KEY (trade_date, sync_type, sync_timestamp)
);
```

**DB size trend query:**
```sql
-- Daily DB size growth over 30 days
SELECT trade_date, MAX(size_mb) AS eod_size_mb
FROM sync_performance
WHERE sync_type = 'full' AND trade_date >= date('now', '-30 days')
GROUP BY trade_date;

-- Intra-day growth (morning vs evening)
SELECT trade_date, MIN(size_mb) AS morning_mb, MAX(size_mb) AS evening_mb,
       MAX(size_mb) - MIN(size_mb) AS daily_growth_mb
FROM sync_performance
WHERE sync_type = 'full' AND trade_date >= date('now', '-7 days')
GROUP BY trade_date;
```

---

## Table 8: `metadata_performance`

Symbol metadata collection. 1 row/day. Subprocess — fields parsed from stdout summary banner.

```sql
CREATE TABLE metadata_performance (
    trade_date          TEXT NOT NULL PRIMARY KEY,
    day_of_week         INTEGER NOT NULL,
    duration_seconds    REAL,
    success             INTEGER NOT NULL,

    -- Parsed from COLLECTION SUMMARY banner in subprocess stdout
    symbols_processed   INTEGER,         -- "Symbols processed: N"
    quotes_fetched      INTEGER,         -- "Quotes fetched: N"
    fundamentals_fetched INTEGER,        -- "Fundamentals fetched: N"
    betas_calculated    INTEGER,         -- "Betas calculated: N"
    db_writes_successful INTEGER,        -- "Database writes: N successful"
    db_writes_failed    INTEGER,         -- "Database writes: N failed"

    recorded_at         TEXT NOT NULL
);
```

**Stdout pattern to parse:**
```
COLLECTION SUMMARY
  Symbols processed: 800
  Quotes fetched: 798
  Fundamentals fetched: 795
  Betas calculated: 790
  Database writes: 795 successful, 5 failed
```

---

## Table 9: `morning_views_performance`

Morning watchlist email generation. 1 row/day. Subprocess — minimal output.

```sql
CREATE TABLE morning_views_performance (
    trade_date          TEXT NOT NULL PRIMARY KEY,
    day_of_week         INTEGER NOT NULL,
    duration_seconds    REAL,
    success             INTEGER NOT NULL,

    email_sent          INTEGER,         -- 0 or 1 (parsed from "emailed successfully")

    recorded_at         TEXT NOT NULL
);
```

---

## Table 10: `backup_performance`

Database backup. 1 row/day (daily or weekly). Subprocess — fields parsed from stdout.

```sql
CREATE TABLE backup_performance (
    trade_date          TEXT NOT NULL,
    backup_type         TEXT NOT NULL,   -- 'daily' or 'weekly'
    day_of_week         INTEGER NOT NULL,
    duration_seconds    REAL,
    success             INTEGER NOT NULL,

    -- Parsed from stdout
    backup_size_mb      REAL,            -- from format_size() output
    table_count         INTEGER,         -- "N tables"
    size_verified       INTEGER,         -- 0 or 1 (source vs backup match)

    recorded_at         TEXT NOT NULL,
    PRIMARY KEY (trade_date, backup_type)
);
```

---

## Table 11: `batch_mode_performance`

Autofix batch mode review. 1 row/day (0 if no errors queued). In-process — fields from error queue.

```sql
CREATE TABLE batch_mode_performance (
    trade_date          TEXT NOT NULL PRIMARY KEY,
    day_of_week         INTEGER NOT NULL,
    duration_seconds    REAL,
    success             INTEGER NOT NULL,

    -- From get_error_queue() return dict
    total_errors        INTEGER,         -- queue['total_errors']
    unique_error_types  INTEGER,         -- queue['unique_errors']
    sessions_spawned    INTEGER,         -- process_error_queue() return value
    skipped             INTEGER,         -- 0 or 1 (e.g. Friday archive running)

    recorded_at         TEXT NOT NULL
);
```

---

## Table 12: `airline_play_performance`

Airline symbol + options tracking. 1 row/day. In-process — fields from return dicts.

```sql
CREATE TABLE airline_play_performance (
    trade_date          TEXT NOT NULL PRIMARY KEY,
    day_of_week         INTEGER NOT NULL,
    duration_seconds    REAL,
    success             INTEGER NOT NULL,

    -- Symbol tracking (from ap_symbol_tracking.run_symbol_tracking())
    symbols_processed   INTEGER,
    symbols_failed      INTEGER,

    -- Options tracking (from ap_options_tracking.run_options_tracking())
    contracts_tracked   INTEGER,         -- total_contracts_tracked

    recorded_at         TEXT NOT NULL
);
```

---

## Table 13: `sector_archive_performance`

Friday sector archive. 0-1 rows/day (only on Fridays). Subprocess — fields parsed from stdout.

```sql
CREATE TABLE sector_archive_performance (
    trade_date          TEXT NOT NULL PRIMARY KEY,
    day_of_week         INTEGER NOT NULL,  -- always 4 (Friday)
    duration_seconds    REAL,
    success             INTEGER NOT NULL,

    -- Parsed from ARCHIVE COMPLETE banner in subprocess stdout
    tier1_rows_archived INTEGER,
    tier1_rows_deleted  INTEGER,
    tier2_rows_archived INTEGER,
    tier2_rows_deleted  INTEGER,
    tier3_rows_archived INTEGER,
    tier3_rows_deleted  INTEGER,
    total_rows_archived INTEGER,         -- overall_stats['total_archived']
    total_rows_deleted  INTEGER,         -- overall_stats['total_deleted']
    error_count         INTEGER DEFAULT 0,

    recorded_at         TEXT NOT NULL
);
```

**Stdout pattern to parse:**
```
ARCHIVE COMPLETE
Total Duration: 2h 15m 30s
Total archived: 1,234,567 rows
Total deleted: 1,200,000 rows
```

---

## Table 14: `news_api_usage`

Alpha Vantage news API usage breakdown by source. 1 row/day. Counters accumulated in
`daily_state.json` via `_save_news_api_usage()` calls from EI and FM during the day.

```sql
CREATE TABLE news_api_usage (
    trade_date          TEXT NOT NULL PRIMARY KEY,
    calls_used          INTEGER NOT NULL,   -- total API calls consumed
    calls_available     INTEGER NOT NULL,   -- 25 - calls_used
    calls_ei            INTEGER,            -- calls by Earnings Intelligence (Step 1.2)
    calls_fm            INTEGER,            -- calls by Flow Monitor (Phase 2)
    calls_other         INTEGER,            -- calls by ad-hoc/other sources
    symbols_enriched    INTEGER,            -- calls that returned usable sentiment
    zero_article_calls  INTEGER,            -- calls that returned no usable data
    recorded_at         TEXT NOT NULL
);
```

**Invariant:** `calls_ei + calls_fm + calls_other = calls_used`

**Data source:** `daily_state.json` → `news_api_usage` dict. Falls back to
`cache/alphavantage_daily_usage.json` for `calls_used` if per-source counters are missing.

**Example queries:**
```sql
-- Daily utilization rate
SELECT trade_date, calls_used, calls_available,
       ROUND(calls_used * 100.0 / 25, 1) AS utilization_pct
FROM news_api_usage ORDER BY trade_date DESC LIMIT 14;

-- Waste rate (calls that returned nothing useful)
SELECT trade_date, zero_article_calls, calls_used,
       ROUND(zero_article_calls * 100.0 / NULLIF(calls_used, 0), 1) AS waste_pct
FROM news_api_usage WHERE calls_used > 0 ORDER BY trade_date DESC LIMIT 14;

-- EI vs FM consumption breakdown
SELECT trade_date, calls_ei, calls_fm, calls_other
FROM news_api_usage ORDER BY trade_date DESC LIMIT 14;
```

---

## Data Flow

```
During the trading day:
  ┌─────────────────────────────────────────────────┐
  │  In-Memory / daily_state.json                   │
  │                                                 │
  │  FMSessionStats ─── per-cycle timing lists      │
  │  run_*() returns ── rich dicts (after propagation) │
  │  step_durations ─── wall-clock per step         │
  │  _save_sync_performance() ── sync entries       │
  │  _save_news_api_usage() ── per-source counters  │
  └─────────────────────────────────────────────────┘

End of day — Phase 6: System Maintenance (single write):
  ┌─────────────────────────────────────────────────┐
  │  Collector reads all sources, writes to:        │
  │                                                 │
  │  daily_context ◄── market_daily_summary + FM stats │
  │  op_pipeline_performance ◄── OP return dicts    │
  │  ei_pipeline_performance ◄── EI return dicts    │
  │  fm_pre_market_performance ◄── FM pre return    │
  │  fm_cycle_performance ◄── FMSessionStats lists  │
  │  fm_post_market_performance ◄── FM post return  │
  │  sync_performance ◄── daily_state.json          │
  │  metadata_performance ◄── subprocess stdout     │
  │  morning_views_performance ◄── subprocess stdout│
  │  backup_performance ◄── subprocess stdout       │
  │  batch_mode_performance ◄── error queue dict    │
  │  airline_play_performance ◄── return dicts      │
  │  sector_archive_performance ◄── subprocess stdout│
  │  news_api_usage ◄── daily_state.json            │
  │                                                 │
  │  All in one transaction. Failure = warning only. │
  └─────────────────────────────────────────────────┘
```

---

## Autofix Integration

Error context gets a **thin pointer**, not embedded metrics:

```python
queue_error(
    error_type='op_collection_zero_contracts',
    context={
        # ...existing error fields...
        'performance_db': 'data/performance.db',
        'health_status': 'DEGRADED',
    },
    severity='CRITICAL'
)
```

The autofix agent queries the database directly:

```sql
-- "Is this slow, or normal?"
SELECT AVG(collection_seconds) AS avg, MAX(collection_seconds) AS max
FROM op_pipeline_performance
WHERE run_type = 'morning' AND trade_date >= date('now', '-30 days');

-- "When did degradation start?"
SELECT trade_date, collection_seconds, total_contracts
FROM op_pipeline_performance WHERE run_type = 'morning'
ORDER BY trade_date DESC LIMIT 14;

-- "What were market conditions when it broke?"
SELECT trade_date, vix_close, market_regime
FROM daily_context ORDER BY trade_date DESC LIMIT 7;

-- "How big is the database and is it growing fast?"
SELECT trade_date, MAX(size_mb) AS eod_size_mb
FROM sync_performance WHERE sync_type = 'full'
GROUP BY trade_date ORDER BY trade_date DESC LIMIT 14;

-- "Is INSERT time growing within a single day?"
SELECT scan_timestamp, cycle_number, storage_seconds, sync_seconds
FROM fm_cycle_performance WHERE trade_date = '2026-02-20'
ORDER BY scan_timestamp;

-- "Did the archive affect Friday performance?"
SELECT a.duration_seconds AS archive_time, a.total_rows_deleted,
       f.duration_seconds AS fm_post_time
FROM sector_archive_performance a
JOIN fm_post_market_performance f USING (trade_date)
WHERE a.day_of_week = 4;
```
