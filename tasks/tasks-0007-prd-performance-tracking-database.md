# Tasks: Performance Tracking Database

**PRD:** tasks/0007-prd-performance-tracking-database.md
**Schema:** docs/performance_tracking_enhancement/performance_db_schema.md
**Generated:** 2026-02-23

## Relevant Files

- `tools/performance_writer.py` - **New file.** Core module: schema creation, data assembly, end-of-day write to `data/performance.db`. Contains `ensure_schema()`, `write_daily_performance()`, and subprocess stdout parsers.
- `main.py` - Orchestrator. Add Phase 6: System Maintenance after Phase 5/4. Update `_print_day_summary()` to handle dict results. Update `results` dict handling.
- `main_runners.py` - Pipeline runners. Change all `run_*()` return types from bool to dict. Add `run_performance_collection()` method. Add `performance_db_path` to `queue_error`/`handle_error` context dicts.
- `main_ui.py` - UI mixin. Update `print_banner()` to include Phase 6. Update `_save_orchestrator_result()` to handle dicts.
- `strategies/flow_monitor/fm_session_stats.py` - Add `scan_timestamps`, `contracts_collected`, `alerts_generated`, `symbols_attempted`, `symbols_with_data` lists. Update `save_to_daily_state()` and `load_from_daily_state()`.
- `strategies/flow_monitor/fm_main.py` - Pass new per-cycle metrics (scan_timestamp, contracts, alerts, symbols) to `FMSessionStats.record_cycle()`. Remove `FMPerformanceTracker` import, instantiation, and 2 call sites.
- `strategies/flow_monitor/fm_performance_tracker.py` - Deprecation target. Move to `strategies/flow_monitor/Deprecated/`.
- `autofix/reference/AUTOFIX_CHEAT_SHEET.md` - Add `performance.db` section with example queries for all 13 tables.
- `docs/performance_tracking_enhancement/performance_db_schema.md` - Existing schema reference. Update status from "Proposed" to "Active" after implementation.

### Notes

- No formal test framework in this project. Validation is done via manual testing and verification scripts.
- The schema doc (`performance_db_schema.md`) is the definitive reference for all 13 table DDL statements — the writer module should use those exact CREATE TABLE statements.
- `daily_state.json` continues as the intra-day buffer. The performance writer reads it at end-of-day; no changes needed to `_save_sync_performance()`.
- All subprocess stdout parsing uses regex on already-captured output — the streaming subprocess infrastructure (`_run_streaming_subprocess`) already captures lines.

## Tasks

- [x] 1.0 Create performance.db schema and writer module
  - [x] 1.1 Create `tools/performance_writer.py` with `ensure_schema()` function containing all 13 CREATE TABLE IF NOT EXISTS statements from the schema doc. Function takes optional `db_path` parameter (default `data/performance.db`).
  - [x] 1.2 Write `write_daily_performance(trade_date, results, step_durations, fm_session_data, sync_entries)` — the main entry point. Opens a single connection, writes all 13 tables in one transaction, logs row counts. Wrapped in try/except that logs warnings on failure (never raises).
  - [x] 1.3 Write `_write_daily_context(cursor, trade_date)` — queries `market_daily_summary` from datalake_query.db for regime/direction/VIX/SPY, gets universe size from `get_symbols_klmn800()`, reads news API budget from Alpha Vantage tracker, reads `symbols_with_data` from FM session data.
  - [x] 1.4 Write `_write_op_performance(cursor, trade_date, results)` — extracts morning and evening OP return dicts from `results` dict. Maps nested collection/rollup/timing/health sub-dicts to table columns. Handles missing runs gracefully (skipped steps = no row).
  - [x] 1.5 Write `_write_ei_performance(cursor, trade_date, results)` — extracts EI return dicts (daily_pipeline, morning_scan, weekly_refresh) from `results`. Maps sub_tasks breakdowns to table columns. NULL columns for non-applicable run type fields.
  - [x] 1.6 Write `_write_fm_tables(cursor, trade_date, fm_session_data, results)` — writes `fm_pre_market_performance` (from results dict), `fm_cycle_performance` (one row per cycle from session stats lists, keyed by scan_timestamp), `fm_post_market_performance` (from results dict).
  - [x] 1.7 Write `_write_sync_performance(cursor, trade_date, sync_entries)` — reads sync_performance list from daily_state.json. Writes both full and quick sync rows. Parses `size_mb` from `size_display` string for full syncs.
  - [x] 1.8 Write subprocess stdout parser functions: `_parse_metadata_stdout(stdout)` returns dict of symbols_processed, quotes_fetched, etc. `_parse_backup_stdout(stdout)` returns dict of backup_size_mb, table_count, size_verified. `_parse_archive_stdout(stdout)` returns dict of per-tier row counts.
  - [x] 1.9 Write `_write_subprocess_tables(cursor, trade_date, results)` — writes `metadata_performance`, `morning_views_performance`, `backup_performance`, `batch_mode_performance`, `airline_play_performance`, `sector_archive_performance` from their respective result dicts. Each result dict should contain a `stdout` field if the step ran as subprocess.
  - [x] 1.10 Verify end-to-end: manually construct a sample `results` dict and call `write_daily_performance()` to confirm all 13 tables get rows with correct types. Check with `direct_db_query.py --db data/performance.db --tables`.

