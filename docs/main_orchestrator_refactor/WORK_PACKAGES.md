# Console Output Overhaul — Work Packages

**Date:** 2026-02-17
**Purpose:** Scoped, independently-executable units of work for the console output refactoring. Each package can be completed by a single Claude Code agent session without stepping on other packages.

**Prerequisites:** Read these first:
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md` — the target architecture
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_AUDIT.md` — violation inventory
- `docs/main_orchestrator_refactor/RETURN_DICT_CONTRACTS.md` — interface contracts

---

## Dependency Graph

```
Package 0:  Orchestrator Standalone Cleanup ──── (no dependencies, start here)
Package 1:  EI Dict Returns ──────────────────── (no dependencies)
Package 2:  EI Visual Cleanup ────────────────── (depends on Package 1)
Package 3:  OP Visual Cleanup ────────────────── (no dependencies)
Package 4:  FM Pre-Market Dict Return ────────── (no dependencies)
Package 5:  FM Post-Market Research + Dict ───── (no dependencies)
Package 6A: FM Formatting Functions + Coffee ─── (depends on Package 0)
Package 6B: FM Function-Level Triage ──────────── (depends on Packages 4, 5, 6A)
Package 6C: FM Market Hours Triage ────────────── (depends on Package 6A)
Package 6D: FM Component Files Cleanup ────────── (depends on Package 6A)
Package 7:  Utility Runner Polish ────────────── (no dependencies, low priority)
```

