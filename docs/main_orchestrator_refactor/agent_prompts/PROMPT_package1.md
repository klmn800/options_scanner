# Coding Agent Prompt — Package 1: EI Dict Returns

You are a coding agent working on a console output refactor for the options scanner system. Your job is to execute Package 1 — converting Earnings Intelligence coordinator functions from `bool` to structured `dict` returns.

## Before You Start

Read these files in this order:
1. `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md` — target architecture (focus on Coordinators section and Return Dict patterns)
2. `docs/main_orchestrator_refactor/RETURN_DICT_CONTRACTS.md` — Section 1 (Earnings Intelligence) — exact dict specs for all 3 methods
3. `docs/main_orchestrator_refactor/WORK_PACKAGES.md` — find Package 1 (6 steps)

Then read the actual source files:
- `strategies/earnings_intel/ei_main.py` — the 3 coordinator functions you'll modify
- `strategies/earnings_intel/ei_moves_upcoming.py` — expand return dict (Step 1)
- `strategies/earnings_intel/ei_snapshot_collector.py` — verify component return dict
- `strategies/earnings_intel/ei_post_earnings_calc.py` — verify component return dict
- `strategies/earnings_intel/ei_arbitrage_scanner.py` — verify component return dict
- `strategies/earnings_intel/ei_fetch_upcoming.py` — verify component return dict
- `main_runners.py` — the 3 orchestrator methods you'll update

## What You're Doing

6 steps, execute in order:

1. **Expand `update_expected_moves()` return dict** (ei_moves_upcoming.py) — Add `alert_details` list with symbol, days_ahead, relative_underpricing_pct, signal. The data is already computed in the processing loop where `earnings_alert = 1` is set.

2. **Fix `events_analyzed` naming bug** (ei_main.py) — In `run_daily_pipeline()`, the coordinator uses `events_analyzed` but the component returns `events_ready`. Change references to match the component's actual key.

3. **Convert `run_morning_scan()` from bool to dict** (ei_main.py) — Easiest conversion. Component already returns everything. Build contract dict from `scan_results`. On failure, return `{'success': False, ...}`. Do NOT call `handle_error()` from coordinator.

4. **Convert `run_weekly_refresh()` from bool to dict** (ei_main.py) — Three sub-tasks: fetch (component dict), archive (cursor.rowcount), cleanup (cursor.rowcount). After all 3, query `SELECT COUNT(*) FROM earnings_upcoming WHERE earnings_date >= DATE('now')` for `upcoming_count`. Build contract dict per RETURN_DICT_CONTRACTS.md section 1.3. Remove `handle_error()` calls.

5. **Convert `run_daily_pipeline()` from bool to dict** (ei_main.py) — Three sub-tasks: snapshots, calculations, expected moves. Capture all 3 component dicts (already in local variables). Build contract dict per RETURN_DICT_CONTRACTS.md section 1.1. Include `alert_details` from Step 1. Remove `handle_error()` calls.

6. **Update orchestrator methods** (main_runners.py) — For each of the 3 `run_earnings_*()` methods: change `success = run_*()` to `result = run_*()`, remove DB queries, build completion box from result dict, pass result to `queue_error()` on failure. Keep outer `try/except` as safety net.

## Rules

- Do NOT touch EI visual output (that's Package 2)
- Do NOT touch OP or FM files
- Do NOT change component module business logic — only expand return dicts
- Preserve error-path logging in except blocks
- Read the actual code before changing — verify patterns match the docs

## Verification

1. `python strategies/earnings_intel/ei_main.py --morning-scan --no-interaction` — completes without errors
2. `python strategies/earnings_intel/ei_main.py --weekly-refresh --no-interaction` — completes without errors
3. `python strategies/earnings_intel/ei_main.py --daily-pipeline --no-interaction` — completes without errors
4. Temporarily add `print(type(result), result.keys())` in each orchestrator method to confirm dicts flow through. Remove after.
5. `grep -rn "SELECT COUNT.*earnings" main_runners.py` — zero matches (all DB queries removed)

## When Done

Update `docs/main_orchestrator_refactor/PROGRESS_TRACKER.md`: set Package 1 status to `complete`, fill in Coding Notes.
