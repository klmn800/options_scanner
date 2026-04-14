# Console Output Audit Report

**Date:** 2026-02-14
**Standard:** `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md` (updated same day)
**Scope:** Orchestrator layer + all 3 strategies plugged into main.py

---

## Executive Summary

The console output standard defines a clean two-layer architecture: orchestrator owns visual structure (boxes, banners, phase headers), strategies own only progress lines and return structured dicts. **None of the three strategies fully comply.** The orchestrator itself has structural issues (duplicate announcements, DB queries for completion stats). Flow Monitor is the worst offender — its `fm_main.py` is effectively a second orchestrator.

| Component | Compliance | Key Issue |
|-----------|-----------|-----------|
| Orchestrator (main_runners.py) | **~60%** | Duplicate announcements, DB queries for stats |
| Flow Monitor | **~15%** | fm_main.py IS an orchestrator; 96 beautiful_log() calls in source (~945/session at runtime) |
| Option Pipeline | **~30%** | Boxes/banners in strategy; return dict exists but strategy also displays |
| Earnings Intelligence | **~20%** | Bool returns instead of dicts; own beautification layer |

---

## 1. Orchestrator Layer (main.py / main_runners.py / main_ui.py)

### What it gets right

- **Mission boxes before every strategy call** — All 14 `run_*` methods in main_runners.py draw a mission box with objectives before execution. Consistent pattern.
- **Phase headers with numbers** — `phase_header()` called from main.py for each major phase (Pre-Market, Flow Monitor, Post-Market, Evening, Friday).
- **Day-end summary from actual results** — `_print_day_summary()` builds from the `results` dict with real True/False/skipped values per step. Never hardcoded.
- **Real-time subprocess streaming** — `_run_streaming_subprocess()` streams each line as it arrives. No silent multi-minute operations.
- **Autofix integration on all errors** — Every `run_*` method queues errors via `queue_error()` on failure.

### Problem 1: Duplicate Announcements (beautiful_log + create_status_box)

Eleven methods emit a `beautiful_log("SUCCESS")` line immediately followed by a `create_status_box("COMPLETE")` with the same information. The user sees both — redundant.

| Method |
|--------|
| `run_morning_option_pipeline()` |
| `run_evening_option_pipeline()` |
| `run_morning_views()` |
| `run_earnings_pipeline()` |
| `run_earnings_morning_scan()` |
| `run_earnings_weekly_refresh()` |
| `run_airline_play_phase()` |
| `run_database_backup()` |
| `run_query_database_sync()` |
| `run_sector_archive()` |
| `run_friday_sector_archive()` |

**Fix:** Remove the `beautiful_log("SUCCESS")` line in each case. The completion box is sufficient.

### Problem 2: Orchestrator Queries DB for Completion Stats

The standard says: "Completion box built ONLY from the strategy's return dict — never query the database separately."

Three methods violate this by running SQL queries after the strategy returns:

- **`run_earnings_pipeline()`**: Queries `earnings_snapshots`, `earnings_moves`, `earnings_upcoming` for counts
- **`run_earnings_morning_scan()`**: Queries `earnings_sector_effects` for opportunity counts
- **`run_earnings_weekly_refresh()`**: Queries `earnings_upcoming` and `earnings_events` for counts

**Root cause:** Earnings Intelligence returns `bool` instead of a metrics dict, so the orchestrator has no choice but to query the DB. Fix is on the EI side (return dicts), then the orchestrator can use them.

### Problem 3: Orchestrator Progress Noise

Seven methods print "Running X..." announcements before calling the subprocess, which then outputs its own progress — creating duplicate narrative:

| Method | Output |
|--------|--------|
| `run_morning_views()` | `"Running morning views..."` |
| `run_metadata_collection()` | `"Collecting metadata..."` |
| `run_earnings_pipeline()` | `"Running snapshot collector..."` |
| `run_earnings_morning_scan()` | `"Scanning for sector sympathy..."` |
| `run_earnings_weekly_refresh()` | `"Fetching earnings calendar..."` |
| `run_sector_archive()` | `"Initializing sector archive..."` |
| `run_friday_sector_archive()` | `"Initializing timed archive..."` |

**Fix:** Remove these print() lines. The mission box already announces what's about to happen. The strategy's progress lines then show it actually happening.

### Problem 4: Coffee Breaks Are Plain Text

`coffee_break()` in main_ui.py uses `_safe_print()` with just two bare lines:
```
☕ Coffee break: 60 seconds - Time for a quick stretch
☕ Resuming operations
```

