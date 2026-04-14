# Return Dict Contract Specification — All Strategies

**Date:** 2026-02-17
**Purpose:** Map the data flow at every boundary for all strategies called by the orchestrator (`main_runners.py`). For each `run_*()` method: what the completion box displays, where it gets each value, what the strategy actually returns today, what the components return, and what the return dict contract should be.

**Scope:** Research and documentation only — no code changes proposed.

**Related docs:**
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md` — the target architecture
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_AUDIT.md` — violation inventory

---

## Table of Contents

1. [Earnings Intelligence](#1-earnings-intelligence) (3 methods, full depth)
2. [Option Pipeline](#2-option-pipeline) (2 methods, full depth)
3. [Flow Monitor](#3-flow-monitor) (1 method wrapping 3 phases, full depth)
4. [Utility Runners](#4-utility-runners) (8 methods, light coverage)
5. [Cross-Cutting Issues](#5-cross-cutting-issues)

---

# 1. Earnings Intelligence

The EI strategy has **3 orchestrator methods** in `main_runners.py` that call **3 coordinator functions** in `ei_main.py`, which call **5 component modules**. A 4th coordinator (`run_all_mode`) is CLI-only and doesn't participate in orchestrator data flow.

```
main_runners.py                    ei_main.py                     Component modules
─────────────────                  ──────────                     ─────────────────
run_earnings_pipeline()      →     run_daily_pipeline()     →     SnapshotCollector.collect_daily_snapshots()
                                                                  PostEarningsCalculator.calculate_post_earnings_metrics()
                                                                  update_expected_moves()

run_earnings_morning_scan()  →     run_morning_scan()       →     ArbitrageScanner.scan_morning_opportunities()

run_earnings_weekly_refresh()→     run_weekly_refresh()     →     EarningsFetcher.fetch_upcoming_earnings()
                                                                  (archive + cleanup are inline SQL in ei_main.py)
```

**The core problem:** All 3 coordinator functions return `bool`. The component modules already return rich dicts that the coordinator discards. The orchestrator compensates by querying the database directly — the exact anti-pattern the standard prohibits.

---

## 1.1 run_earnings_pipeline() — Daily Pipeline (5:00 PM)

### Orchestrator side (main_runners.py)

**Completion box currently displays (on success):**
| Field | Source |
|-------|--------|
| Snapshots collected today | DB query: `SELECT COUNT(*) FROM earnings_snapshots WHERE DATE(created_at) = DATE('now')` |
| Moves calculated today | DB query: `SELECT COUNT(*) FROM earnings_moves WHERE DATE(calculated_at) = DATE('now')` |
| Earnings alerts count | DB query: `SELECT COUNT(*) FROM earnings_upcoming WHERE earnings_alert = 1` |
| Alert signal breakdown | DB query: `SELECT symbol, earnings_days_ahead, relative_underpricing_pct, earnings_play_signal FROM earnings_upcoming WHERE earnings_alert = 1` |
| Top alert symbols (up to 5) | Same DB query, formatted with days-ahead and underpricing % |
| Status line | Hardcoded: "Full pipeline successful" |

**All 6 values come from DB queries.** Zero values come from the strategy return.

**Violations:** `beautiful_log("Initializing...")`, `beautiful_log("Starting...")`, `print("Running...")`, `beautiful_log("SUCCESS")`, 3 DB queries for completion box data.

**What the orchestrator receives:** `bool` from `run_daily_pipeline()`.

**Autofix integration:** `queue_error()` in except block with bare `{'exception_type': ..., 'error_message': ...}`. Strategy return dict not available.

### Coordinator side (ei_main.py)

**Returns:** `bool` (True/False)

**What it knows but discards:**

| Local variable | Component call |
|---------------|----------------|
| `snapshot_results` | `collector.collect_daily_snapshots()` |
| `calc_results` | `calculator.calculate_post_earnings_metrics()` |
| `moves_results` | `update_expected_moves()` |

Also tracks timing per sub-task and per-task success booleans.

**Autofix issue:** Calls `handle_error()` directly on each sub-task failure.

### Component return dicts

**`SnapshotCollector.collect_daily_snapshots()`** (ei_snapshot_collector.py)
```python
{
    'trade_date': str | None,       # YYYY-MM-DD, None if no trade date
    'events_in_window': int,        # earnings events in T-7 to T+3 window
    'symbols_processed': int,       # events processed
    'snapshots_created': int,       # successfully created
    'snapshots_skipped': int,       # skipped (missing data)
    'errors': int                   # error count
}
```

**`PostEarningsCalculator.calculate_post_earnings_metrics()`** (ei_post_earnings_calc.py)
```python
{
    'trade_date': str | None,       # YYYY-MM-DD, None if no trade date
    'events_ready': int,            # events at T+3 ready for calculation
    'moves_calculated': int,        # successfully calculated moves
    'sector_effects_calculated': int, # peer sector effect records
    'errors': int                   # error count
}
```

**`update_expected_moves()`** (ei_moves_upcoming.py)
```python
{
    'processed': int,               # symbols successfully processed
    'failed': int,                  # symbols that failed
    'alerts': int                   # earnings alerts triggered
}
```
Note: Only component without an `errors` field (uses `failed`). Also lacks `trade_date`.

### Proposed contract

`ei_main.run_daily_pipeline()` returns:
```python
{
    'success': bool,
    'duration_seconds': float,
    'errors': int,                  # sum of sub-task errors
    'failed_symbols': list,         # aggregated (GAP: not currently tracked)
    'sub_tasks': {
        'snapshots': {
            'success': bool,
            'duration_seconds': float,
            'trade_date': str | None,
            'events_in_window': int,
            'symbols_processed': int,
            'snapshots_created': int,
            'snapshots_skipped': int,
            'errors': int,
        },
        'calculations': {
            'success': bool,
            'duration_seconds': float,
            'trade_date': str | None,
            'events_ready': int,
            'moves_calculated': int,
            'sector_effects_calculated': int,
            'errors': int,
        },
        'expected_moves': {
            'success': bool,
            'duration_seconds': float,
            'processed': int,
            'failed': int,
            'alerts': int,
        },
    },
    # Orchestrator-facing summary fields (derived from sub_tasks):
    'snapshots_created': int,
    'moves_calculated': int,
    'alerts_triggered': int,
}
```

### Gap: Alert details not available from component return

The orchestrator currently queries the DB for per-alert details (symbol, days ahead, signal, underpricing %). `update_expected_moves()` only returns `{'alerts': int}`.

**Recommendation:** Expand `update_expected_moves()` to include:
```python
'alert_details': [
    {'symbol': 'TOST', 'days_ahead': 3, 'relative_underpricing_pct': 45.2, 'signal': 'BUY'},
    ...
]
```
The data is already computed in the function's processing loop.

### Bug: `events_analyzed` vs `events_ready` naming

`PostEarningsCalculator` returns `events_ready` but the coordinator references `events_analyzed`. The `.get('events_analyzed', 0)` on the component dict returns 0 — the key doesn't exist. **Silent bug:** health reporter always gets 0 for this field.

---

## 1.2 run_earnings_morning_scan() — Morning Arbitrage (6:30 AM)

### Orchestrator side (main_runners.py)

**Completion box currently displays:**
| Field | Source |
|-------|--------|
| Opportunities found | DB query on `earnings_sector_effects` |
| High-quality plays | DB query with `arbitrage_quality = 'HIGH'` |
| Status line | Hardcoded: "Scan successful" |

**All values from DB queries.** Violations: 4 duplicate announcements.

**What the orchestrator receives:** `bool` from `run_morning_scan()`.

### Coordinator side (ei_main.py)

**Returns:** `bool` (True/False). Captures `scan_results` from scanner, logs it, discards it.

### Component return dict

**`ArbitrageScanner.scan_morning_opportunities()`** (ei_arbitrage_scanner.py)
```python
{
    'scan_date': str,               # YYYY-MM-DD
    'earnings_today': int,          # earnings events for scan date
    'opportunities_found': int,     # total opportunities
    'high_quality': int,            # score > 40
    'medium_quality': int,          # score 20-40
    'low_quality': int,             # score <= 20
    'persisted': int,               # records inserted into earnings_sector_effects
    'errors': int                   # error count
}
```
**Richest component return dict in EI.** Already has everything the orchestrator needs and more.

### Proposed contract

`ei_main.run_morning_scan()` returns:
```python
{
    'success': bool,
    'duration_seconds': float,
    'errors': int,
    'failed_symbols': list,         # GAP: not currently tracked, minor
    # Single sub-task — flatten scanner results directly:
    'scan_date': str,
    'earnings_today': int,
    'opportunities_found': int,
    'high_quality': int,
    'medium_quality': int,
    'low_quality': int,
    'persisted': int,
}
```

**Difficulty: Easiest.** Component already returns everything. Coordinator just passes it through.

---

## 1.3 run_earnings_weekly_refresh() — Weekly Refresh (Fridays)

### Orchestrator side (main_runners.py)

**Completion box currently displays:**
| Field | Source |
|-------|--------|
| Upcoming earnings | DB query: `SELECT COUNT(*) FROM earnings_upcoming WHERE earnings_date >= DATE('now')` |
| Archived events | DB query: `SELECT COUNT(*) FROM earnings_events` (total all-time!) |
| Status line | Hardcoded: "Calendar refreshed for coming week" |

**Data accuracy issue:** "Archived events" shows total all-time count, not events archived this run.

**What the orchestrator receives:** `bool` from `run_weekly_refresh()`.

### Coordinator side (ei_main.py)

**Returns:** `bool`. Only Task 1 (fetch) calls an external component. Tasks 2-3 are inline SQL with rowcounts captured in local variables (`archived_count`, `cleanup_count`) then discarded.

**Autofix issue:** 4 `handle_error()` calls (fetch=ERROR, archive=CRITICAL, cleanup=ERROR, outer=CRITICAL).

### Component return dict

**`EarningsFetcher.fetch_upcoming_earnings()`** (ei_fetch_upcoming.py)
```python
{
    'symbols_processed': int,       # total symbols processed
    'earnings_found': int,          # symbols with earnings data
    'new_insertions': int,          # records inserted/updated
    'past_cleaned': int,            # past records deleted
    'errors': int                   # error count
}
```

### Proposed contract

`ei_main.run_weekly_refresh()` returns:
```python
{
    'success': bool,
    'duration_seconds': float,
    'errors': int,
    'failed_symbols': list,         # GAP: not currently tracked
    'sub_tasks': {
        'fetch': {
            'success': bool,
            'duration_seconds': float,
            'symbols_processed': int,
            'earnings_found': int,
            'new_insertions': int,
            'past_cleaned': int,
            'errors': int,
        },
        'archive': {
            'success': bool,
            'duration_seconds': float,
            'events_archived': int,  # cursor.rowcount from INSERT
        },
        'cleanup': {
            'success': bool,
            'duration_seconds': float,
            'records_deleted': int,  # cursor.rowcount from DELETE
        },
    },
    # Orchestrator-facing summary:
    'earnings_found': int,
    'events_archived': int,
    'records_cleaned': int,
    'upcoming_count': int,           # GAP: requires post-task count query
}
```

### Gap: `upcoming_count`

No component returns this. **Recommendation:** Coordinator queries it once after all tasks complete. Cheap count query, coordinator is the right place since it just modified the table.

### EI Cross-Cutting Issues

**Autofix calls inside coordinator:** 9 total `handle_error()` calls across all 3 coordinator functions (4 in run_weekly_refresh, 4 in run_daily_pipeline, 1 in run_morning_scan). A 10th exists in run_all_mode (CLI-only). Per standard, should all route through orchestrator via return dict.

**Visual output from coordinator:** Phase headers, tree diagrams, `[1/3]` lines, success celebrations, error boxes. Per standard, coordinators produce zero visual output. The 8 formatting functions in ei_main.py should be deleted.

**Health reporter and diagnostic logger:** Internal concerns, no impact on orchestrator data flow.

---

# 2. Option Pipeline

The OP strategy has **2 orchestrator methods** (morning and evening) that both call the same coordinator function `OPOrchestrator.run_pipeline()`, which sequences 4 phases.

```
main_runners.py                    op_main.py                     Component modules
─────────────────                  ──────────                     ─────────────────
run_morning_option_pipeline()  →   run_pipeline()           →     OIDCollector.collect_daily_oi()
run_evening_option_pipeline()  →     (same function)              OIDSymbolRollup.process_symbols()
                                                                  OITimingCalculator.process_date()
                                                                  _generate_health_report()
```

**Key difference from EI:** OP already returns a comprehensive dict. The orchestrator already reads from it. The problem is the strategy *also* displays its own visual output (banners, celebrations, phase headers).

---

## 2.1 run_morning_option_pipeline()

### Orchestrator side

**Completion box currently displays (on success):**
| Field | Source |
|-------|--------|
| Trade Date | Local variable `trade_date` |
| Symbols Collected | `results['collection']['symbols_collected']` |
| Total Contracts | `results['collection']['total_contracts']` |
| Symbol Summaries | `results['rollup']['summaries_created']` |
| OI Timing Calculated | `results['timing']['contracts_updated']` |
| Status line | Hardcoded: "Complete pipeline executed" |

**All values come from the return dict.** This is the correct pattern.

**Violations:** `beautiful_log("Initializing...")`, `beautiful_log("Beginning...")`, `beautiful_log("completed successfully")`.

**What the orchestrator receives:** `dict` from `op.run_pipeline()`.

**Autofix:** On `success: False`, passes the full results dict to `handle_error()`. This is actually good -- richer context than bare exception strings.

### Coordinator side (op_main.py, `run_pipeline()`)

**Returns:** `dict` via `_finalize_results()`:
```python
{
    'success': bool,
    'message': str,
    'completion_time': str,          # ISO format
    'start_time': float,             # unix timestamp
    'total_execution_time': float,   # seconds
    'errors': list,                  # list of error strings
    'collection': {                  # from _run_collection_phase()
        'success': bool,
        'execution_time': float,
        'symbols_collected': int,
        'symbols_failed': int,
        'failed_symbols': list,
        'total_contracts': int,
        'api_calls': int,
    },
    'analysis': {                    # deprecated — always {'success': True, 'skipped': True, ...}
        'success': True,
        'skipped': True,
        'reason': str,
    },
    'rollup': {                      # from _run_rollup_phase()
        'success': bool,
        'execution_time': float,
        'symbols_processed': int,
        'symbols_with_data': int,
        'summaries_created': int,
    },
    'timing': {                      # from _run_timing_phase()
        'success': bool,
        'execution_time': float,
        'contracts_processed': int,
        'contracts_updated': int,
        'contracts_skipped': int,
    },
    'health': dict,                  # health report results
}
```

**This is the best return dict in the system.** Comprehensive, well-structured, and the orchestrator actually uses it.

### Component return dicts (one level deeper)

**`OIDCollector.collect_daily_oi()`** — Returns `bool`, not dict. Stats accessed via `collector.collection_stats` attribute:
```python
{
    'total_symbols': int,
    'processed_symbols': int,
    'successful_symbols': int,
    'failed_symbols': int,
    'failed_symbol_list': list,
    'total_contracts': int,
    'api_calls_made': int,
    'start_time': float,
}
```
The coordinator wraps this into the `collection` sub-dict with normalized field names.

**`OIDSymbolRollup.process_symbols()`** — Returns `dict`:
```python
{
    'total_symbols': int,
    'symbols_processed': int,
    'symbols_with_data': int,
    'symbols_skipped_no_data': int,
    'summaries_created': int,
    'processing_time_per_batch': list,
    'total_processing_duration': float,
    'errors_encountered': int,
    'failed_symbols': list,
}
```

**`OITimingCalculator.process_date()`** — Returns `dict`:
```python
{
    'total': int,                    # contracts with OI > 1000
    'updated': int,                  # contracts updated with timing data
    'skipped': int,                  # insufficient data
}
```

### Proposed contract

**The existing return dict is already close to the target.** Minor adjustments needed:

```python
# Add to top level:
'duration_seconds': float,           # alias for total_execution_time (standard naming)

# Collection sub-dict already has failed_symbols list — good

# Rollup sub-dict: add failed_symbols and errors
'rollup': {
    ...existing fields...,
    'failed_symbols': list,          # from component's failed_symbols
    'errors': int,                   # from component's errors_encountered
}
```

**What needs to change:** Mostly visual output cleanup. The data flow is already correct. Strategy-side formatting functions (`safe_log`, `create_phase_header`, `create_progress_box`, `create_success_celebration`, `create_error_box`, `log_pipeline_start`) in op_main.py should be removed. The component banners in op_collector.py, op_symbol_rollup.py, and op_timing_calculator.py should also go.

---

## 2.2 run_evening_option_pipeline()

**Structurally identical to morning.** Calls the same `op.run_pipeline()`. Completion box reads the same fields from the same return dict.

**One difference:** The evening box includes `rollup.summaries_created` unconditionally, while morning conditionally includes it. Both should use the same logic.

**No separate contract needed.** Same return dict, same data flow.

---

# 3. Flow Monitor

FM is architecturally the most complex. The orchestrator method `run_flow_monitor()` wraps **3 phases** that run over ~8 hours, each with different output characteristics.

```
main_runners.py                    fm_main.py                     Component modules
─────────────────                  ──────────                     ─────────────────
run_flow_monitor()           →     run_pre_market()         →     fm_alert_resolver.resolve_yesterday_alerts()
                                                                  fm_alert_resolver.update_watchlist_sentiment()

                                   run_market_hours()        →     fm_collector.run_once() [per cycle]
                                     (delegated orchestrator)      fm_analyzer.analyze() [per cycle]
                                                                  fm_alerts.process_alerts() [per cycle]
                                                                  fm_watchlist.update_daily_watchlist() [per cycle]
                                                                  news_sentiment.enrich_watchlist_batch() [per cycle]
                                                                  fm_watchlist.update_prices_and_detect() [per cycle]
                                                                  run_quick_sync() [periodic]
                                                                  FMSessionStats.get_summary() [end of session]

                                   run_post_market()         →     run_historical_backfill()
                                     (coordinator)                 run_evening_market_regime_summary()
                                                                  run_symbol_rollup_task()
                                                                  run_daily_evaluation_task()
                                                                  fm_watchlist.archive_expired_entries()
```

**The core problem:** `run_pre_market()` and `run_post_market()` return `bool`. `run_market_hours()` returns a `dict` (the only FM function that does). `fm_main.py` is effectively a second orchestrator with 96 `beautiful_log()` calls, its own formatting functions, and full visual control.

---

## 3.1 run_flow_monitor() — Orchestrator wrapper (main_runners.py)

### Orchestrator side

**Completion box currently displays (on success):**
| Field | Source |
|-------|--------|
| Pre-Market status | Local bool `pre_market_success` |
| Market Hours status | Hardcoded "Completed" |
| Post-Market status | Local bool `post_market_success` |
| "Daily Cycle: Successfully finished" | Hardcoded |
| "System ready for evening operations" | Hardcoded |

**Mostly hardcoded text.** The completion box shows success/failure flags but no metrics. The real metrics display happens in `_display_session_summary()`, which reads from the `session_stats` dict returned by `run_market_hours()`.

**Session summary box (separate from completion box) displays:**
| Field | Source |
|-------|--------|
| Cycles (total, successful, failed) | `session_stats['total_cycles']`, `successful_cycles`, `failed_cycles` |
| Timing (avg, fastest, slowest) | `session_stats['timing']` sub-dict |
| Collection errors by type | `session_stats['errors']['by_type']` |
| Missing quotes (count + always-missing list) | `session_stats['missing_quotes']` |
| Failed options count | `session_stats['failed_options']` |
| News enrichment stats | `session_stats['news_enrichment']` |

**This session summary is correctly built from the return dict** — no DB queries.

**Violations:** `beautiful_log("Initializing...")`. Multiple `beautiful_log()` calls for time-skip logic. News enrichment summary is reasonable operational output.

### What the orchestrator receives

| Phase | Return type | Used for |
|-------|------------|----------|
| `run_pre_market()` | `bool` | Only checked for completion box flag |
| `run_market_hours()` | `dict` | Session summary box + news enrichment display |
| `run_post_market()` | `bool` | Only checked for completion box flag |

---

## 3.2 run_pre_market() — (fm_main.py)

### Current return: `bool`

**What it knows but discards:**

| Local variable | Component call |
|---------------|----------------|
| `resolution_stats` | `fm_alert_resolver.resolve_yesterday_alerts()` |
| `sentiment_stats` | `fm_alert_resolver.update_watchlist_sentiment()` |

### Component return dicts

**`fm_alert_resolver.resolve_yesterday_alerts()`**
```python
{
    'alerts_resolved': int,
    'building': int,                 # BUILDING (opening positions)
    'closing': int,                  # CLOSING (exiting positions)
    'neutral': int,                  # NEUTRAL (churning)
    'not_found': int,                # contracts not in today's OI
}
```

**`fm_alert_resolver.update_watchlist_sentiment()`**
```python
{
    'symbols_updated': int,
}
```

### Proposed contract

`fm_main.run_pre_market()` returns:
```python
{
    'success': bool,
    'duration_seconds': float,
    'sub_tasks': {
        'alert_resolution': {
            'success': bool,
            'alerts_resolved': int,
            'building': int,
            'closing': int,
            'neutral': int,
            'not_found': int,
            'details': list,  # Per-alert dicts: symbol, strike, expiration_date, option_type,
                              # significance_score, resolution, oi_change, alert_count,
                              # alert_date, alert_ul, alert_oi, alert_vol, alert_iv, alert_last,
                              # today_ul, today_oi, today_iv, today_last
        },
        'sentiment_update': {
            'success': bool,
            'symbols_updated': int,
        },
    },
    # Orchestrator-facing summary:
    'alerts_resolved': int,
    'symbols_updated': int,
}
```

---

## 3.3 run_market_hours() — Delegated orchestrator (fm_main.py)

### Current return: `dict` (already correct)

```python
{
    'success': bool,
    'total_cycles': int,
    'news_enrichment': {
        'enriched': int,
        'skipped': int,
        'failed': int,
    },
    'session_stats': {               # from FMSessionStats.get_summary()
        'total_cycles': int,
        'successful_cycles': int,
        'failed_cycles': int,
        'timing': {
            'avg_cycle': float,
            'min_cycle': float,
            'max_cycle': float,
            'avg_collection': float,
            'avg_analysis': float,
            'avg_alert': float,
        },
        'errors': {
            'total': int,
            'by_type': {'timeout': int, 'rate_limit': int, 'connection': int, 'other': int},
            'by_symbol_count': int,
        },
        'missing_quotes': {
            'total_symbols': int,
            'always_missing': list[str],
            'details': dict,
        },
        'failed_options': {
            'total_symbols': int,
            'always_failed': list[str],
            'details': dict,
        },
        'news_enrichment': dict,     # mirrors outer news_enrichment
    },
}
```

**This is already well-structured.** `FMSessionStats` (`fm_session_stats.py`) is called out in the standard as the exemplary model file — computes, aggregates, returns. Provides `format_end_of_day_lines()` that returns strings without printing.

### Per-cycle component chain

Each ~20-minute cycle calls components in sequence:
```
collector.run_once()                     → str (scan_timestamp) or False
analyzer.analyze()                       → dict (16 fields, see below)
alerts.process_alerts()                  → dict (8 fields, see below)
fm_watchlist.update_daily_watchlist()     → dict (4 fields, see below)
enrich_watchlist_batch()                 → dict (3 fields)
fm_watchlist.update_prices_and_detect()  → dict (5 fields)
run_quick_sync()                         → tuple (success, elapsed, rows)
```

**Key component dicts:**

**`fm_analyzer.analyze()`**
```python
{
    'contracts_processed': int,      'contracts_updated': int,
    'missing_baselines': int,        'errors': int,
    'premium_filtered': int,         'volume_filtered': int,
    'smart_money_alerts': int,       'unified_alerts': int,
    'high_conviction': int,          'early_day_fallbacks': int,
    'running_total_used': int,       'missing_price_data': int,
    'bad_tick_data': int,            'data_quality_warnings': int,
    'exceptional_volume_day': int,
}
```

**`fm_alerts.process_alerts()`**
```python
{
    'candidates_found': int,         'alerts_sent': int,
    'console_sent': int,             'email_sent': int,
    'save_failures': int,            'social_queued': int,
    'etf_filtered': int,             'delta_filtered': int,
}
```

**`fm_watchlist.update_daily_watchlist()`**
```python
{
    'entries_created': int,
    'entries_updated': int,
    'total_alerts_processed': int,
    'created_symbols': list[str],    # drives news enrichment
}
```

**`fm_watchlist.update_prices_and_detect()`**
```python
{
    'prices_updated': int,           'dips_detected': int,
    'zscore_detections': int,        'fallback_detections': int,
    'missing_rv_count': int,
}
```

### Proposed contract

**No change needed to the return dict.** It's already comprehensive. The work here is visual output cleanup: remove the 96 `beautiful_log()` calls, formatting functions, and celebration blocks from `fm_main.py`. The per-cycle output (delegated orchestrator role) should use `print()` or `logging.info()` only.

---

## 3.4 run_post_market() — Coordinator (fm_main.py)

### Current return: `bool`

**What it knows but discards:**

The coordinator tracks per-task success bools and timing, then returns `tasks_successful == total_tasks`. It also queries the database for diagnostic metrics that it logs but doesn't return.

| Task | Internal function | Returns |
|------|------------------|---------|
| Historical backfill | `run_historical_backfill()` | `bool` |
| Market regime summary | `run_evening_market_regime_summary()` | `bool` |
| Symbol rollup | `run_symbol_rollup_task()` | `bool` |
| Daily evaluation | `run_daily_evaluation_task()` | `bool` |
| Watchlist cleanup | `fm_watchlist.archive_expired_entries()` | `dict` |

**Note:** All 4 internal `run_*()` functions also return `bool`. Only `archive_expired_entries()` returns a dict (with `entries_archived` field).

**Autofix issue:** `run_post_market()` calls `handle_error()` directly after each task failure. The backfill failure is marked `CRITICAL`.

**DB queries for diagnostic logging:** After each task succeeds, `run_post_market()` queries the database for diagnostic counts (regime classification, rollup symbols/alerts, evaluation scans). These are for the diagnostic log only, not the completion box.

### Component return dicts (inner functions)

**`run_historical_backfill()`** — Returns `bool`. Wraps `fm_backfill_handler.run_daily_backfill()` which likely returns stats but they're discarded. Would need deeper trace.

**`run_evening_market_regime_summary()`** — Returns `bool`. Runs a subprocess (`fm_market_regime_summary.py`). Exit code only.

**`run_symbol_rollup_task()`** — Returns `bool`. Calls `fm_symbol_rollup.run_daily_rollup()`. Return value discarded.

**`run_daily_evaluation_task()`** — Returns `bool`. Calls `fm_daily_evaluation.run_daily_evaluation()`. Return value discarded.

**`fm_watchlist.archive_expired_entries()`** — Returns `dict`:
```python
{
    'entries_archived': int,
}
```

### Proposed contract

`fm_main.run_post_market()` returns:
```python
{
    'success': bool,
    'duration_seconds': float,
    'tasks_successful': int,
    'tasks_total': int,
    'errors': int,
    'sub_tasks': {
        'backfill': {
            'success': bool,
            'duration_seconds': float,
            # GAP: inner function returns bool, no metrics available
            # Would need run_historical_backfill() to return dict
        },
        'market_regime': {
            'success': bool,
            'duration_seconds': float,
            # GAP: subprocess, exit code only
        },
        'symbol_rollup': {
            'success': bool,
            'duration_seconds': float,
            # GAP: inner function returns bool
        },
        'evaluation': {
            'success': bool,
            'duration_seconds': float,
            # GAP: inner function returns bool
        },
        'watchlist_cleanup': {
            'success': bool,
            'duration_seconds': float,
            'entries_archived': int,
        },
    },
}
```

### Gaps: Post-market sub-tasks all return bool

This is the deepest gap in FM. Four of five post-market sub-tasks return `bool`, and the internal functions they call likely return useful data that's discarded at two levels. The `run_post_market()` coordinator also queries the DB for diagnostic metrics (regime classification, rollup counts, evaluation scans) that should come from return dicts instead.

**Recommendation:** Converting the 4 inner `run_*()` wrappers from bool→dict is prerequisite work. Each wraps a component that likely already computes the needed metrics. Trace those components when implementation begins.

---

# 4. Utility Runners

These are simpler methods. Most run subprocesses or single operations. Light coverage — one paragraph each with proposed contract.

---

## 4.1 run_morning_views()

**Current state:** Runs `morning_view/morning_views.py --email` as a subprocess with output suppressed. Completion box is hardcoded ("Views created: 4 SQL views"). Returns `bool`.

**Proposed contract:**
```python
{
    'success': bool,
    'duration_seconds': float,
    # Subprocess — can't return dict through process boundary.
    # Completion box can only show success/fail + duration.
}
```
**Note:** This is a subprocess exception per the standard. Unless the script is converted to in-process, the orchestrator can only show exit code status.

---

## 4.2 run_metadata_collection()

**Current state:** Runs `data/symbol_metadata.py --no-interaction` via `subprocess.run()`. Completion box is hardcoded ("All ~750 symbols updated"). Returns `bool`.

**Proposed contract:**
```python
{
    'success': bool,
    'duration_seconds': float,
    # Subprocess — exit code only.
}
```

---

## 4.3 run_airline_play_phase()

**Current state:** Calls `ap_symbol_tracking.run_symbol_tracking()` and `ap_options_tracking.run_options_tracking()` in-process. Both already return dicts. Completion box already reads from them. **This method is nearly compliant.**

**Component return dicts:**

**`ap_symbol_tracking.run_symbol_tracking()`**
```python
{
    'trade_date': str,
    'symbols_processed': int,
    'symbols_failed': int,
    'elapsed_seconds': float,
}
```

**`ap_options_tracking.run_options_tracking()`**
```python
{
    'trade_date': str,
    'symbols_processed': int,
    'symbols_failed': int,
    'total_contracts_tracked': int,
    'elapsed_seconds': float,
    'results': list,                 # per-symbol results
}
```

**Proposed contract:** Wrap both results:
```python
{
    'success': bool,
    'duration_seconds': float,
    'errors': int,
    'sub_tasks': {
        'symbol_tracking': {
            'success': bool,
            'symbols_processed': int,
            'symbols_failed': int,
        },
        'options_tracking': {
            'success': bool,
            'symbols_processed': int,
            'total_contracts_tracked': int,
        },
    },
    # Orchestrator-facing:
    'symbols_tracked': int,
    'contracts_tracked': int,
}
```

**Violations to fix:** 4 `beautiful_log` calls. Already minimal.

---

## 4.4 run_database_backup()

**Current state:** Daily backup runs `db_backup.py` as streaming subprocess. Weekly backup copies the daily file via `shutil.copy2()`. Completion box is hardcoded ("Backup completed successfully", filler: "Protection: Database secured", "System: Ready for safe operations"). Returns `bool`.

**Proposed contract:**
```python
{
    'success': bool,
    'duration_seconds': float,
    'backup_type': str,              # 'daily' or 'weekly'
    'target_file': str,              # 'datalake_backup.db' or 'datalake_backup_weekly.db'
    # Subprocess — can't return metrics through process boundary.
}
```

**Violations:** `beautiful_log("SUCCESS")` before completion box. Filler lines in box.

---

## 4.5 run_batch_mode_review()

**Current state:** Calls `get_error_queue()` and `process_error_queue()` from `tools/autofix.py`. Displays an intermediate "ERROR QUEUE" box then a completion box. Returns `bool` (always True unless exception).

**Proposed contract:**
```python
{
    'success': bool,
    'duration_seconds': float,
    'skipped': bool,                 # True if Friday archive running
    'skip_reason': str | None,
    'total_errors': int,
    'unique_errors': int,
    'sessions_spawned': int,
}
```

**Note:** The intermediate "ERROR QUEUE" box is a reasonable information display, not a violation — it shows what's about to be processed before the processing begins.

---

## 4.6 run_query_database_sync()

**Current state:** Runs `db_backup.py --sync --auto` as streaming subprocess. Has complex recovery logic for partial sync files. Handles 4 exit codes (0=success, 2=cancelled, 3=partial, other=error). Completion box includes sync timing parsed from stdout. Returns `bool`.

**Proposed contract:**
```python
{
    'success': bool,
    'duration_seconds': float,
    'partial': bool,                 # True if exit code 3 (copy ok, rename failed)
    'recovered': bool,               # True if partial sync from prior run was recovered
    # Subprocess — limited metrics available.
}
```

**Violations:** `beautiful_log("Starting...")`, `print("Syncing...")`, `beautiful_log("SUCCESS")`. Filler lines in box ("Analysis tools can now safely query fresh data", "System: Ready for analysis operations").

---

## 4.7 run_sector_archive()

**Current state:** Runs `db_archive_sector.py --all-tiers` as streaming subprocess. Completion box is hardcoded ("All tiers processed", "Database: Performance optimized"). Returns `bool`.

**Proposed contract:**
```python
{
    'success': bool,
    'duration_seconds': float,
    # Subprocess — exit code only. Archive script streams its own progress.
}
```

**Violations:** `print("Initializing...")`.

---

## 4.8 run_friday_sector_archive()

**Current state:** Same as `run_sector_archive()` but with `--time-limit` flag and timeout handling. Exit code 124 = timeout (expected behavior, counts as success). Returns `bool`.

**Proposed contract:**
```python
{
    'success': bool,
    'duration_seconds': float,
    'timed_out': bool,               # True if hit Monday 5:45 AM cutoff
    # Subprocess — exit code only.
}
```

**Violations:** `print("Initializing...")`. Double mission box.

---

# 5. Cross-Cutting Issues

## 5.1 Subprocess strategies can't return dicts

6 of 14 `run_*()` methods use subprocesses:
- `run_morning_views()` — Popen
- `run_metadata_collection()` — subprocess.run
- `run_database_backup()` (daily) — `_run_streaming_subprocess()`
- `run_query_database_sync()` — `_run_streaming_subprocess()`
- `run_sector_archive()` — `_run_streaming_subprocess()`
- `run_friday_sector_archive()` — `_run_streaming_subprocess()`

Per the standard, "strategies that run via `_run_streaming_subprocess()` can't return dicts through the process boundary — they return exit codes." These get simple `{success, duration_seconds}` contracts. Their completion boxes can only show what was parsed from stdout or what the orchestrator already knows (file paths, time available, etc.).

## 5.2 Every strategy reinvents beautification

| Function | FM | OP | EI |
|----------|----|----|-----|
| `safe_log()` | Yes | Yes | Yes |
| `colorize()` | Yes | No | Yes |
| `beautiful_log()` | Yes | No | Yes |
| `create_phase_header()` | Yes | Yes | Yes |
| `create_progress_box()` | No | Yes | Yes |
| `create_success_celebration()` | Yes | Yes | Yes |
| `create_error_box()` | Yes | Yes | Yes |

All doing the orchestrator's job. Should be deleted from all strategy files.

## 5.3 Autofix calls scattered across strategies

| File | `handle_error()` calls | `queue_error()` calls |
|------|----------------------|---------------------|
| ei_main.py | 10 (9 in 3 coordinators + 1 in run_all_mode) | 0 |
| op_main.py | 6 | 0 |
| fm_main.py (market hours) | 3 | 1 |
| fm_main.py (post-market) | 4 | 1 |
| main_runners.py | 6 | 16 |

Per the standard: strategies never call autofix directly (except subprocesses). All 23 strategy-side `handle_error()` calls should route through the orchestrator via `success: False` / `severity: 'CRITICAL'` in the return dict.

## 5.4 Duplicate announcement pattern

Every `run_*()` method in main_runners.py follows the same pattern:
1. Mission box (correct)
2. `beautiful_log("Initializing...")` (duplicate)
3. `beautiful_log("Starting/Running...")` (second duplicate)
4. `print("Running...")` (third duplicate)
5. Strategy runs
6. `beautiful_log("SUCCESS")` (duplicate completion)
7. Completion box (correct)

Items 2-4 and 6 should be removed in every case.

## 5.5 Summary of data flow health

| Method | Return type | Box source | Status |
|--------|-----------|------------|--------|
| `run_morning_option_pipeline()` | dict | Return dict | **Good** (visual cleanup only) |
| `run_evening_option_pipeline()` | dict | Return dict | **Good** (visual cleanup only) |
| `run_flow_monitor()` | mixed | Dict (market hours), bools (pre/post) | **Partial** |
| `run_earnings_pipeline()` | bool | DB queries | **Broken** — needs dict |
| `run_earnings_morning_scan()` | bool | DB queries | **Broken** — needs dict (easy fix) |
| `run_earnings_weekly_refresh()` | bool | DB queries | **Broken** — needs dict |
| `run_airline_play_phase()` | bool | Component dicts (correct!) | **Nearly compliant** |
| `run_morning_views()` | bool | Hardcoded | Subprocess |
| `run_metadata_collection()` | bool | Hardcoded | Subprocess |
| `run_database_backup()` | bool | Hardcoded | Subprocess |
| `run_batch_mode_review()` | bool | Autofix API | Moderate |
| `run_query_database_sync()` | bool | Parsed stdout | Subprocess |
| `run_sector_archive()` | bool | Hardcoded | Subprocess |
| `run_friday_sector_archive()` | bool | Hardcoded | Subprocess |

## 5.6 Difficulty ranking

1. **EI morning scan** — Easiest. Component returns everything. Just pass through.
2. **EI weekly refresh** — Medium. One component dict + two rowcounts + one count query.
3. **Airline play** — Medium. Already reads dicts. Just wrap + remove bool return.
4. **EI daily pipeline** — Medium-hard. Three component dicts to aggregate. Alert details gap.
5. **FM pre-market** — Medium. Two component dicts, straightforward.
6. **OP pipeline** — Easy (data flow). Hard (visual cleanup across 4 files).
7. **FM post-market** — Hard. All 4 sub-tasks return bool. Needs two levels of bool→dict conversion.
8. **FM market hours** — Already done (data). Hard (visual cleanup — 96 beautiful_log calls in source, ~945 per runtime session).
9. **Utility runners** — Trivial. Subprocess boundary means minimal contracts.