- [x] 2.0 Propagate return dicts through run_*() methods
  - [x] 2.1 Change `run_morning_option_pipeline()` in `main_runners.py`: replace `return True` (line ~318) with `return results` (the OP pipeline dict). Replace `return False` with `return {'success': False, 'error': str(e)}`.
  - [x] 2.2 Change `run_evening_option_pipeline()` similarly — same pattern as morning, returns OP pipeline dict or error dict.
  - [x] 2.3 Change `run_earnings_morning_scan()`: replace `return True` with `return result` (the EI scan dict). Replace `return False` with error dict.
  - [x] 2.4 Change `run_earnings_daily_pipeline()`: replace `return True` with `return result` (the EI daily dict). Replace `return False` with error dict.
  - [x] 2.5 Change `run_earnings_weekly_refresh()`: replace `return True` with `return result` (the EI refresh dict). Replace `return False` with error dict.
  - [x] 2.6 Change `run_flow_monitor()`: currently returns the FM phase return values. Ensure pre-market, market-hours, and post-market dicts are all captured in a combined dict and returned. Structure: `{'success': bool, 'pre_market': dict, 'market_hours': dict, 'post_market': dict}`.
  - [x] 2.7 Change subprocess-based methods to return structured dicts. For each of `run_metadata_collection()`, `run_morning_views()`, `run_database_backup()`, `run_friday_sector_archive()`, `run_airline_play()`: return `{'success': bool, 'duration_seconds': float, 'stdout': str}` (with `stdout` captured from the subprocess result for later parsing by the performance writer). For `run_query_database_sync()`: return `{'success': bool, 'duration_seconds': float, 'stdout': str, 'sync_type': 'full'}`.
  - [x] 2.8 Update `_print_day_summary()` in `main.py` (line ~315) to handle dict results. Currently checks `elif result:` for truthiness. Change to: extract `success = result.get('success', False) if isinstance(result, dict) else bool(result)`. Non-empty dicts are truthy, but explicit extraction is clearer.
  - [x] 2.9 Update `_save_orchestrator_result()` in `main_ui.py` — currently stores the raw result value in daily_state.json. After this change, it will store dicts. `_load_daily_state()` already returns whatever was stored, so it handles dicts naturally. The truthiness check in `main.py` (task 2.8) covers the consumption side.
  - [ ] 2.10 Verify: run a single step (e.g., `python main.py --option-morning`) and confirm: (a) the return dict flows through to `results['1.1 Morning Option Pipeline']`, (b) `_print_day_summary` correctly shows OK/FAILED, (c) `daily_state.json` contains the dict under `orchestrator_results`.