Per the updated standard, these should use the standard box format. Additionally, all 12 coffee breaks are hardcoded to 60 seconds — the context messages vary but the duration doesn't.

### Problem 5: Mixed Output Channels

Three different output paths are used inconsistently:

| Channel | Goes to console? | Goes to .log? |
|---------|-----------------|---------------|
| `beautiful_log()` via log_utils | Yes | Yes |
| `create_status_box()` via log_utils | Yes | Yes |
| `coffee_break()` via `_safe_print()` | Yes | **No** |
| `print()` statements | Yes | **No** |

The `print()` statements (Problem 3) and coffee breaks bypass the log file entirely.

---

## 2. Flow Monitor Strategy

### Severity: CRITICAL

`fm_main.py` is not a strategy file — it's a second orchestrator. It defines its own `beautiful_log()`, `colorize()`, `create_phase_header()`, `create_success_celebration()`, and `create_error_box()` functions. It manages three phases (pre-market, market hours, post-market) with full visual orchestration.

### Violation Inventory

| Category | Count | Key locations |
|----------|-------|--------------|
| `beautiful_log()` calls | 96 | Throughout fm_main.py (96 source-level; ~945 runtime calls in a typical 4-hour market session) |
| `print()` statements | 40+ | fm_main.py, fm_alerts.py, fm_social_notifier.py, fm_collector.py |
| Box-drawing decorations | 80+ | `═`, `─`, `├─`, `└─` throughout |
| Completion announcements | 12+ | "COMPLETE", "SUCCESS", celebrations |
| Formatting function definitions | 12 | fm_main.py (9 beautification + safe_log + get_dynamic_symbol_count + get_api_budget_info) |

### Per-File Breakdown

**fm_main.py (1,818 lines) — CRITICAL:**
- Defines 12 formatting/utility functions: `get_display_settings()`, `colorize()`, `beautiful_log()`, `get_dynamic_symbol_count()`, `get_api_budget_info()`, `create_phase_header()`, `create_task_box()`, `create_error_box()`, `create_success_celebration()`, `create_section_divider()`, `contextual_coffee_break()`, `safe_log()` — all orchestrator functions that shouldn't be in a strategy
- `run_pre_market()` returns `bool` (should return dict)
- `run_market_hours()` returns `dict` (correct — the only one that does)
- `run_post_market()` returns `bool` (should return dict)
- `create_success_celebration("PRE-MARKET SETUP COMPLETE", ...)`
- Market hours: ~945 beautiful_log calls in a typical 4-hour session (240 cycles × ~4 calls each, plus periodic summaries)
- Post-market: 18 beautiful_log calls across 6 sub-tasks, each announcing start + success/failure

**fm_alerts.py — MEDIUM:**
- Alert display box with `print()` using `═` and `-` separators, emoji category headers (🔴 🟡 ⚪)
- `_log_alert_summary()` with `logging.info("=" * 50)` decorative separators
- Returns structured dict (correct)

**fm_social_notifier.py — MEDIUM:**
- `queue_alert_for_posting()` draws a `═` box with `print()` for every queued alert
- CLI commands use 21+ `print()` statements (acceptable for standalone use)

**fm_collector.py — LOW:**
- 10 `print()` statements for startup/status messages that should use `logging`
- Per-symbol logging is appropriate

**fm_baseline_generator.py — CLEAN:**
- No `_log_summary()` or `"=" * N` patterns found. No violations.

**fm_alert_resolver.py — LOW:**
- Diagnostic output with `logging.info("=" * 60)` separators

**fm_session_stats.py — EXEMPLARY:**
- Zero violations. Returns structured dict via `get_summary()`. Provides `format_end_of_day_lines()` that returns strings without printing them. This is the model for how all FM files should work.

### Architectural Issue

The fundamental problem is that `fm_main.py` was built as an orchestrator, not a strategy. When main_runners.py calls `run_flow_monitor()`, it calls fm_main.py's `main()`, which then runs its own three-phase orchestration with its own visual output. This creates a nested orchestrator pattern that the standard doesn't account for.

**Two approaches to fix:**
1. **Absorb fm_main.py into main_runners.py** — Move the phase logic (pre-market, market hours, post-market) into `run_flow_monitor()` as sub-steps, like how the Earnings pipeline sub-steps work
2. **Strip fm_main.py to pure coordination** — Remove all visual output, have it return structured results for each phase, let the orchestrator handle display

### Output Volume Problem