Packages 0, 1, 3, 4, 5, 7 can all run in parallel.
Package 2 waits on 1. Package 6A waits on 0 (Package 0 adds daily state persistence to `fm_session_stats.py` which 6A must not conflict with). Package 6B waits on 4, 5, and 6A. Packages 6C and 6D each wait on 6A only and can run in parallel with each other (and with 6B, if 6B's dependencies are met).

---

## Package 0: Orchestrator Standalone Cleanup

**Goal:** Remove redundant announcements and filler from main_runners.py, fix coffee break format in main_ui.py with dynamic "Up Next" support, add STEP_SEQUENCE constant, and add daily state persistence (`logs/daily_state.json`) so orchestrator results and FM session stats survive mid-day restarts. Zero strategy changes except adding save/load to `fm_session_stats.py`.

**Estimated scope:** ~150 lines deleted/modified across 4 files + ~60 lines added for daily state infrastructure.

**Dependencies:** None. Safe to start immediately. Other packages (especially 6) depend on this being done first for daily state.

**Files modified:**
- `main_runners.py`
- `main_ui.py` (coffee break rewrite + daily state helpers)
- `main.py` (add `STEP_SEQUENCE` constant, update `coffee_break()` call sites, wire daily state reset/load/save)
- `strategies/flow_monitor/fm_session_stats.py` (add `save_to_daily_state()` and `load_from_daily_state()` methods)

**Files read-only (reference):**
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md` (coffee break format spec)
- `docs/main_orchestrator_refactor/VISUAL_DESIGN_REFERENCE.md` (coffee break mockup with "Up Next", daily state notes in sections 11-12)
- `tools/log_utils.py` (create_status_box API for coffee breaks)

**Do NOT touch:** Any strategy file except `fm_session_stats.py`. Any coordinator. Any component module.

### Steps

**Step 1: Remove duplicate `beautiful_log("SUCCESS")` lines before completion boxes.**

These 10 methods emit a success announcement immediately before a completion box. Remove the `beautiful_log` line in each case (the completion box is the success signal). Search for each string to find the exact line:

| Method | Content to find and delete |
|--------|---------------------------|
| `run_morning_option_pipeline()` | `self.beautiful_log("Morning Option Pipeline completed successfully", 'success')` |
| `run_evening_option_pipeline()` | `self.beautiful_log("Evening Option Pipeline completed successfully", 'success')` |
| `run_morning_views()` | `self.beautiful_log("✅ MORNING VIEWS COMPLETED SUCCESSFULLY", 'success')` |
| `run_earnings_pipeline()` | `self.beautiful_log("✅ EARNINGS INTELLIGENCE PIPELINE COMPLETED", 'success')` |
| `run_earnings_morning_scan()` | `self.beautiful_log("✅ ARBITRAGE SCANNER COMPLETED", 'success')` |
| `run_earnings_weekly_refresh()` | `self.beautiful_log("✅ WEEKLY REFRESH COMPLETED", 'success')` |
| `run_database_backup()` | `self.beautiful_log("✅ DATABASE BACKUP COMPLETED SUCCESSFULLY", 'success')` |
| `run_query_database_sync()` | `self.beautiful_log("✅ QUERY DATABASE SYNC COMPLETED SUCCESSFULLY", 'success')` |
| `run_sector_archive()` | `self.beautiful_log("✅ SECTOR ARCHIVE COMPLETED SUCCESSFULLY", 'success')` |
| `run_friday_sector_archive()` | `self.beautiful_log("✅ DATABASE ARCHIVE COMPLETED SUCCESSFULLY", 'success')` |

Also remove the blank `print("")` lines that immediately follow each of these (they exist to separate the beautiful_log from the box — no longer needed).

**Step 2: Remove duplicate "Initializing/Starting/Running" announcements.**

These lines duplicate the mission box that already precedes each strategy call. Remove the `beautiful_log` + `print` pairs. Find these by searching for the string content within each method:

| Method | Content to find and delete |
|--------|---------------------------|
| `run_morning_option_pipeline()` | `"Initializing Option Pipeline orchestrator"`, `"Beginning Option Pipeline Refresh"` |
| `run_evening_option_pipeline()` | `"Initializing Option Pipeline for evening"`, `"Running Evening Option Pipeline"` |
| `run_morning_views()` | `"Initializing Morning Views generation"`, `print("🔄 Running morning views")` |
| `run_metadata_collection()` | `"Starting metadata collection pipeline"`, `print("🔄 Collecting metadata")` |
| `run_earnings_pipeline()` | `"Initializing Earnings Intelligence pipeline"`, `"Starting Earnings Intelligence daily pipeline"`, `print("🔄 Running snapshot collector")` |
| `run_earnings_morning_scan()` | `"Initializing earnings arbitrage scanner"`, `"Running morning arbitrage scanner"`, `print("🔄 Scanning for sector sympathy")` |
| `run_earnings_weekly_refresh()` | `"Initializing earnings weekly refresh"`, `"Running earnings weekly refresh"`, `print("🔄 Fetching earnings calendar")` |
| `run_database_backup()` | `"Starting database backup process"`, `print("🔄 Initializing backup operation")` |
| `run_query_database_sync()` | `"Starting query database sync"`, `print("🔄 Syncing to query database")` |
| `run_sector_archive()` | `"Starting sector archive (all tiers)"`, `print("📦 Initializing sector archive")` + `print("🔍 Scanning database for archivable")` |
| `run_friday_sector_archive()` | `"Starting Friday archive operation"`, `print("📦 Initializing timed archive")` + `print("🔍 Scanning database for expired")` |

**Note:** Keep `beautiful_log` lines that convey genuinely new information the mission box doesn't have (e.g., the time-skip logic in `run_flow_monitor()` that reports "Market hours detected — skipping pre-market"). Also keep error-path `beautiful_log` calls — those report failures, not duplicate announcements.

**Step 3: Remove filler lines from completion boxes.**

Find completion boxes with non-measured filler text and remove those lines:

| Method | Filler to remove |
|--------|-----------------|
| `run_database_backup()` | `"Protection: ✅ Database secured"`, `"System: Ready for safe operations"` |
| `run_query_database_sync()` | `"Analysis tools can now safely query fresh data"`, `"System: Ready for analysis operations"` |
| `run_sector_archive()` | `"Database: Performance optimized"` |
| `run_friday_sector_archive()` | `"Database: Performance optimized"`, `"🎉 Archive completed with full weekend runtime"` |
| `run_morning_views()` | `"Views created: 4 SQL views in datalake_query.db"` (hardcoded count) |
| `run_metadata_collection()` | `"All ~750 symbols updated with fresh metadata"` (hardcoded approximate count) |

Replace hardcoded counts with success/fail status only (these are subprocesses — we can't get real counts through the process boundary).

**Step 4: Add STEP_SEQUENCE constant and rewrite coffee_break().**

In `main.py` (or `main_ui.py` — wherever `CleanOrchestrator` is defined), add a class-level constant defining the daily step order. This is the single source of truth for "Up Next" resolution:

```python
STEP_SEQUENCE = [
    'Morning Option Pipeline',
    'Earnings Arbitrage Scanner',
    'Metadata Collection',
    'Query Database Sync (Morning)',
    'Morning Views',
    'Flow Monitor',
    'Evening Option Pipeline',
    'Query Database Sync (Evening)',
    'Earnings Pipeline',
    'Airline Play Tracking',
    'Query Database Sync (Final)',
    'Daily Backup',
    'Autofix Review',
    # Friday-only (only reached inside `if is_friday:` block)
    'Weekly Backup',
    'Earnings Calendar Refresh',
    'Sector Archive',
]
```

In `main_ui.py`, rewrite `coffee_break()` to use `create_status_box` with dynamic "Up Next" lookup:

```python
def coffee_break(self, seconds, context="Taking a break", after_step=None):
    """Timed pause between operations with dynamic 'Up Next' display.

    Args:
        seconds: Duration to sleep
        context: Human-readable context message
        after_step: Name of the step that just completed (must match a
                    STEP_SEQUENCE entry). Used to look up the next step.
    """
    from tools.log_utils import create_status_box as _box

    lines = [context]
    if seconds >= 60:
        lines.append("Duration: {} minutes".format(seconds // 60))
    else:
        lines.append("Duration: {} seconds".format(seconds))

    # Dynamic "Up Next" lookup
    if after_step and hasattr(self, 'STEP_SEQUENCE'):
        try:
            idx = self.STEP_SEQUENCE.index(after_step)
            if idx + 1 < len(self.STEP_SEQUENCE):
                lines.append("Up Next: {}".format(self.STEP_SEQUENCE[idx + 1]))
        except ValueError:
            pass  # after_step not in sequence — skip "Up Next"

    _box("☕ Coffee Break", lines)
    time.sleep(seconds)
    _box("Resuming Operations", [
        "Wait complete — continuing pipeline",
    ])
```

**Step 5: Update all coffee_break() call sites in main.py.**

Add `after_step=` to every existing `coffee_break()` call in `run_smart_endless_operation()`:

| Line (approx) | Current call | Add parameter |
|--------|-------------|---------------|
| 363 | `self.coffee_break(60, "Time for a quick stretch")` | `after_step="Morning Option Pipeline"` |
| 368 | `self.coffee_break(60, "Quick coffee break")` | `after_step="Earnings Arbitrage Scanner"` |
| 377 | `self.coffee_break(60, "Morning cuppa to go with the news")` | `after_step="Query Database Sync (Morning)"` |
| 395 | `self.coffee_break(60, "Taking a well-deserved break")` | `after_step="Flow Monitor"` |
| 404 | `self.coffee_break(60, "Stretching our legs a bit")` | `after_step="Query Database Sync (Evening)"` |
| 409 | `self.coffee_break(60, "Quick breather before the home stretch")` | `after_step="Earnings Pipeline"` |
| 421 | `self.coffee_break(60, "Final sync complete - waiting for lock release before backup")` | `after_step="Query Database Sync (Final)"` |
| 426 | `self.coffee_break(60, "One more sip before we're done")` | `after_step="Daily Backup"` |
| 435 | `self.coffee_break(60, "Daily backup complete - lock release before weekly backup")` | `after_step="Daily Backup"` |
| 440 | `self.coffee_break(60, "Weekly backup complete - lock release before earnings refresh")` | `after_step="Weekly Backup"` |
| 445 | `self.coffee_break(60, "Earnings refresh complete - lock release before archive")` | `after_step="Earnings Calendar Refresh"` |
| 455 | `self.coffee_break(60, "Day complete - lock release after Friday operations")` | `after_step="Sector Archive"` (last step — no "Up Next" will display) |

**Note:** The `after_step` values must match `STEP_SEQUENCE` entries exactly (case-sensitive). If a step name changes in `STEP_SEQUENCE`, the corresponding `after_step=` call sites need updating too — but the "Up Next" resolution is always dynamic from the sequence.

**Step 6: Add daily state persistence (`logs/daily_state.json`).**

Create a single JSON file that persists orchestrator phase results and FM session stats across restarts. This file is overwritten (reset) at the start of each daily cycle, at the same time the orchestrator log file rolls over.

**File location:** `logs/daily_state.json` (undated — always one file, overwritten each morning)

**Structure:**
```json
{
  "date": "2026-02-18",
  "orchestrator_results": {
    "1.1 Morning Option Pipeline": true,
    "1.2 Arbitrage Scanner": true,
    "1.3 Metadata Collection": true
  },
  "fm_session": {
    "total_cycles": 15,
    "successful_cycles": 14,
    "failed_cycles": 1,
    "errors_by_type": {"timeout": 3, "connection": 1, "rate_limit": 0, "other": 0},
    "cycle_times": [142.3, 138.7, 145.1],
    "collection_times": [98.2, 95.1, 101.4],
    "analysis_times": [31.4, 30.2, 32.1],
    "alert_times": [8.1, 7.9, 8.5],
    "missing_quotes": {"VIXW": 15, "SPX": 15, "VIX": 15},
    "failed_options": {"WOLF": 15, "BDX": 12},
    "news_enrichment": {"enriched": 12, "skipped": 3, "failed": 1}
  }
}
```

**Helpers to add** (in `main_ui.py` or a small utility — keep it simple):

```python
DAILY_STATE_PATH = os.path.join('logs', 'daily_state.json')

def _reset_daily_state(date_str):
    """Overwrite daily_state.json with empty structure. Called at start of each daily cycle."""
    state = {'date': date_str, 'orchestrator_results': {}, 'fm_session': {}}
    with open(DAILY_STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)

def _load_daily_state():
    """Load daily_state.json. Returns None if file missing or date doesn't match today."""
    try:
        with open(DAILY_STATE_PATH, 'r') as f:
            state = json.load(f)
        if state.get('date') == now_eastern().strftime('%Y-%m-%d'):
            return state
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None

def _save_orchestrator_result(step_name, result):
    """Update a single orchestrator result in daily_state.json."""
    state = _load_daily_state() or {'date': now_eastern().strftime('%Y-%m-%d'), 'orchestrator_results': {}, 'fm_session': {}}
    state['orchestrator_results'][step_name] = result
    with open(DAILY_STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)

def _save_fm_session(session_dict):
    """Update FM session stats in daily_state.json. Called after each FM cycle."""
    state = _load_daily_state() or {'date': now_eastern().strftime('%Y-%m-%d'), 'orchestrator_results': {}, 'fm_session': {}}
    state['fm_session'] = session_dict
    with open(DAILY_STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)
```

**Wire into orchestrator:**
- In `run_smart_endless_operation()`, call `_reset_daily_state(date_str)` at the top of each daily cycle (near where `results = {}` is initialized). Then also load any existing state: `saved = _load_daily_state()` → if not None, pre-populate `results` from `saved['orchestrator_results']`.
- After each phase completes (where `results['1.1 Morning ...'] = True/False` is set), also call `_save_orchestrator_result(step_name, result)`.
- In `_print_day_summary()`, the `results` dict now contains both fresh and restored results — no change needed to the display logic.

**Step 7: Wire FM session stats into daily_state.json.**

In `fm_session_stats.py`, add `save_to_daily_state()` and `load_from_daily_state()` methods to `FMSessionStats`:

- `save_to_daily_state()`: Serializes the stats object to a dict and calls `_save_fm_session(dict)`. Called after each cycle completes (in `run_market_hours()` after `stats.record_cycle()`).
- `load_from_daily_state()`: Class method or init parameter. On `FMSessionStats()` creation, check daily_state.json for existing `fm_session` data. If found and today's date matches, restore counters from it.

This means: if FM is restarted mid-day, the session summary at end-of-day will reflect ALL cycles from the entire day, not just post-restart.

**Note:** This changes the "Do NOT touch fm_session_stats.py" guidance in Package 6. Package 6 should NOT add these methods — they are added here in Package 0. Package 6's instruction is updated to say: "fm_session_stats.py is modified by Package 0 (daily state persistence) — do not make additional changes."

### Verification

1. **Grep check:** `grep -rn "beautiful_log.*successfully\|beautiful_log.*COMPLETED\|beautiful_log.*COMPLETE\|beautiful_log.*Initializing\|beautiful_log.*Starting.*pipeline\|beautiful_log.*Running.*pipeline\|beautiful_log.*Beginning" main_runners.py` — should return only error-path and FM time-skip lines, not pre-completion or pre-mission duplicates.
2. **Grep check:** `grep -rn "Database secured\|Ready for safe operations\|Ready for analysis\|Performance optimized\|~750 symbols\|4 SQL views" main_runners.py` — should return zero matches.
3. **Visual check:** Read the coffee_break method and confirm it uses `create_status_box` and resolves "Up Next" from `STEP_SEQUENCE`.
4. **Sequence check:** Verify `STEP_SEQUENCE` order matches the actual execution order in `run_smart_endless_operation()`.
5. **Call site check:** `grep -rn "coffee_break" main.py` — every call should have `after_step=` parameter. Count should match the 12 calls listed above.
6. **Daily state reset check:** Verify `_reset_daily_state()` is called at the top of each daily cycle in `run_smart_endless_operation()`.
7. **Daily state save check:** Verify `_save_orchestrator_result()` is called after each phase result is recorded.
8. **FM state save check:** Verify `stats.save_to_daily_state()` is called after each cycle in `run_market_hours()`.
9. **Restart resilience check:** Verify `_load_daily_state()` is called at startup and pre-populates the `results` dict.
10. **Staleness check:** Verify that loading a file with yesterday's date returns None (fresh start).
11. **Smoke test:** `python main.py --once --debug 2>&1 | head -100` — should show mission box → progress → completion box → coffee break with "Up Next" line. (Only feasible outside market hours.)

---

## Package 1: EI Dict Returns

**Goal:** Convert all 3 EI coordinator functions from `bool` to structured `dict` returns. Update the orchestrator to use these dicts for completion boxes instead of DB queries. Fix the `events_analyzed` naming bug.

**Estimated scope:** ~200 lines changed across 3 files.

**Dependencies:** None (can run in parallel with Packages 0, 3, 4, 5).

**Files modified:**
- `strategies/earnings_intel/ei_main.py` — convert 3 return values from bool to dict
- `strategies/earnings_intel/ei_moves_upcoming.py` — expand return dict with alert details
- `main_runners.py` — update 3 `run_earnings_*()` methods to use return dicts, remove DB queries

**Files read-only (reference):**
- `docs/main_orchestrator_refactor/RETURN_DICT_CONTRACTS.md` sections 1.1-1.3 — exact dict specs
- `strategies/earnings_intel/ei_snapshot_collector.py` — verify component return dict
- `strategies/earnings_intel/ei_post_earnings_calc.py` — verify component return dict
- `strategies/earnings_intel/ei_arbitrage_scanner.py` — verify component return dict
- `strategies/earnings_intel/ei_fetch_upcoming.py` — verify component return dict

**Do NOT touch:** EI visual output (that's Package 2). OP files. FM files. Component module logic (only expand return dicts).

### Steps

**Step 1: Expand `update_expected_moves()` return dict (ei_moves_upcoming.py)**

Currently returns `{'processed': int, 'failed': int, 'alerts': int}`.

Add an `alert_details` list. The function already computes this data in its processing loop — it knows which symbols triggered alerts and their signal/underpricing values. Collect them into:
```python
'alert_details': [
    {'symbol': str, 'days_ahead': int, 'relative_underpricing_pct': float, 'signal': str},
    ...
]
```

Find where `earnings_alert = 1` is set in the processing loop and capture the symbol's details at that point.

**Step 2: Fix `events_analyzed` naming bug (ei_main.py)**

In `run_daily_pipeline()`, the coordinator initializes `calc_results = {'moves_calculated': 0, 'events_analyzed': 0, 'errors': 0}` but the component returns `events_ready`, not `events_analyzed`. Find the initialization dict and the `.get('events_analyzed', 0)` references and change them to `events_ready` to match the component's actual return key.

**Step 3: Convert `run_morning_scan()` from bool to dict (ei_main.py)**

This is the easiest conversion — the component already returns everything needed.

Find where `scan_results` is captured from `scanner.scan_morning_opportunities()`. Instead of reading it for logging then returning `True`, build and return the contract dict:

```python
return {
    'success': True,
    'duration_seconds': time.time() - start_time,
    'errors': scan_results.get('errors', 0),
    'failed_symbols': [],
    'scan_date': scan_results.get('scan_date', ''),
    'earnings_today': scan_results.get('earnings_today', 0),
    'opportunities_found': scan_results.get('opportunities_found', 0),
    'high_quality': scan_results.get('high_quality', 0),
    'medium_quality': scan_results.get('medium_quality', 0),
    'low_quality': scan_results.get('low_quality', 0),
    'persisted': scan_results.get('persisted', 0),
}
```

On failure, return `{'success': False, 'failure_reason': str(e), 'errors': 1, ...}` with zeros for all count fields. Do NOT call `handle_error()` from the coordinator — that moves to the orchestrator.

**Step 4: Convert `run_weekly_refresh()` from bool to dict (ei_main.py)**

Three sub-tasks: fetch (component dict), archive (inline SQL rowcount), cleanup (inline SQL rowcount).

- Capture `fetch_results` from `fetcher.fetch_upcoming_earnings()`
- Capture `archived_count` from `cursor.rowcount` after the archive INSERT
- Capture `cleanup_count` from `cursor.rowcount` after the cleanup DELETE
- After all 3 tasks, query `SELECT COUNT(*) FROM earnings_upcoming WHERE earnings_date >= DATE('now')` for `upcoming_count`
- Build and return the contract dict per RETURN_DICT_CONTRACTS.md section 1.3
- Remove `handle_error()` calls from within this function

**Step 5: Convert `run_daily_pipeline()` from bool to dict (ei_main.py)**

Three sub-tasks: snapshots, calculations, expected moves.

- Capture all 3 component return dicts (already captured in local variables)
- Track timing per sub-task (already tracked)
- Build and return the contract dict per RETURN_DICT_CONTRACTS.md section 1.1
- Include `alert_details` from the expanded `update_expected_moves()` return (Step 1)
- Remove `handle_error()` calls from within this function

**Step 6: Update orchestrator methods (main_runners.py)**

For each of the 3 methods, the pattern is the same:

1. Change from `success = run_*()` to `result = run_*()`
2. Change the success check from `if success:` to `if result.get('success'):` (or `if result['success']:`)
3. Remove the DB queries that follow the strategy call (the `SELECT COUNT(*)` blocks)
4. Build the completion box content from `result` fields instead of DB query results
5. On failure, pass `result` as context to `queue_error()` instead of bare exception strings
6. Keep the outer `try/except` as a safety net — build a failure dict in the except block

**For `run_earnings_morning_scan()`:**
- Remove the `SELECT COUNT(*)` queries that follow `run_morning_scan()` in the success branch
- Completion box: `"Opportunities found: {}"`.format(result['opportunities_found']), `"High-quality plays: {}"`.format(result['high_quality'])

**For `run_earnings_weekly_refresh()`:**
- Remove the `SELECT COUNT(*)` queries that follow `run_weekly_refresh()` in the success branch
- Completion box: `"Earnings fetched: {}"`.format(result['earnings_found']), `"Events archived: {}"`.format(result['events_archived']), `"Upcoming earnings: {}"`.format(result['upcoming_count'])
- Note: The current "Archived events" shows total all-time count (misleading). The new `events_archived` from the return dict shows THIS RUN's count (correct).

**For `run_earnings_pipeline()`:**
- Remove the large DB query block that follows `run_daily_pipeline()` in the success branch (queries `earnings_snapshots`, `earnings_moves`, `earnings_upcoming`)
- Completion box: use `result['snapshots_created']`, `result['moves_calculated']`, `result['alerts_triggered']`
- Alert detail display: iterate `result.get('alert_details', [])` for the top-5 symbols breakdown

### Verification

1. **Run morning scan:** `python strategies/earnings_intel/ei_main.py --morning-scan --no-interaction` — should complete without errors, no celebrations or phase headers from EI.
2. **Run weekly refresh:** `python strategies/earnings_intel/ei_main.py --weekly-refresh --no-interaction` — same.
3. **Run daily pipeline:** `python strategies/earnings_intel/ei_main.py --daily-pipeline --no-interaction` — same.
4. **Check return types:** Add a temporary `print(type(result), result.keys())` in each orchestrator method to confirm dicts are flowing through. Remove after verification.
5. **Grep check:** `grep -rn "SELECT COUNT.*earnings" main_runners.py` — should return zero matches (all DB queries removed).

---

## Package 2: EI Visual Cleanup

**Goal:** Remove all beautification functions, visual output, and direct autofix calls from `ei_main.py` and its component files.

**Estimated scope:** ~150 lines deleted across 6-7 files.

**Dependencies:** Package 1 must be complete. (The visual output is currently the only user feedback for EI runs. Once the orchestrator uses the return dicts for completion boxes, the strategy-side output becomes redundant and can be safely removed.)

**Files modified:**
- `strategies/earnings_intel/ei_main.py` — delete formatting functions, remove visual output
- `strategies/earnings_intel/ei_arbitrage_scanner.py` — remove `_display_opportunities()` banners, `_log_summary()` separators
- `strategies/earnings_intel/ei_fetch_upcoming.py` — remove `_log_summary()` separators
- `strategies/earnings_intel/ei_snapshot_collector.py` — remove `_log_summary()` separators
- `strategies/earnings_intel/ei_post_earnings_calc.py` — remove `_log_summary()` separators
- `strategies/earnings_intel/ei_moves_upcoming.py` — remove startup/completion banners

**Files read-only (reference):**
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md` — what strategies ARE allowed to produce (progress lines, inline warnings)
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_AUDIT.md` section 4 — complete violation inventory for EI

**Do NOT touch:** Return values (those were fixed in Package 1). Component business logic. main_runners.py.

### Steps

**Step 1: Delete formatting functions from ei_main.py**

Delete these 8 functions from the `CONSOLE LOGGING FUNCTIONS` section near the top of the file:
- `safe_log()`
- `colorize()`
- `beautiful_log()`
- `create_phase_header()`
- `create_progress_box()`
- `create_success_celebration()`
- `create_error_box()`
- `log_pipeline_start()`

**Step 2: Replace all calls to deleted functions in ei_main.py**

Sub-phase elements are a third visual layer (see `VISUAL_DESIGN_REFERENCE.md` Section 15). The philosophy is smart logging: keep useful structure, remove redundancy, fix output channels.

Search for every call to the above functions in `ei_main.py`. For each:

**KEEP (convert `safe_log()` → `logging.info()`):**
- `[1/3] Task Name` progress markers (e.g., `📸 [1/3] Collecting IV/price snapshots...`) → **keep as `logging.info("  [1/3] Collecting IV/price snapshots...")`**
- Tree diagram intros for each mode (e.g., `├─ Fetch upcoming earnings`, `└─ Cleanup old records`) → **keep as `logging.info("   ├─ Fetch upcoming earnings (next 90 days)")`**
- Per-task confirmation one-liners (e.g., `✅ Fetched 42 earnings for 800 symbols`) → **keep as `logging.info()`**
- Inline warnings about failures → **keep as `logging.warning("...")`**

**DELETE:**
- `create_phase_header("📅 WEEKLY REFRESH MODE", now)` and similar mode headers → redundant with orchestrator mission box
- `create_success_celebration("WEEKLY REFRESH", accomplishments)` and similar → redundant with orchestrator completion box
- `create_error_box("Weekly refresh completed with errors")` → replace with `logging.error()`
- `log_pipeline_start("Weekly Refresh", [...])` → redundant with orchestrator mission box
- `"=" * 60` / `"=" * 70` separator lines in `run_all_mode()` → delete

**Step 3: Remove `handle_error()` calls from ei_main.py**

These were identified in Package 1 but NOT removed there (Package 1 focused on dict returns). Remove the `handle_error()` calls in the coordinator functions. The orchestrator now handles error routing via the return dict.

Remove the `from tools.autofix import handle_error` import if it becomes unused.

**Step 4: Remove banners and `_log_summary()` from component files**

For each component file, find and remove:
- `"=" * N` separator lines
- "COMPLETE", "SUCCESS", "SUMMARY" announcement blocks
- Startup banners with configuration displays
- Keep: actual progress lines (`"Processing symbol X..."`, `"Progress: N/M"`)

| File | What to remove |
|------|---------------|
| `ei_arbitrage_scanner.py` | `_display_opportunities()` banner, `_log_summary()` separators |
| `ei_fetch_upcoming.py` | `_log_summary()` separators, startup banner |
| `ei_snapshot_collector.py` | `_log_summary()` separators, startup banner |
| `ei_post_earnings_calc.py` | `_log_summary()` separators (line 680 def, line 111 call) |
| `ei_moves_upcoming.py` | Startup banner, completion announcements |

**Note on `_log_summary()`:** These functions compute summary data AND display it. If the summary data is needed for the return dict, extract the computation into the return dict and delete the display. If the return dict already has the data (it should after Package 1), just delete the whole function.

### Verification

1. **Grep check:** `grep -rn "beautiful_log\|create_phase_header\|create_success_celebration\|create_error_box\|create_progress_box\|safe_log\|log_pipeline_start" strategies/earnings_intel/` — should return zero matches.
2. **Grep check:** `grep -rn "handle_error" strategies/earnings_intel/ei_main.py` — should return zero matches.
3. **Grep check:** `grep -rn '"=" \* [0-9]' strategies/earnings_intel/` — should return zero matches (no `"=" * 60` separator lines).
4. **Import check:** Verify `ei_main.py` still runs: `python strategies/earnings_intel/ei_main.py --morning-scan --no-interaction` — should show only progress lines, no boxes/banners/celebrations.

---

## Package 3: OP Visual Cleanup

**Goal:** Remove beautification functions and completion banners from the Option Pipeline. Data flow is already correct — this is visual-only cleanup.

**Estimated scope:** ~120 lines deleted across 4 files.

**Dependencies:** None (OP already returns correct dicts; orchestrator already uses them).

**Files modified:**
- `strategies/option_pipeline/op_main.py` — delete formatting functions, remove visual output
- `strategies/option_pipeline/op_collector.py` — remove completion banner
- `strategies/option_pipeline/op_symbol_rollup.py` — remove completion banner
- `strategies/option_pipeline/op_timing_calculator.py` — remove completion markers and backfill banner

**Files read-only (reference):**
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_AUDIT.md` section 3 — OP violation inventory
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md` — what strategies are allowed to produce

**Do NOT touch:** Return values (already correct). main_runners.py (already reads from dicts).

### Steps

**Step 1: Delete formatting functions from op_main.py**

Delete these 6 functions from the formatting section near the top of the file:
- `safe_log()`, `create_phase_header()`, `create_progress_box()`, `create_success_celebration()`, `create_error_box()`, `log_pipeline_start()`

**Step 2: Replace all calls in op_main.py**

Sub-phase elements are a third visual layer (see `VISUAL_DESIGN_REFERENCE.md` Section 15). The philosophy is smart logging: keep useful structure, remove redundancy, fix output channels.

**KEEP (convert `safe_log()` → `logging.info()`):**
- Sub-phase headers: `create_phase_header("📊 PHASE 1: DATA COLLECTION", ...)` → inline as `logging.info("── 📊 DATA COLLECTION (1/4) ──...")`
- Tree diagram intros: `create_progress_box()` calls with `├─` / `└─` descriptions → inline as `logging.info("   ├─ Calculating Put/Call ratios")` etc.
- Inline sub-phase completion summaries (Pattern A in VISUAL_DESIGN_REFERENCE.md Section 15.3): the `logging.info("✅ OI timing analysis completed...")` tree blocks → **KEEP as-is** (already uses `logging.info()`)
- Per-item progress lines and batch summaries → **KEEP as-is**

**DELETE:**
- `create_success_celebration("OPTION PIPELINE", accomplishments)` — the final pipeline summary is redundant with the orchestrator completion box
- `log_pipeline_start()` call — redundant with orchestrator mission box
- Startup banner (`"=" * 70` block in `main()`) — only used in standalone CLI mode
- Final success/failure print statements in `main()` — only used in standalone CLI mode
- `_log_pipeline_summary()` method — produces Pattern D (final celebration), redundant with orchestrator completion box

**Step 3: Remove `═══` borders from component completion summaries, KEEP metric content**

Sub-phase completion summaries are useful diagnostic output (see `VISUAL_DESIGN_REFERENCE.md` Section 15.3). The `═══` borders are the violation — the content stays.

| File | What to REMOVE | What to KEEP (as `logging.info()`) |
|------|---------------|-----------------------------------|
| `op_collector.py` | `"=" * 70` border lines (2 lines), `"🎉 COLLECTION COMPLETE"` banner title | The 6 metric lines (Time, Symbols Processed, Successful, Failed, Total Contracts, API Calls) — strip leading emoji, output as plain `logging.info()` |
| `op_symbol_rollup.py` | `"=" * 60` separator lines (3 lines), `"OP ROLLUP COMPLETE: ..."` title line | Stats lines (Total symbols, Symbols processed, Symbols with data, Summaries created, Errors, Processing time) — already `logging.info()` |
| `op_timing_calculator.py` | `[OK]` completion marker (line 160) | The inline tree summary (`├─ Total contracts processed: ...`) is already in `op_main.py` and uses `logging.info()` — keep it. If `BACKFILL COMPLETE` exists (line 200), delete the banner line only. |

Keep: Progress logging lines (e.g., progress counters showing `N/M symbols`). These are the correct strategy output.

### Verification

1. **Grep check:** `grep -rn "safe_log\|create_phase_header\|create_success_celebration\|create_error_box\|create_progress_box\|log_pipeline_start" strategies/option_pipeline/` — zero matches.
2. **Grep check:** `grep -rn '"=" \* [0-9]\|COLLECTION COMPLETE\|ROLLUP COMPLETE' strategies/option_pipeline/` — zero matches (no banners remain).
3. **Smoke test:** `python strategies/option_pipeline/op_main.py --no-interaction` — should show only progress lines, return dict at the end.

---

## Package 4: FM Pre-Market Dict Return

**Goal:** Convert `run_pre_market()` from `bool` to structured dict return. Update the orchestrator to use it.

**Estimated scope:** ~40 lines changed across 2 files.

**Dependencies:** None.

**Files modified:**
- `strategies/flow_monitor/fm_main.py` — `run_pre_market()` function only
- `main_runners.py` — `run_flow_monitor()` pre-market section only

**Files read-only (reference):**
- `docs/main_orchestrator_refactor/RETURN_DICT_CONTRACTS.md` section 3.2 — contract spec
- `strategies/flow_monitor/fm_alert_resolver.py` — verify component return dicts

**Do NOT touch:** `run_market_hours()` (already returns dict). `run_post_market()` (that's Package 5). FM visual output (that's Package 6).

### Steps

**Step 1: Convert `run_pre_market()` in fm_main.py**

- Capture `resolution_stats` from `fm_alert_resolver.resolve_yesterday_alerts()`
- Capture `sentiment_stats` from `fm_alert_resolver.update_watchlist_sentiment()`
- Instead of returning `True`/`False`, build and return the contract dict:

```python
return {
    'success': True,
    'duration_seconds': time.time() - start_time,
    'sub_tasks': {
        'alert_resolution': {
            'success': True,
            'alerts_resolved': resolution_stats.get('alerts_resolved', 0),
            'building': resolution_stats.get('building', 0),
            'closing': resolution_stats.get('closing', 0),
            'neutral': resolution_stats.get('neutral', 0),
            'not_found': resolution_stats.get('not_found', 0),
        },
        'sentiment_update': {
            'success': True,
            'symbols_updated': sentiment_stats.get('symbols_updated', 0),
        },
    },
    'alerts_resolved': resolution_stats.get('alerts_resolved', 0),
    'symbols_updated': sentiment_stats.get('symbols_updated', 0),
}
```

On failure: `{'success': False, 'failure_reason': str(e), ...}` with zeros.

**Step 2: Update orchestrator (main_runners.py `run_flow_monitor()`)**

Find where `pre_market_success` is set from `run_pre_market()`. Change to capture the dict. Use it in the FM completion box to show actual pre-market metrics (alerts resolved, symbols updated) instead of just a success/fail flag.

### Verification

1. **Type check:** Temporarily add `print(type(pre_market_result))` in the orchestrator — confirm it's `dict`.
2. **Content check:** Confirm the completion box shows "Alerts resolved: N" instead of just "Pre-Market: Success".

---

## Package 5: FM Post-Market Research + Dict Return

**Goal:** Trace FM post-market inner component return values, convert the 4 bool-returning wrapper functions to return dicts, then convert `run_post_market()` itself to return a structured dict.

**Estimated scope:** ~150 lines changed across 1-2 files. Research phase required first.

**Dependencies:** None (but logically benefits from Package 4 being done first, for pattern consistency).

**Files modified:**
- `strategies/flow_monitor/fm_main.py` — `run_post_market()` and its 4 inner `run_*()` wrapper functions

**Files read-only (reference — research targets):**
- `docs/main_orchestrator_refactor/RETURN_DICT_CONTRACTS.md` section 3.4 — contract spec with known gaps
- `strategies/flow_monitor/fm_backfill_handler.py` — trace what `run_daily_backfill()` returns
- `strategies/flow_monitor/fm_market_regime_summary.py` — subprocess, exit code only
- `strategies/flow_monitor/fm_symbol_rollup.py` — trace what `run_daily_rollup()` returns
- `strategies/flow_monitor/fm_daily_evaluation.py` — trace what `run_daily_evaluation()` returns
- `strategies/flow_monitor/fm_watchlist.py` — `archive_expired_entries()` already returns dict

**Do NOT touch:** `run_pre_market()` (Package 4). `run_market_hours()` (already correct). FM visual output (Package 6).

### Steps

**Step 1: Research — trace inner component returns**

The contracts doc flags 4 of 5 post-market sub-tasks as returning `bool` with "would need deeper trace." Before implementing, read each component module and document what data is available:

- `fm_backfill_handler.run_daily_backfill()` — what does it compute? Does it return a dict that the wrapper discards, or does it truly only return bool?
- `fm_symbol_rollup.run_daily_rollup()` — same question
- `fm_daily_evaluation.run_daily_evaluation()` — same question
- `fm_market_regime_summary.py` — subprocess, confirm exit code is the only signal

For each, document: current return type, what metrics are available, what the wrapper discards.

**Step 2: Convert inner wrapper functions**

For each of the 4 `run_*_task()` wrappers in `run_post_market()`:
- If the component already returns a dict: pass it through (add `success`, `duration_seconds`)
- If the component returns bool: check if it has stats attributes (like `op_collector.collection_stats`). If so, read them. If not, return a minimal `{success, duration_seconds}` dict.
- `fm_market_regime_summary.py` is a subprocess: `{success, duration_seconds}` is all we can get.

**Step 3: Convert `run_post_market()` to return dict**

Aggregate all 5 sub-task results into the contract dict per RETURN_DICT_CONTRACTS.md section 3.4. Remove DB queries used for diagnostic logging (the `SELECT COUNT(DISTINCT symbol)` and `SELECT COUNT(*)` queries after each task) — those metrics should come from the return dicts.

**Step 4: Update orchestrator**

In `run_flow_monitor()`, change from `post_market_success = run_post_market(...)` to `post_market_result = run_post_market(...)`. Use the dict for the FM completion box.

### Verification

1. **Research output:** Before implementing, write a brief comment at the top of each changed function documenting what the component returns (this aids future maintenance).
2. **Type check:** `print(type(post_market_result))` in orchestrator — confirm dict.
3. **Smoke test:** If possible, run `python strategies/flow_monitor/fm_main.py --post-market --no-interaction` and verify no crashes. (May require specific time-of-day conditions.)

---

## Package 6A: FM Formatting Functions + Coffee Break Rewrite

**Goal:** Delete the 9 beautification/formatting function definitions from the top of `fm_main.py` and rewrite `coffee_break()` to use the standard `create_status_box()` from `log_utils.py`. This is the prerequisite for all other FM visual cleanup — the formatting functions must be gone before the call sites can be triaged.

**Estimated scope:** ~120 lines deleted + ~30 lines rewritten in 1 file.

**Dependencies:** Package 0 must be complete. (Package 0 adds daily state persistence to `fm_session_stats.py` which 6A must not conflict with.)

**Files modified:**
- `strategies/flow_monitor/fm_main.py` — top-of-file formatting functions + `coffee_break()` rewrite

**Files read-only (reference):**
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md` — delegated orchestrator rules (section on FM market hours)
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_AUDIT.md` section 2 — FM violation inventory
- `strategies/flow_monitor/fm_session_stats.py` — **exemplary file**, modified by Package 0 (daily state persistence methods added). Do not make additional changes in this package.

**Do NOT touch:** `fm_session_stats.py` (modified by Package 0). `fm_watchlist.py`. `fm_baseline_generator.py`. Return values (fixed in Packages 4-5). `main_runners.py`. Any call sites to `beautiful_log()`, `safe_log()`, etc. — those are triaged in Packages 6B/6C/6D.

### fm_main.py Structure Map (shared reference for all 6x packages)

Before starting, understand the file layout (1,818 lines total). Read the file to confirm these sections — the descriptions are authoritative, not the exact boundaries:

| Section | beautiful_log | safe_log | Action (which package) |
|---------|:---:|:---:|--------|
| 11 formatting/utility function definitions (top of file, after imports) | — | — | DELETE all except `get_dynamic_symbol_count()` and `get_api_budget_info()` (verify callers first) — **6A** |
| `coffee_break()` + `contextual_coffee_break()` | 0 | 2 | REWRITE `coffee_break()` to use `create_status_box`, DELETE `contextual_coffee_break()` — **6A** |
| `run_subprocess_task()` | 0 | 8 | KEEP (utility), convert safe_log → logging — **6B** |
| `run_historical_backfill()` | 9 | 0 | Triage per guide — **6B** |
| `run_quick_sync()` | 14 | 0 | Triage per guide — **6B** |
| Logging setup, diagnostics | 0 | 4 | KEEP (infrastructure) — **6B** |
| `safe_log()` definition + utility functions | — | — | DELETE `safe_log()` definition — **6B** |
| `run_symbol_rollup_task()` | 0 | 3 | Convert safe_log → logging — **6B** |
| `run_market_regime_task()` | 0 | 2 | Convert safe_log → logging — **6B** |
| `run_daily_evaluation_task()` | 0 | 5 | Convert safe_log → logging — **6B** |
| `run_pre_market()` | 13 | 0 | Triage per guide — **6B** |
| `run_market_hours()` | 24 | 0 | MOST CRITICAL — see detailed guide — **6C** |
| `run_post_market()` | 22 | 0 | Triage per guide — **6B** |

### Steps

**Step 1: Delete formatting functions from fm_main.py**

Find the `BEAUTIFICATION FUNCTIONS` section near the top of the file (after imports). Delete these 9 functions entirely:

| Function | What it does (for identification) |
|----------|----------------------------------|
| `get_display_settings()` | Caches config dict with `use_emoji`, `use_colors`, `verbosity_level` |
| `colorize()` | Wraps text in raw ANSI escape codes (`\033[91m` etc.) |
| `beautiful_log()` | Routes message through `colorize()` then `safe_log()` |
| `create_phase_header()` | Prints `"── phase_name ──"` via safe_log |
| `create_task_box()` | Prints single line `"Task N/M: name — purpose"` via safe_log |
| `create_error_box()` | Prints `"ERROR: message"` via safe_log |
| `create_success_celebration()` | Prints `"pipeline_name complete:"` + accomplishment lines via safe_log |
| `create_section_divider()` | Prints `"─" * 60` or titled divider via beautiful_log |
| `contextual_coffee_break()` | Draws a custom `┌─┐│├└` box with context-aware coffee break messages |

Also check `get_dynamic_symbol_count()` and `get_api_budget_info()` — if their ONLY callers are the deleted formatting functions, delete them too. If they have callers in `run_market_hours()` or other kept code, leave them.

**Step 2: Rewrite `coffee_break()` to use standard formatting**

The current `coffee_break()` calls the now-deleted `contextual_coffee_break()` and `beautiful_log()`. Rewrite it to use `create_status_box` from `log_utils.py` while preserving:
- The context-aware messages (backfill_complete, sync_complete, etc.)
- The interruptible sleep with `shutdown_event` checking
- The "Up Next" task info
- The visible box output (Ben wants coffee breaks to remain visually present)

```python
def coffee_break(duration=60, message="Taking a coffee break", context='default', next_task=None):
    """Timed pause with visual feedback using standard log_utils formatting"""
    from tools.log_utils import create_status_box

    context_messages = {
        'backfill_complete': "Data refreshed — all symbols have current pricing",
        'backfill_partial': "Data partially refreshed — some symbols failed",
        'rollup_complete': "Symbol analysis complete — daily metrics calculated",
        'pre_evaluation': "Running performance evaluation",
        'task_complete': "Task complete",
        'tasks_complete': "All daily tasks completed successfully",
        'pipeline_transition': "Pipeline complete — preparing for next phase",
        'sync_complete': "Query DB synced",
        'default': "Quick coffee break"
    }
    msg = context_messages.get(context, context_messages['default'])

    lines = [msg, "Duration: {} seconds".format(duration)]
    if next_task:
        lines.append("Up Next: {}".format(next_task))
    create_status_box("☕ Coffee Break", lines)

    # Interruptible sleep - check shutdown every 5 seconds
    for i in range(duration // 5):
        if shutdown_event.is_set():
            logging.info("Coffee break interrupted - shutting down gracefully")
            break
        time.sleep(5)
    remaining = duration % 5
    if remaining > 0 and not shutdown_event.is_set():
        time.sleep(remaining)
```

**IMPORTANT:** After this rewrite, all existing `coffee_break()` calls throughout fm_main.py continue to work — same function signature, same behavior, just rendered through the standard channel. Do NOT replace `coffee_break()` calls with `time.sleep()`.

**Note:** This is a different function from the orchestrator's `self.coffee_break(seconds, context)` in `main_ui.py` (rewritten in Package 0 Step 4). FM's version is a module-level function with its own signature `(duration, message, context, next_task)` and its own interruptible sleep logic using `shutdown_event`. They serve the same visual purpose but are independent implementations in different files — don't confuse them.

### Verification

1. **Grep check:** `grep -rn "def get_display_settings\|def colorize\|def beautiful_log\|def create_phase_header\|def create_task_box\|def create_error_box\|def create_success_celebration\|def create_section_divider\|def contextual_coffee_break" strategies/flow_monitor/fm_main.py` — zero matches (all 9 function definitions deleted).
2. **Coffee break check:** `grep -rn "create_status_box" strategies/flow_monitor/fm_main.py` — at least 1 match (in the rewritten `coffee_break()`).
3. **Coffee break callers check:** `grep -rn "coffee_break(" strategies/flow_monitor/fm_main.py` — should show the rewritten function definition and its callers. Verify callers still pass valid `context=` values.
4. **Import check:** `python -c "from strategies.flow_monitor.fm_main import run_pre_market, run_market_hours, run_post_market; print('OK')"` — should succeed. (Note: `beautiful_log()` etc. call sites still exist but will fail at runtime — that's expected until 6B/6C/6D complete the triage.)

---

## Package 6B: FM Function-Level Triage (Pre/Post-Market + Utilities)

**Goal:** Triage all `beautiful_log()` and `safe_log()` calls in fm_main.py's non-market-hours functions: `run_historical_backfill()`, `run_quick_sync()`, `run_subprocess_task()`, utility task wrappers, `run_pre_market()`, and `run_post_market()`. Delete the `safe_log()` definition. Remove `handle_error()` from post-market.

**Estimated scope:** ~100 lines deleted/modified in 1 file.

**Dependencies:** Packages 4, 5, and 6A must be complete. (Pre-market and post-market need dict returns from Packages 4/5 before their visual output can be safely removed. 6A must have deleted the formatting function definitions.)

**Files modified:**
- `strategies/flow_monitor/fm_main.py` — non-market-hours functions only

**Files read-only (reference):**
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md`
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_AUDIT.md` section 2
- `docs/main_orchestrator_refactor/VISUAL_DESIGN_REFERENCE.md` Section 15 (sub-phase elements)

**Do NOT touch:** `run_market_hours()` (that's Package 6C). FM component files (that's Package 6D). `fm_session_stats.py`. `main_runners.py`.

### Steps

**Step 3: `run_historical_backfill()` — 9 beautiful_log calls**

Find each `beautiful_log()` call in this function and triage:

| Content pattern | Action |
|----------------|--------|
| `"Starting historical backfill..."` | **DELETE** — redundant with caller context |
| `"Checking for symbols needing backfill..."` | **DELETE** — operational noise |
| `"Found N symbols needing backfill"` | **KEEP as `logging.info()`** — actionable info |
| `"Processing batch N/M..."` | **KEEP as `logging.info()`** — progress |
| `"Backfill complete for SYMBOL"` | **DELETE** — per-symbol noise (the progress counter suffices) |
| `"Coffee break between batches..."` | **DELETE** — the `coffee_break()` call itself provides the visual |
| `"Historical backfill complete"` | **DELETE** — completion announced by caller |
| Error-path logging | **KEEP as `logging.error()`** |

**Step 4: `run_quick_sync()` — 14 beautiful_log calls**

Most of these are legitimate operational logging (fetching symbols, API status). Apply the same triage:

| Content pattern | Action |
|----------------|--------|
| `"Starting quick sync..."` / `"Quick sync complete"` | **DELETE** |
| `"Fetching N symbols..."`, `"API budget: N calls remaining"` | **KEEP as `logging.info()`** |
| Per-symbol progress lines | **KEEP as `logging.info()`** |
| Coffee break announcements | **DELETE** — the `coffee_break()` call provides the visual |
| Error-path logging | **KEEP as `logging.error()`** |

**Step 5: Delete `safe_log()` definition and convert all calls**

`safe_log()` is an enhanced print with UTF-8 fallback. All 46 calls to `safe_log()` throughout the file should be converted:

| Current | Replacement |
|---------|------------|
| `safe_log("message")` | `logging.info("message")` |
| `safe_log("WARNING: ...", level='warning')` | `logging.warning("...")` |
| `safe_log("ERROR: ...", level='error')` | `logging.error("...")` |

Note: `safe_log()` in fm_main.py does NOT take a `level` parameter — it always prints. So all calls convert to `logging.info()` unless the message text clearly indicates a warning or error.

The `safe_log()` function definition can be deleted after all calls are converted. If it's imported by other FM files, check those files too — but it's likely only used within `fm_main.py`.

**Step 6: `run_pre_market()` — 13 beautiful_log calls**

After Package 4, this function returns a dict. Most visual output becomes redundant with the orchestrator completion box. However, pre-market has 2 sub-tasks (alert resolution + sentiment update) that benefit from lightweight progress lines.

| Content pattern | Action |
|----------------|--------|
| `create_phase_header("PRE-MARKET PREPARATION", now)` | **DELETE** — redundant with orchestrator mission box |
| `"🌅 PRE-MARKET PREPARATION - Flow Monitor system ready"` | **DELETE** — redundant with mission box |
| `"⚡ Market hours monitoring will begin at 9:30 AM"` | **DELETE** — redundant with mission box |
| `"🔍 TASK 0: Resolving Yesterday's Flow Alerts"` | **KEEP as `logging.info()`** — sub-phase progress marker |
| `"Using fresh OI data from morning Option Pipeline"` | **KEEP as `logging.info()`** — context |
| `"✅ Resolved N alerts (N BUILDING, N CLOSING, N NEUTRAL)"` | **KEEP as `logging.info()`** — diagnostic detail (also in return dict, but useful as real-time progress) |
| `"⚠️ N contracts not found in today's OI data"` | **KEEP as `logging.warning()`** |
| `"✅ Resolution data synced to query database"` | **KEEP as `logging.info()`** — confirmation |
| `"✅ Updated sentiment for N watchlist symbols"` | **KEEP as `logging.info()`** — confirmation |
| `create_success_celebration("PRE-MARKET SETUP COMPLETE", accomplishments)` | **DELETE** — redundant with orchestrator completion box |
| `create_error_box("PRE-MARKET SETUP FAILED")` | **DELETE** — orchestrator handles failure box |
| Error-path logging | **KEEP as `logging.error()`** |

After this step, `run_pre_market()` should emit ~3-5 compact progress lines during execution, then return a dict for the orchestrator to build the completion box.

**Step 8: `run_post_market()` — 22 beautiful_log calls, 5 handle_error calls**

Sub-phase elements are a third visual layer (see `VISUAL_DESIGN_REFERENCE.md` Section 15). FM post-market has 5 internal tasks that benefit from lightweight progress structure.

| Category | Action |
|----------|--------|
| `create_phase_header("POST-MARKET ANALYSIS", now)` | **DELETE** — redundant with orchestrator mission box |
| `"🌆 INITIATING POST-MARKET ANALYSIS PIPELINE"` | **DELETE** — redundant with orchestrator mission box |
| Per-task `"💾 Running historical data backfill first..."` etc. | **KEEP as `logging.info()`** — these are sub-phase progress markers (1 line per task, useful signal of what's running) |
| Per-task `"✅ [task] complete"` confirmations | **KEEP as `logging.info()`** — compact confirmation lines. However, if Package 5 moves these metrics into the return dict AND the orchestrator renders per-sub-task boxes, then delete to avoid duplication. **Ask Ben** if unsure. |
| Per-task metric displays (e.g., `"Market Regime: elevated \| Bull \| SPY +0.5%"`) | **KEEP as `logging.info()`** — information-dense, not redundant. Delete only the DB queries that fetch the data (Package 5 puts it in the return dict). |
| `coffee_break()` calls between tasks | **KEEP** — these produce visual output via the rewritten function (Step 2 in 6A) |
| DB diagnostic queries (the `SELECT` blocks after each task) | **DELETE** — metrics come from return dict now (Package 5) |
| `create_success_celebration("POST-MARKET PIPELINE", accomplishments)` | **DELETE** — redundant with orchestrator completion box |
| `create_error_box("POST-MARKET PIPELINE HAD FAILURES...")` | **DELETE** — replace with orchestrator failure box |
| `handle_error()` calls (1 CRITICAL + 3 ERROR + 1 WARNING) | **DELETE** — orchestrator routes via return dict |
| Error-path logging in except blocks | **KEEP as `logging.error()`** |

**Note on handle_error in post-market vs market hours:** Post-market's 5 `handle_error()` calls should be REMOVED because post-market returns a dict (Package 5) and the orchestrator does the error routing. Market hours' 4 `handle_error()` calls should be KEPT because market hours runs as a long-lived subprocess where errors must be handled immediately.

### Verification

1. **Grep check:** `grep -rn "safe_log" strategies/flow_monitor/fm_main.py` — zero matches (definition deleted + all calls converted).
2. **Grep check:** `grep -rn "beautiful_log" strategies/flow_monitor/fm_main.py` — matches should ONLY be in `run_market_hours()` (those are triaged in Package 6C). Zero matches in any other function.
3. **handle_error check:** `grep -rn "handle_error" strategies/flow_monitor/fm_main.py` — should return EXACTLY 4 matches, all in `run_market_hours()` (post-market's 5 calls removed, market hours' 4 kept).
4. **Import check:** `python -c "from strategies.flow_monitor.fm_main import run_pre_market, run_post_market; print('OK')"` — should succeed.

---

## Package 6C: FM Market Hours Triage

**Goal:** Triage the 24 `beautiful_log()` calls in `run_market_hours()` — the most critical section of FM. This function runs for 6+ hours as a delegated orchestrator and SHOULD produce per-cycle operational output, but the current output is too verbose.

**Estimated scope:** ~50 lines modified in 1 file.

**Dependencies:** Package 6A must be complete (formatting functions must be deleted first so we're converting to `logging.info()`, not to already-deleted helpers).

**Files modified:**
- `strategies/flow_monitor/fm_main.py` — `run_market_hours()` function only

**Files read-only (reference):**
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md` — delegated orchestrator rules (section on FM market hours)
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_AUDIT.md` section 2 — FM violation inventory
- `docs/main_orchestrator_refactor/VISUAL_DESIGN_REFERENCE.md` Section 10 (approved target output), Section 17 (per-call cross-check table)

**Do NOT touch:** Any function outside `run_market_hours()`. FM component files (that's Package 6D). `fm_session_stats.py`. `main_runners.py`.

### Steps

**Step 7: `run_market_hours()` — 24 beautiful_log calls — MOST CRITICAL**

This is the largest section and requires careful triage. FM market hours is a **delegated orchestrator** — it runs for 6+ hours and SHOULD produce per-cycle operational output. But the current output is too verbose.

**The performance breakdown is useful and stays:**
```
✅ Cycle 15 complete - Performance Breakdown:
   📊 Collection: 1222.9s
   🔍 Analysis: 22.4s
   🚨 Alerts: 1.8s
   🎯 Watchlist: 6.4s
   🔄 DB Sync: 99.6s (104,416 rows)
   ⏱️ Total: 1353.0s
```

**Action:** Keep this multi-line breakdown. Convert from `beautiful_log()`/`print()` to `logging.info()`. Do NOT condense to a single line.

**The real issues are redundancy and output channel, not volume:**
- Remove duplicate announcements (e.g., "collection complete" appearing in two formats)
- Remove pre-alert chatter that's repeated in the processing summary
- Remove DEBUG-prefixed lines logged at INFO level
- Convert all output to `logging.info()` / `logging.warning()` (no `beautiful_log()`, no raw `print()`)
- Strategy-owned `═══` banners get removed, but the **content** they wrap stays

See `VISUAL_DESIGN_REFERENCE.md` Section 10 for the full approved target output with line-by-line keep/cut decisions. See Section 17 for the complete per-call cross-check table mapping every `beautiful_log()` call to a verdict.

**Full triage for market hours:**

| Category | Action |
|----------|--------|
| Startup banner / `"MARKET HOURS BEGINNING"` + `"Real-time monitoring"` | **DELETE** |
| `create_phase_header("MARKET HOURS MONITORING")` | **DELETE** — redundant with orchestrator mission box |
| Per-cycle multi-line performance breakdown (`"✅ Cycle N complete"` + 6 metric lines) | **KEEP** — convert to `logging.info()` (see Section 10 of VISUAL_DESIGN_REFERENCE.md) |
| Every-10-cycle performance summary (`"📈 PERFORMANCE SUMMARY"` + 6 stat lines) | **KEEP** — convert to `logging.info()` |
| `"🔍 Collection complete: {ts} ({time}s)"` | **KEEP as `logging.info()`** — Section 10 explicitly keeps the emoji-prefixed one; the SECOND "collection complete" (if any from fm_collector) is the one that's redundant |
| DEBUG-prefixed lines at INFO level | **DELETE** (if found — not present in current code) |
| Cycle header `"=== Cycle N \| time \| symbols ==="` | **⚠️ ASK BEN** — Section 10 shows it in approved target, but this row previously said DELETE. See VISUAL_DESIGN_REFERENCE.md Section 17 for analysis. Recommend KEEP as visual separator for long logs, but strip `===` decoration (plain `logging.info()` format). |
| `"🔔 Market closed."` | **KEEP as `logging.info()`** — natural exit signal |
| `coffee_break()` calls between cycles | **KEEP** — these produce visual output via the rewritten function (6A Step 2) |
| API budget warnings (`"Low API budget"`) | **KEEP as `logging.warning()`** |
| Failure cluster warnings | **KEEP as `logging.warning()`** |
| `handle_error()` calls (4 total: 3 CRITICAL + 1 WARNING) | **KEEP** — FM is a subprocess, these ARE the error routing |
| End-of-day summary (`stats.format_end_of_day_lines()` loop) | **KEEP as `logging.info()`** — convert from beautiful_log |
| Symbol gaps file saved (`"Saved to {filename}"`) | **KEEP as `logging.info()`** — diagnostic |
| `"🏁 MARKET HOURS PIPELINE COMPLETE"` | **DELETE** — orchestrator handles completion |
| Error-path logging in except blocks (`"Collection failed"`, `"Market cycle error"`) | **KEEP as `logging.error()` / `logging.warning()`** |

**IMPORTANT on `handle_error()` in market hours:** There are 4 calls total — 3 with `severity='CRITICAL'` (zero alerts stored, collection failed, unexpected error) and 1 with `severity='WARNING'` (news enrichment failure). They exist because FM market hours runs as its own subprocess. Unlike pre/post-market (which return dicts to the orchestrator), market hours can't route errors through a return value during execution. All 4 `handle_error()` calls are correct and should be KEPT.

### Verification

1. **Grep check:** `grep -rn "beautiful_log" strategies/flow_monitor/fm_main.py` — zero matches in the entire file (6B handled non-market-hours, 6C handles market hours).
2. **handle_error check:** `grep -rn "handle_error" strategies/flow_monitor/fm_main.py` — should return EXACTLY 4 matches, all in `run_market_hours()` — 3 with `severity='CRITICAL'` and 1 with `severity='WARNING'` (news enrichment).
3. **Market hours output check:** Verify the multi-line performance breakdown is preserved (not condensed). Verify redundant duplicate lines are removed (see VISUAL_DESIGN_REFERENCE.md Section 10 keep/cut list).
4. **Cycle header decision:** The "Ask Ben" item about cycle header format (`=== Cycle N | time | symbols ===`) MUST be resolved before this package is marked complete. Flag it in Review Notes.

---

## Package 6D: FM Component Files Cleanup

**Goal:** Remove `"=" * N` separator lines, `print()` → `logging.info()` conversions, and decorative banners from all FM component files. Verify `safe_log()` is fully removed across the FM directory. Remove dead imports from `fm_main.py`.

**Estimated scope:** ~80 lines deleted/modified across 8 files.

**Dependencies:** Package 6A must be complete (safe_log must be deleted from fm_main before checking cross-file imports).

**Files modified:**
- `strategies/flow_monitor/fm_alerts.py` — alert display borders, `_log_alert_summary()` separators
- `strategies/flow_monitor/fm_analyzer.py` — `_log_analysis_summary()` `═══` banner removal
- `strategies/flow_monitor/fm_social_notifier.py` — queue alert box
- `strategies/flow_monitor/fm_collector.py` — convert `print()` to `logging.info()`
- `strategies/flow_monitor/fm_alert_resolver.py` — remove diagnostic separators
- `strategies/flow_monitor/fm_symbol_rollup.py` — remove `"=" * 60` separator and `"OP ROLLUP COMPLETE"` announcement
- `strategies/flow_monitor/evaluation/fm_evaluator.py` — remove `"=" * 50` separator
- `strategies/flow_monitor/fm_agent.py` — remove `"=" * 70` separators
- `strategies/flow_monitor/fm_main.py` — dead import cleanup only (Step 11)

**Files read-only (reference):**
- `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_AUDIT.md` section 2
- `docs/main_orchestrator_refactor/VISUAL_DESIGN_REFERENCE.md` Section 16 (alert display target mockup)

**Do NOT touch:** `fm_session_stats.py`. `fm_watchlist.py` (`"=" * 70` patterns are email body formatting, not console output). `fm_baseline_generator.py` (no violations — verified clean). `main_runners.py`.

### Steps

**Step 9: Clean up FM component files**

| File | What to remove |
|------|---------------|
| `fm_alerts.py` | `_display_alerts_to_console()`: Remove `"="*80` border lines and `"-"*N` category separators. Convert all `print()` to `logging.info()`. Keep emoji category headers (`🔴 HIGH CONVICTION`, `🟡 MEDIUM`, `⚪ LOW`), per-alert detail lines, and summary line. Use blank lines to separate categories. `_log_alert_summary()`: Remove `"="*50` borders. Keep stat lines as `logging.info()`. See VISUAL_DESIGN_REFERENCE.md Section 16 for the full target mockup. **⚠️ ASK BEN** if he prefers to keep the alert display borders for visual prominence — this is easy to reverse. |
| `fm_analyzer.py` | `_log_analysis_summary()`: Remove `"="*60` border lines around `UNIFIED ALGORITHM ANALYSIS SUMMARY`. Keep all stat lines as `logging.info()`. The content (contracts processed, statistics tracking, data quality, filter counts, conviction tiers, timing) stays — only the decorative borders are removed. |
| `fm_social_notifier.py` | `queue_alert_for_posting()` box (`═` box with `print()`). Keep CLI `print()` statements (acceptable for standalone use). |
| `fm_collector.py` | Convert ~10 `print()` startup/status messages to `logging.info()`. |
| `fm_symbol_rollup.py` | `"=" * 60` separator and `"OP ROLLUP COMPLETE"` announcement. Search for these patterns. |
| `fm_alert_resolver.py` | Diagnostic separators (`"="*60`). |
| `evaluation/fm_evaluator.py` | `"=" * 50` separator. Search for this pattern. |
| `fm_agent.py` | `"=" * 70` separators. Search for this pattern. |

**Step 10: Verify `safe_log()` is fully removed**

After all steps, search the entire `strategies/flow_monitor/` directory for `safe_log` references. If any FM component files import or call `safe_log` from `fm_main`, update those imports and calls too.

**Step 11: Remove dead imports**

After deleting formatting functions and `safe_log()`, check the import section at the top of `fm_main.py` for now-unused imports. The file currently does NOT import `colorama` or `shutil` — it uses raw ANSI codes in `colorize()`. Once `colorize()` is deleted, verify no other code depends on ANSI sequences.

**Note on `handle_error` import:** `fm_main.py` uses lazy imports (`from tools.autofix import handle_error` inside each function body), NOT a top-level import. Since market hours KEEPS 3 `handle_error()` calls, those inline imports stay. No top-level import cleanup needed for autofix.

### Verification

1. **Grep check:** `grep -rn "safe_log" strategies/flow_monitor/` — zero matches (including component files).
2. **Grep check:** `grep -rn '"="\s*\*\s*[0-9]\|"=" \* [0-9]\|"="\*[0-9]' strategies/flow_monitor/` — zero matches in non-Deprecated files. Note: fm_alerts.py uses `"="*50` (no spaces), so check both patterns. fm_watchlist.py `"=" * 70` patterns are email body content and should remain.
3. **Alert display decision:** The "Ask Ben" item about alert display borders MUST be resolved before this package is marked complete. Flag it in Review Notes.
4. **Import check:** `python -c "from strategies.flow_monitor.fm_main import run_pre_market, run_market_hours, run_post_market; print('OK')"` — should succeed.
5. **FM internal coffee breaks check:** Verify `coffee_break()` calls throughout fm_main.py use `create_status_box()` (via the rewrite in 6A).
6. **Full Phase 2 output check:** Verify output matches the mockup in VISUAL_DESIGN_REFERENCE.md "Full Phase 2 Example".

---

## Package 7: Utility Runner Polish

**Goal:** Minor cleanup of utility runner methods. Remove remaining filler, normalize simple contracts.

**Estimated scope:** ~30 lines across 1-2 files.

**Dependencies:** None (but lowest priority — do last).

**Files modified:**
- `main_runners.py` — utility method completion boxes only

**Do NOT touch:** Strategy files. Subprocess scripts.

### Steps

**Step 1: Normalize subprocess completion boxes**

For subprocess runners that can't return metrics, simplify boxes to show only what's honestly known:

```
Success/Fail status
Duration
```

No "Database secured", no "Performance optimized", no approximate counts.

**Step 2: Airline play method**

`run_airline_play_phase()` is nearly compliant — already reads from component dicts. Find and remove the 4 `beautiful_log` calls (search for `"Running airline tracking"`, `"Phase 1/2"`, `"Phase 2/2"`, `"Airline tracking phase completed"`). Ensure the completion box uses dict values (it likely already does).

**Step 3: Batch mode review**

`run_batch_mode_review()` — the intermediate "ERROR QUEUE" box is acceptable (shows what's about to be processed). Remove any duplicate announcements if present.

### Verification

1. **Grep check:** `grep -rn "Database secured\|Performance optimized\|Ready for.*operations\|~750\|4 SQL views" main_runners.py` — zero matches.

---

## Implementation Order Recommendation

For a single developer working sequentially:

```
 1. Package 0  (Orchestrator Cleanup)             — 30 min, immediate wins, builds confidence
 2. Package 1  (EI Dict Returns)                  — 2 hours, highest-impact data flow fix
 3. Package 2  (EI Visual Cleanup)                — 1 hour, depends on Package 1
 4. Package 3  (OP Visual Cleanup)                — 1 hour, independent
 5. Package 4  (FM Pre-Market Dict)               — 30 min, small and focused
 6. Package 5  (FM Post-Market Research)          — 2 hours, includes research phase
 7. Package 6A (FM Formatting + Coffee Break)     — 45 min, depends on Package 0
 8. Package 6B (FM Pre/Post-Market + Utilities)   — 1 hour, depends on 4, 5, 6A
 9. Package 6C (FM Market Hours Triage)           — 1 hour, depends on 6A (Ask Ben item)
10. Package 6D (FM Component Files Cleanup)       — 45 min, depends on 6A
11. Package 7  (Utility Polish)                   — 15 min, final polish
```

For parallel execution with multiple agents:

```
Batch A (parallel): Packages 0, 1, 3, 4, 5
Batch B (parallel): Packages 2, 6A          (after their dependencies complete)
Batch C (parallel): Packages 6B, 6C, 6D     (after 6A completes; 6B also needs 4+5)
Batch D: Package 7                           (final)
```

---

## Global Rules for All Packages

1. **Never add new visual output.** The goal is removal, not replacement. If something is deleted, it's deleted — don't replace a celebration block with a different celebration block. Exception: coffee breaks are CONVERTED to use `create_status_box()` — that's using the approved channel, not adding new output.

2. **Preserve actual progress lines.** `"Progress: 200/747 symbols (26.8%)"` stays. `"🎉 COLLECTION COMPLETE"` goes.

3. **Preserve error-path logging.** Lines in `except` blocks that log the exception should stay (convert to `logging.error()` if currently using `beautiful_log`). The orchestrator's safety net needs these.

4. **Test for import errors.** After deleting functions, run `python -c "import strategies.earnings_intel.ei_main"` (etc.) to verify nothing breaks at import time.

5. **Don't refactor business logic.** These packages change what functions RETURN and what they PRINT. They don't change what they DO. If you find a bug while working, note it and move on — don't fix it in the same change.

6. **Always read the actual code first.** This document describes what to look for by function name and content pattern, not by line number. Before making any change, read the function in question and verify the pattern matches. Code may have shifted since this document was written.
