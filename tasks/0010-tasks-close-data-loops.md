# Phase 3: Close the Data Loops

**Created:** 2026-02-26
**Origin:** Earnings Intelligence refactor — `docs/earnings_strategy_refactor/REFACTOR_PLAN.md` (Phase 3)
**Research:** `docs/earnings_strategy_refactor/RESEARCH_AND_FINDINGS.md` (Sessions 4-6)
**Dependencies:** Phase 0 (complete). Benefits from snapshots accumulating (started 2026-02-25).

---

## Summary

The Earnings Intelligence system has structural gaps that leave critical analytical columns permanently NULL. All 9,324 rows in `earnings_moves` have NULL price moves (`move_1day_pct`, `move_3day_pct`, `move_vs_expected_pct`, `move_direction`) because the calculation depends on `earnings_snapshots` which was empty until Session 6 fixed it (2026-02-25). Signal data (`earnings_play_signal`, `relative_underpricing_pct`) is lost during the Friday archive from `earnings_upcoming` → `earnings_events`. And `earnings_moves` lacks its own `earnings_date` column, requiring a JOIN to `earnings_events` — which is problematic because most `earnings_events` rows are archived to sector databases.

This phase adds fallback calculations, denormalizes key columns, preserves signal data during archival, and backfills historical gaps.

## Key Design Decisions

| Decision | Answer | Rationale |
|----------|--------|-----------|
| Snapshots vs historical_prices | **Snapshots = primary (long-term), historical_prices = fallback** | Snapshots capture IV data at specific points relative to earnings — richer than historical_prices. But snapshots just started accumulating (2026-02-25), so the fallback handles the gap period and the 9,324 historical rows. |
| Deprecate earnings_snapshots? | **No** | The table is correctly designed and the collector was just fixed. It will be the primary data source once enough data accumulates (~2 weeks). The fallback is insurance, not a replacement. |
| Backfill historical rows? | **Yes, full backfill including cross-archive queries** | 9,324 rows with all-NULL price moves is a real data integrity gap. The value for backtesting is significant. Use airlines.db as test target, then all sector archives. |
| Denormalization backfill scope | **Production + sector archives** | `earnings_moves` has 9,324 rows with `event_id` → `earnings_events`. Only 177 events in production, ~9,147 archived to sector DBs. Must query archives to backfill `earnings_date`. |
| Signal columns on earnings_events | **5 columns**: earnings_play_signal, relative_underpricing_pct, expected_move_pct, straddle_expected_move_pct, historical_avg_move_pct | Preserves the system's pre-earnings recommendation for backtesting. "Was the STRONG BUY signal accurate?" Currently this data is permanently lost during archival. |
| Bonus earnings_events columns | **2 columns**: eps_estimate, revenue_estimate | Piggybacked on Phase 2 — Finnhub provides these during Friday refresh. Archive query copies them to `earnings_events`. Adds context for future analysis. |
| Snapshot wiring changes | **Likely no code changes needed** — verify after data accumulates | Session 6 fixed the collector. The existing lookup uses `(event_id, symbol, is_primary_symbol)` which works. Just need to verify data is flowing correctly. |

## Current State of `earnings_moves` (9,324 rows)

| Column | Status | Why |
|--------|--------|-----|
| `move_1day_pct` | **ALL NULL** | `_calculate_price_moves()` queries empty `earnings_snapshots` |
| `move_2day_pct` | **ALL NULL** | Same |
| `move_3day_pct` | **ALL NULL** | Same — **blocks Phase 1 T+3 `actual_move_pct` on earnings_watchlist** |
| `move_5day_pct` | **ALL NULL** | Same |
| `max_intraday_move_pct` | **ALL NULL** | Same |
| `move_direction` | **ALL NULL** | Derived from `move_1day_pct` |
| `move_vs_expected_pct` | **ALL NULL** | Formula needs non-NULL `move_1day_pct` (line 182-186) |
| `iv_buildup_pct` | Populated | `_get_iv_from_option_summary()` fallback works |
| `iv_collapse_pct` | Populated | Same fallback |
| `iv_crush_severity` | Populated | Same fallback |
| `expected_move_pct` | Populated | `_get_expected_move_at_earnings()` works directly |
| `earnings_date` | **DOES NOT EXIST** | Must denormalize from `earnings_events` |

## Relevant Files