In a typical 4-hour market session, Flow Monitor produces ~945 lines of `beautiful_log()` output. Per-symbol collection lines are expected and correct (FM is a delegated orchestrator with per-item detail logging). The problem is not volume — it's that the output uses `beautiful_log()` with emoji formatting instead of plain `logging.info()`, and includes celebration blocks, phase headers, and announcements that belong to the orchestrator layer.

---

## 3. Option Pipeline Strategy

### Severity: HIGH

Option Pipeline has the same structural issue as the others (own beautification layer, boxes in strategy code) but has one major advantage: **it already returns a comprehensive structured dict** from `run_pipeline()`.

### Violation Inventory

| Category | Count | Key locations |
|----------|-------|--------------|
| Box-drawing separators | 8+ | op_main.py, op_collector.py, op_symbol_rollup.py, op_timing_calculator.py |
| Completion announcements | 7+ | "COMPLETE", "SUCCESS", "[OK]" |
| Beautiful formatting functions | 6 | op_main.py |
| `safe_log()` with decorative output | 25+ | Throughout op_main.py |
| Tree diagrams (├─, └─, •) | 12+ | Phase descriptions in op_main.py |

### Per-File Breakdown

**op_main.py — HIGH:**
- Defines `safe_log()`, `create_phase_header()`, `create_progress_box()`, `create_success_celebration()`, `create_error_box()`, `log_pipeline_start()` — same pattern as FM and EI
- Phase headers with emoji (`📊 PHASE 1: DATA COLLECTION`)
- Tree diagrams with `├─` and `└─`
- `create_success_celebration("OPTION PIPELINE", accomplishments)`
- Startup banner with `"=" * 70`
- Final success/failure print statements
- **Returns structured dict** (correct — comprehensive with collection, analysis, rollup, timing, health metrics)

**op_collector.py — HIGH:**
- Massive completion banner: `"=" * 70`, `"🎉 COLLECTION COMPLETE"`, followed by 6 metric lines with emoji
- Progress logging is acceptable

**op_symbol_rollup.py — MEDIUM:**
- Initialization `print()` statements
- `"=" * 60` completion banner with "OP ROLLUP COMPLETE" and statistics
- Progress logging is acceptable

**op_timing_calculator.py — MEDIUM:**
- `[OK]` completion marker
- Backfill completion banner with `"=" * 60`

**op_config.py, op_storage.py — LOW:**
- `print()` in `if __name__ == '__main__'` test blocks (acceptable)

### Bright Spot

The return dict from `run_pipeline()` is the best in the system — comprehensive, well-structured, and actually used by the orchestrator in `run_morning_option_pipeline()` to build the completion box. This is the correct pattern. The problem is that the strategy *also* displays its own output.

---

## 4. Earnings Intelligence Strategy

### Severity: HIGH

Earnings Intelligence has the most return-value violations: all four `run_*()` functions return `bool` instead of dicts, despite the component modules already returning dicts internally. It also defines its own complete beautification layer.

### Violation Inventory

| Category | Count | Key locations |
|----------|-------|--------------|
| Banner separators (=== lines) | 18+ | ei_main.py, all ei_*.py files |
| Completion announcements | 20+ | ✅ SUCCESS, ❌ FAILED, celebrations |
| Functions returning bool instead of dict | 4 | run_weekly_refresh, run_daily_pipeline, run_morning_scan, run_all_mode |
| Beautification functions | 7 | ei_main.py |
| Tree diagrams (├─, └─) | 4 | Startup trees in each mode |

### Per-File Breakdown

**ei_main.py (1,063 lines) — HIGH:**
- Defines `safe_log()`, `colorize()`, `beautiful_log()`, `create_phase_header()`, `create_progress_box()`, `create_success_celebration()`, `create_error_box()`, `log_pipeline_start()`
- Startup banner with `"=" * 70`
- Final success/failure announcement
- Each mode has: phase header → startup tree → [1/N] progress → ✅ success per task → celebration
- **All four run_*() functions return bool**

**ei_arbitrage_scanner.py — MEDIUM:**
- `_display_opportunities()`: `"=" * 80` separator, formatted opportunity display
- `_log_summary()`: `"=" * 60` separator, "ARBITRAGE SCAN SUMMARY"
- Startup banner and success announcements
- Returns dict (correct)

**ei_fetch_upcoming.py — MEDIUM:**
- `_log_summary()`: `"=" * 60` separator, "EARNINGS FETCH SUMMARY"
- Startup banner and success announcements
- Returns dict (correct)

**ei_snapshot_collector.py — MEDIUM:**
- `_log_summary()`: `"=" * 60` separator, "SNAPSHOT COLLECTION SUMMARY"
- Startup banner and success announcements
- Returns dict (correct)