- [x] 3.0 Enrich FMSessionStats with per-cycle tracking fields
  - [x] 3.1 Add `self.scan_timestamps = []` to `__init__()`. In `record_cycle()`, accept `scan_timestamp` in the `timings` dict and append it: `self.scan_timestamps.append(timings.get('scan_timestamp', ''))`. This becomes the PK for `fm_cycle_performance`.
  - [x] 3.2 Add `self.contracts_collected = []` and `self.alerts_generated = []` to `__init__()`. In `record_cycle()`, append from timings dict: `self.contracts_collected.append(timings.get('contracts_collected', 0))` and same for alerts.
  - [x] 3.3 Add `self.symbols_attempted = []` and `self.symbols_with_data = []` to `__init__()`. In `record_cycle()`, append from timings dict.
  - [x] 3.4 Update `save_to_daily_state()` to include the 5 new lists in the dict passed to `_save_fm_session()`: `scan_timestamps`, `contracts_collected`, `alerts_generated`, `symbols_attempted`, `symbols_with_data`.
  - [x] 3.5 Update `load_from_daily_state()` to restore the 5 new lists (with `[]` defaults) so mid-day restarts preserve them.
  - [x] 3.6 Update `get_summary()` to include new fields in the timing sub-dict (totals/averages as appropriate).
  - [x] 3.7 Wire `fm_main.py` cycle loop: in the timings dict passed to `session_stats.record_cycle()`, add `scan_timestamp` (from the collector's scan timestamp), `contracts_collected` (from collector stats), `alerts_generated` (from alert phase), `symbols_attempted` (symbols sent to API), `symbols_with_data` (symbols that returned data). Also added `last_contracts_collected` and `last_symbols_with_data` attributes to `fm_collector.py`.

- [x] 4.0 Deprecate FMPerformanceTracker
  - [x] 4.1 In `fm_main.py`, remove the `performance_tracker.track_cycle_performance(...)` call (line ~1409) and the `performance_tracker.track_error(...)` call (line ~1417).
  - [x] 4.2 Remove both `performance_tracker = FMPerformanceTracker()` instantiations in `fm_main.py` (lines ~1102 and ~1537).
  - [x] 4.3 Remove the `from strategies.flow_monitor.fm_performance_tracker import FMPerformanceTracker` import in `fm_main.py` (line ~38). Also removed `performance_tracker` parameter from 5 function signatures and 5 call sites.
  - [x] 4.4 Moved `fm_performance_tracker.py` to `strategies/flow_monitor/Deprecated/`. Added deprecation notice.
  - [x] 4.5 Verified `fm_health_reporter.py` has zero references. Import test passed.

- [x] 5.0 Add Phase 6: System Maintenance to orchestrator
  - [x] 5.1 In `main.py`, after the Phase 5 block, added Phase 6 with `self.phase_header("SYSTEM MAINTENANCE", phase_number=6)` and performance collection step with timing wrapper.
  - [x] 5.2 Created `run_performance_collection()` in `main_runners.py`. Imports ensure_schema + write_daily_performance, reads daily_state.json for FM session + sync data, writes all tables, returns `{'success': bool, 'rows_written': int}`. Never crashes (try/except wraps everything).
  - [x] 5.3 Updated `print_banner()` in `main_ui.py` — Phase 6: System Maintenance / 6.1 Performance Data Collection shows on all days.
  - [x] 5.4 Added 'Performance Collection' to `STEP_SEQUENCE` in `main.py`.
  - [x] 5.5 Verified: `_print_day_summary()` iterates `results.items()` — Phase 6 result included automatically.
  - [x] 5.6 Moved `_print_day_summary()` call to AFTER Phase 6 block.

- [x] 6.0 Autofix integration and documentation
  - [x] 6.1 Added `'performance_db': 'data/performance.db'` to all 22 `queue_error()`/`handle_error()` context dicts in `main_runners.py`. 3 calls that passed `context=result` converted to `{**result, 'performance_db': ...}`.
  - [x] 6.2 Added `'health_status'` to both OP pipeline failure `handle_error()` calls (morning + evening).
  - [x] 6.3 Added "Performance Database" section to `AUTOFIX_CHEAT_SHEET.md` with 13-table summary and 10 diagnostic queries.
  - [x] 6.4 Updated schema doc status to "Active — implemented 2026-02-23".