- `strategies/earnings_intel/ei_post_earnings_calc.py` — Primary target. Add `_get_price_moves_from_historical()` fallback (parallels existing `_get_iv_from_option_summary()`). Add `earnings_date` to INSERT. Lines 220-266 (`_calculate_price_moves`), lines 335-430 (`_get_iv_from_option_summary` — pattern reference), lines 477-503 (INSERT statement).
- `strategies/earnings_intel/ei_main.py` — Update archive query (lines 132-142) to include signal columns in SELECT from `earnings_upcoming`.
- `strategies/earnings_intel/ei_backfill_metrics.py` — Existing backfill script, pattern reference for the new migration script.
- `data/sector_archive/` — Sector archive databases for cross-archive backfill. Airlines.db = test target.
- `data/datalake_schema_2026-01-01.md` — Schema reference for `earnings_moves`, `earnings_events`, `historical_prices`.

### Notes

- `historical_prices` has daily OHLC data. For price moves, we need `close_price` at specific days relative to `earnings_date`. The query is straightforward: `SELECT close_price FROM historical_prices WHERE symbol=? AND trade_date=? ORDER BY trade_date DESC LIMIT 1` for each day offset.
- The fallback mirrors the existing IV fallback pattern: `_calculate_price_moves()` returns empty → try `_get_price_moves_from_historical()` → if that's also empty, columns stay NULL.
- Phase 1's `ei_watchlist.py` pulls `earnings_moves.move_3day_pct` for T+3 `actual_move_pct`. Once Task 1 is done and the pipeline runs, this column will be populated for new events. The backfill (Task 5) handles historical rows.
- The archive query at `ei_main.py:132-142` uses `INSERT OR IGNORE` — existing rows won't be updated. The new signal columns will only be populated for events archived AFTER this change.
- `max_intraday_move_pct` requires intraday data that `historical_prices` doesn't have (only daily OHLC). The fallback can approximate it as `max(high - open, open - low) / open * 100` from OHLC, or leave it NULL. Discuss with implementer.

## Tasks

- [x] 1.0 Price Moves Fallback in `ei_post_earnings_calc.py`
  - [x] 1.1 Implement `_get_price_moves_from_historical()` — queries historical_prices for T0, T+1, T+2, T+3, T+5 close prices. Uses `trade_date >= ?` for on-or-after lookups (handles weekends/holidays).
  - [x] 1.2 Calculate moves, direction, max_intraday (approximated from T+1 OHLC). Also includes move_5day_pct (was missing from original INSERT).
  - [x] 1.3 Returns dict matching `_calculate_price_moves()` format.
  - [x] 1.4 Integrated into `_calculate_event_metrics()` — snapshots primary, historical_prices fallback. Logs which path was used.
  - [x] 1.5 `move_vs_expected_pct` formula fires automatically when `move_1day_pct` is populated. Confirmed — 28 rows now have it (the 28 events with `expected_move_pct` data from Feb 10 recalibration).

- [x] 2.0 Denormalize `earnings_date` onto `earnings_moves`
  - [x] 2.1 ALTER TABLE + `_migrate_earnings_moves_schema()` runs on PostEarningsCalculator init.
  - [x] 2.2 INSERT updated to include earnings_date (+ move_5day_pct which was previously missing).
  - [x] 2.3 Index `idx_em_earnings_date` created.

- [x] 3.0 Archive Signal Data to `earnings_events`
  - [x] 3.1 `_migrate_earnings_events_schema()` adds 7 columns (idempotent). Called before archive query.
  - [x] 3.2 Archive query updated with all 7 columns in both INSERT and SELECT.
  - [x] 3.3 INSERT OR IGNORE confirmed — existing 177 rows keep NULLs. Signal data only for future archives.

- [x] 4.0 Backfill Migration Script
  - [x] 4.1 Created `ei_backfill_price_moves.py` with --dry-run, --pass, --verbose options.
  - [x] 4.2 Pass 1: 32 rows updated from production earnings_events.
  - [x] 4.3 Pass 2: 9,290 rows updated from 15 sector archives. All sectors had earnings_events tables. Only 2 orphaned rows remain.
  - [x] 4.4 Pass 3: 74 rows got price moves from historical_prices. 0 had insufficient data. Also computed move_vs_expected_pct where expected_move_pct was available.
  - [x] 4.5 Validation: earnings_date 0%→100%, move_1day_pct 99.2%→100%, move_5day_pct 99.2%→100%, move_direction 99.2%→100%, move_vs_expected_pct 0%→0.3% (28 rows, limited by expected_move_pct availability).

- [ ] 5.0 Verify Snapshot Wiring — DEFERRED (~2 weeks after 2026-02-25)
  - [ ] 5.1 Check earnings_snapshots accumulation after 1-2 weeks of pipeline runs.
  - [ ] 5.2 Verify primary path (snapshots) fires for T+3 events with snapshot data.
  - [ ] 5.3 Document verification results.