**ei_moves_upcoming.py — MEDIUM:**
- Startup banner, configuration display, completion announcements, alert summary box with `-` separators
- Returns dict (correct)

### The Bool Return Problem

This is EI's most impactful issue. The component modules *already return dicts*:

| Component | Returns |
|-----------|---------|
| `EarningsFetcher.fetch_upcoming_earnings()` | `dict` with metrics |
| `SnapshotCollector.collect_daily_snapshots()` | `dict` with metrics |
| `PostEarningsCalculator.calculate()` | `dict` with metrics |
| `ArbitrageScanner.scan_morning_opportunities()` | `dict` with metrics |
| `update_expected_moves()` | `dict` with processed/failed/alerts |

But `ei_main.py`'s `run_daily_pipeline()`, `run_weekly_refresh()`, etc. **discard these dicts** and return only `True`/`False`. This forces the orchestrator (main_runners.py) to query the database for the numbers it needs for the completion box — the exact anti-pattern the standard prohibits.

---

## 5. Cross-Cutting Patterns

### Pattern: Every Strategy Reinvents Beautification

All three strategies define nearly identical helper functions:

| Function | FM | OP | EI |
|----------|----|----|-----|
| `safe_log()` | Yes | Yes | Yes |
| `colorize()` | Yes | No | Yes |
| `beautiful_log()` | Yes | No | Yes |
| `create_phase_header()` | Yes | Yes | Yes |
| `create_progress_box()` | No | Yes | Yes |
| `create_success_celebration()` | Yes | Yes | Yes |
| `create_error_box()` | Yes | Yes | Yes |

These are all doing the orchestrator's job. The system already has `tools/log_utils.py` for this purpose.

### Pattern: Strategies Announce Their Own Completion

Every strategy has some form of "I'm done!" output — celebrations, success messages, banners. The standard says this is the orchestrator's job via the completion box.

### Pattern: Tree Diagrams

All three strategies use tree diagrams to describe what they're about to do:
```
├─ Step 1: Fetch data
├─ Step 2: Analyze
└─ Step 3: Report
```

These are mini mission boxes drawn by the strategy. The orchestrator already draws a mission box before calling the strategy. This creates duplicate "here's what we'll do" messaging.

---

## 6. Prioritized Fix Plan

### Tier 1: High Impact, Low Effort

These fixes improve output quality without restructuring:

1. **Remove duplicate announcements in main_runners.py** — Delete the 7 `beautiful_log("SUCCESS")` lines that precede completion boxes. (~10 minutes)

2. **Remove orchestrator progress noise** — Delete the 7 "Running X..." print statements in main_runners.py. (~10 minutes)

3. **Fix coffee break format** — Update `coffee_break()` in main_ui.py to use `create_status_box()` per the updated standard. (~15 minutes)

### Tier 2: High Impact, Medium Effort

4. **Convert EI return values from bool to dict** — Wire through the component dicts that already exist. Remove DB queries from main_runners.py. (~1-2 hours across ei_main.py + main_runners.py)

5. **Strip completion announcements from all strategies** — Remove `create_success_celebration()`, banner separators, and "COMPLETE"/"SUCCESS" messages from FM, OP, and EI. (~2-3 hours across ~15 files)

6. **Remove beautification functions from strategies** — Delete `safe_log()`, `colorize()`, `beautiful_log()`, `create_phase_header()`, `create_progress_box()`, `create_success_celebration()`, `create_error_box()` from all three strategy entry points. Replace remaining legitimate output with `print()` or `logging.info()`. (~1-2 hours)

### Tier 3: High Impact, High Effort (Architectural)

7. **Restructure fm_main.py** — Either absorb its orchestration into main_runners.py or strip it to pure coordination with dict returns. This is the single largest task because fm_main.py is 1,818 lines with interleaved business logic and display logic. (~4-8 hours)

8. **Clean up FM market-hours output** — Remove redundant duplicate lines and fix output channels (no `beautiful_log()`, no raw `print()`). The per-cycle content is information-dense and useful — the goal is smart logging, not minimal logging. See `VISUAL_DESIGN_REFERENCE.md` Section 10 for approved keep/cut decisions. (~2-3 hours)

9. **Remove `_log_summary()` from all EI/OP component files** — Replace with returning summary data in the dict. (~2-3 hours across ~8 files)

### Tier 4: Polish

10. **Consolidate output channels** — Ensure all orchestrator output goes through log_utils (including coffee breaks). (~30 minutes)

