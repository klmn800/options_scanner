# data/ - Databases and Data Collection

This directory houses all SQLite databases, database maintenance scripts, and data collection scripts that operate outside of the strategy modules.

---

## Databases

### Production Database

| File | Purpose | Size |
|------|---------|------|
| `datalake.db` | Primary production database. Written to by all collection pipelines. | ~9 GB |
| `datalake_query.db` | Read-only analysis copy. Synced 3x daily from datalake.db. | ~9 GB |

**Two-database workflow:** Production pipelines write to `datalake.db`. All analysis, Claude Code queries, Oracle, and reporting tools read from `datalake_query.db`. This prevents locking conflicts between collection and analysis.

**Do not query `datalake.db` during collection windows** (6:30-8:00 AM, 4:30-6:00 PM). Use `datalake_query.db` instead.

### Backup Databases

| File | Purpose | Updated |
|------|---------|---------|
| `datalake_backup.db` | Daily backup. Overwrites previous day. | Every evening ~7:15 PM |
| `datalake_backup_weekly.db` | Weekly backup. Preserved until next Friday. | Friday nights after archive |

### Other Databases

| File | Purpose |
|------|---------|
| `analysis_cache.db` | Oracle AI analysis cache (symbol_ai_analysis table) |

### WAL Files

`datalake.db-shm` and `datalake.db-wal` are SQLite write-ahead log files. They appear when the database is actively being written to and are managed automatically by SQLite. Do not delete them while the database is in use.

---

## Data Collection Scripts

These scripts collect data from external APIs and populate tables in `datalake.db`. They run as subprocesses called by the main orchestrator or strategy modules.

| Script | Called By | Schedule | What It Does |
|--------|-----------|----------|-------------|
| `market_daily_summary.py` | `fm_main.py` (Flow Monitor) | Daily, post-market | Collects SPY/VIX/sector ETF OHLCV + market breadth via Tradier API. Calculates VIX regime and market direction. Writes to `market_daily_summary` table. |
| `symbol_metadata.py` | `main_runners.py` (morning pipeline) | Daily, ~6:35 AM | Populates `symbol_metadata` with sector/industry (Morningstar codes), market cap, beta, liquidity tiers via Tradier API. Essential for sector archive routing. |
| `tradier_historical_backfill.py` | On-demand / daily | Daily update mode | Fetches last 5 trading days of OHLCV for all KLMN 800 symbols. Writes to `historical_prices` table. Also supports full 2021-present backfill via `--backfill-2021`. |

### On-Demand Utilities

These are not scheduled but available for manual backfill operations:

| Script | What It Does |
|--------|-------------|
| `yfinance_historical_backfill.py` | Alternative historical price backfill using free Yahoo Finance API. No API key needed. Supports `--resume` for interrupted collections. Use if Tradier API is unavailable. |
| `yfinance_earnings_historical.py` | Collects historical earnings data (dates, EPS estimates/actuals) via Yahoo Finance. Writes to `temp_earnings_raw`. Supports `--all-klmn`, `--missing-klmn`, `--symbols`. |

---

## health/ - Database Maintenance

Scripts that maintain database health: backups, syncs, archiving, and optimization.

| Script | Purpose | Schedule |
|--------|---------|----------|
| `db_backup.py` | Backup and query database sync. Handles daily backups, 3x daily query DB sync, and quick sync during market hours. | Automated by main.py |
| `db_archive_sector.py` | Three-tier sector-based archiving. Moves/copies aged data from production into sector archive databases. | Friday nights (~7:30 PM) |
| `db_optimize_sectors.py` | Runs ANALYZE on all sector archive databases for query performance. | After Friday archive |
| `close_db_browser.py` | Closes DB Browser for SQLite to release file locks. Called automatically by db_backup.py when locks are detected during sync. | On-demand (via subprocess) |
| `create_sector_archive.py` | Creates new sector archive databases with proper schema. | Manual (one-time per new sector) |
| `migrate_symbol_archive.py` | Moves a symbol's data between sector archives (e.g., if sector assignment changes). | Manual (rare) |

### Normal Operation

On a typical trading day, the health scripts run in this order:

1. **~7:20 AM** - Query DB Sync #1 (after morning Option Pipeline)
2. **~5:45 PM** - Query DB Sync #2 (after evening Option Pipeline)
3. **~7:00 PM** - Query DB Sync #3 (final complete dataset)
4. **~7:15 PM** - Daily backup (datalake.db -> datalake_backup.db)
5. **Friday ~7:30 PM** - Archive + optimize + weekly backup

### What's Normal vs. Needs Attention

**Normal:**
- Query sync takes ~14 minutes (I/O bound, copying ~9 GB)
- Friday archive takes several hours (moves millions of rows across 15 sector DBs)
- Archive may not finish all tiers every Friday (graceful timeout at Monday 5:45 AM)
- `datalake.db` size fluctuates: grows during the week, shrinks after Friday archive+VACUUM

**Needs attention:**
- Query sync consistently failing (stale analysis data)
- Archive not running for 2+ weeks (production DB bloat)
- `datalake.db` growing past ~12 GB (archive may be stuck)
- "database is locked" errors during sync (usually DB Browser left open)

---

## sector_archive/ - Historical Data by Sector

15 sector-based SQLite databases containing archived historical data. Updated every Friday night by the three-tier archiver. Total ~85 GB.

See `sector_archive/README.md` for complete documentation including:
- Archive contents and sizes per sector
- Three-tier retention strategy (15d/30d/90d)
- How to query archives
- Schema reference

---

## Other Files

| File/Folder | Purpose |
|-------------|---------|
| `datalake_schema_2026-01-01.md` | Current database schema documentation (table definitions, column lists) |
| `logs/` | Log files from data collection scripts |
| `Deprecated/` | Old scripts and schema docs no longer in use |
| `__init__.py` | Python package marker |

---

## Key Rules for Working in This Directory

1. **Always use `datalake_query.db` for analysis.** Only touch `datalake.db` when writing production pipeline code.
2. **Never run `db_backup.py --sync` without approval.** Syncing during market hours interrupts live data collection.
3. **Open interest is point-in-time.** Never `SUM(open_interest)` across dates — always filter to a specific `trade_date` first.
4. **All numeric values follow decimal precision policy.** Prices: 2 decimals. Greeks/IV: 4 decimals. Use `tools/decimal_formatter.py` before database writes.
5. **Friday nights are for archiving.** Avoid heavy database operations on Friday evenings.
