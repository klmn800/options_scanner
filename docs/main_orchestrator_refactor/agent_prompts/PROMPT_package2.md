# Coding Agent Prompt — Package 2: EI Visual Cleanup

You are a coding agent working on a console output refactor for the options scanner system. Your job is to execute Package 2 — removing all beautification functions, visual output, and direct autofix calls from the Earnings Intelligence strategy files. Data flow is already correct (Package 1 converted EI to return dicts) — this is visual-only cleanup.

## Before You Start

Read these files in this order:
1. `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md` — target architecture (especially Coordinators section and what strategies ARE allowed to produce)
2. `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_AUDIT.md` — Section 4 (EI violation inventory)
3. `docs/main_orchestrator_refactor/VISUAL_DESIGN_REFERENCE.md` — Section 15 (Sub-Phase Structure) for what to keep
4. `docs/main_orchestrator_refactor/WORK_PACKAGES.md` — find Package 2 (4 steps)

Then read the actual source files:
- `strategies/earnings_intel/ei_main.py` — main target (formatting functions + call sites)
- `strategies/earnings_intel/ei_arbitrage_scanner.py` — banner removal
- `strategies/earnings_intel/ei_fetch_upcoming.py` — separator removal
- `strategies/earnings_intel/ei_snapshot_collector.py` — separator removal
- `strategies/earnings_intel/ei_post_earnings_calc.py` — separator removal
- `strategies/earnings_intel/ei_moves_upcoming.py` — banner removal

## What You're Doing

4 steps:

### Step 1: Delete formatting functions from ei_main.py

Delete these 8 functions from the `CONSOLE LOGGING FUNCTIONS` section near the top of the file:
- `safe_log()`
- `colorize()`
- `beautiful_log()`
- `create_phase_header()`
- `create_progress_box()`
- `create_success_celebration()`
- `create_error_box()`
- `log_pipeline_start()`

### Step 2: Replace all calls to deleted functions in ei_main.py

Search for every call to the above functions. For each:

**KEEP (convert to `logging.info()`):**
- `[1/3] Task Name` progress markers (e.g., `📸 [1/3] Collecting IV/price snapshots...`) → `logging.info("  [1/3] Collecting IV/price snapshots...")`
- Tree diagram intros for each mode (e.g., `├─ Fetch upcoming earnings`, `└─ Cleanup old records`) → `logging.info("   ├─ Fetch upcoming earnings (next 90 days)")`
- Per-task confirmation one-liners (e.g., `✅ Fetched 42 earnings for 800 symbols`) → `logging.info()`
- Inline warnings about failures → `logging.warning("...")`

**DELETE:**
- `create_phase_header("📅 WEEKLY REFRESH MODE", now)` and similar mode headers — redundant with orchestrator mission box
- `create_success_celebration("WEEKLY REFRESH", accomplishments)` and similar — redundant with orchestrator completion box
- `create_error_box("Weekly refresh completed with errors")` — replace with `logging.error()`
- `log_pipeline_start("Weekly Refresh", [...])` — redundant with orchestrator mission box
- `"=" * 60` / `"=" * 70` separator lines in `run_all_mode()` — delete

### Step 3: Remove `handle_error()` calls from ei_main.py

These were identified in Package 1 but NOT removed there. Remove the `handle_error()` calls in the coordinator functions. The orchestrator now handles error routing via the return dict.

Remove the `from tools.autofix import handle_error` import if it becomes unused.

### Step 4: Remove banners and `_log_summary()` from component files

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

## Rules

- Do NOT touch return values (already correct from Package 1)
- Do NOT touch main_runners.py (already reads from dicts)
- Do NOT change component business logic
- Keep progress logging lines (progress counters, per-symbol processing)
- All kept output should go through `logging.info()`, not `print()` or `safe_log()`

## Verification

1. `grep -rn "beautiful_log\|create_phase_header\|create_success_celebration\|create_error_box\|create_progress_box\|safe_log\|log_pipeline_start" strategies/earnings_intel/` — zero matches
2. `grep -rn "handle_error" strategies/earnings_intel/ei_main.py` — zero matches
3. `grep -rn '"=" \* [0-9]' strategies/earnings_intel/` — zero matches
4. `python -c "from strategies.earnings_intel.ei_main import run_morning_scan, run_weekly_refresh, run_daily_pipeline; print('OK')"` — succeeds
5. `[1/3]` step markers exist as `logging.info()` calls
6. `├─` tree diagram content exists as `logging.info()` calls

## When Done

Update `docs/main_orchestrator_refactor/PROGRESS_TRACKER.md`: set Package 2 status to `complete`, fill in Coding Notes.