11. **Add time-based heartbeat** — Implement the 60-second silence override in strategies that process slow operations. (~1 hour)

12. **Suppress third-party library noise** — Add logger level overrides for requests, urllib3, etc. where not already present. (~30 minutes)

---

## 7. What Already Works

Credit where due — these patterns are correct and should be preserved:

- **fm_session_stats.py** — Returns structured data, provides formatted lines without printing them. Model file.
- **Option Pipeline return dict** — Comprehensive, well-structured, actually used by orchestrator. Model return value.
- **Day-end summary** — Built from actual results dict. Honest.
- **Subprocess streaming** — `_run_streaming_subprocess()` is correct.
- **Phase headers in main.py** — Clean organization of the daily cycle.
- **Autofix integration** — Consistent error queuing across all runners.
- **Progress logging intervals in op_collector.py and op_symbol_rollup.py** — Reasonable frequency.

---

## 8. Autofix Integration Assessment

The console output overhaul and Autofix aren't in conflict — they're complementary. The overhaul's core change (strategies return structured dicts instead of bool/None/printing their own output) directly improves Autofix context quality. This section assesses the current integration and what changes with the overhaul.

### Current State

Every `run_*()` method in main_runners.py has a `try/except` that calls `queue_error()` on failure. This is consistent and correct — the orchestrator is already the integration point. However, the context passed to autofix is poor:

| What autofix gets today | What it should get after overhaul |
|------------------------|----------------------------------|
| `{'error': str(e)}` — bare exception string | Full return dict: symbols_processed, failed_symbols, failure_reason, duration, sub_task results |
| Triggered only by unhandled exceptions | Triggered by `success: False` in return dict (graceful failures) AND unhandled exceptions (safety net) |
| No distinction between degraded and fatal | `severity` field in return dict enables routing: ERROR → batch queue, CRITICAL → immediate spawn |

### What Changes

**In main_runners.py (orchestrator):**

The `try/except` block becomes a fallback, not the primary error path. Strategies that fail gracefully return `{'success': False, ...}`. The orchestrator draws a failure completion box from the dict, then passes the same dict to `queue_error()`. Autofix gets the strategy's own structured failure diagnosis for free.

**CRITICAL errors flow through the return dict:**

Today, some strategies call `handle_error()` + `sys.exit(1)` directly — the orchestrator never sees the failure, never draws a completion box, and the console output is orphaned (mission box opens, then process dies). After the overhaul, strategies return `{'success': False, 'severity': 'CRITICAL', 'failure_reason': '...'}`. The orchestrator draws the failure box first, then calls `handle_error()`. Clean console output even for fatal errors.

Direct `handle_error()` calls remain only for pre-execution failures where no return path exists (import crashes, database unreachable at startup).

**Subprocess strategies are the exception:**

Strategies running via `_run_streaming_subprocess()` can't return dicts through the process boundary. These may call `queue_error()` directly. The orchestrator detects non-zero exit codes and draws error boxes.

### What Doesn't Change in Autofix

- `queue_error()` API signature stays the same (context dict just gets richer)
- `handle_error()` behavior stays the same
- Batch mode scheduling, deduplication, safety rails unchanged
- Instruction files for spawned sessions unchanged
- Prompt builders in `main_fix_launcher.py` / `batch_mode_spawner.py` may benefit from a minor update to format richer context, but richer context is additive — existing formatting still works

### Integration Work Required

This is **not a separate task** — it happens naturally as part of the overhaul tiers:

- **Tier 2, Item 4 (Convert EI returns from bool to dict):** Once EI returns dicts, the orchestrator can pass them to `queue_error()` instead of bare exception strings. Same for any other bool→dict conversion.
- **Tier 2, Items 5-6 (Strip completion announcements, remove beautification functions):** Any strategy-level `queue_error()` or `handle_error()` calls discovered during this work should be moved to the orchestrator.
- **Tier 3, Item 7 (Restructure fm_main.py):** FM's coordinator should return dicts for each phase; orchestrator handles both display and error routing.

### Checklist Addition

When working through the overhaul, verify for each `run_*()` method:

- [ ] `queue_error()` passes the strategy's return dict as context, not just `str(e)`
- [ ] `success: False` in return dict triggers `queue_error()` (not just unhandled exceptions)
- [ ] No strategy-level `queue_error()` or `handle_error()` calls (except subprocesses)
- [ ] CRITICAL failures returned in dict with `severity: 'CRITICAL'`, orchestrator calls `handle_error()` after drawing failure box
- [ ] The `except Exception` safety net still exists for truly unhandled crashes
