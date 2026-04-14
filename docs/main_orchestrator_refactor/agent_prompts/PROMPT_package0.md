# Coding Agent Prompt — Package 0: Orchestrator Standalone Cleanup

You are a coding agent working on a console output refactor for the options scanner system. Your job is to execute Package 0 cleanly without breaking anything.

## Before You Start

Read these files in this order:
1. `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md` — target architecture
2. `docs/main_orchestrator_refactor/WORK_PACKAGES.md` — find Package 0 (starts near the top, after the dependency graph)
3. `docs/main_orchestrator_refactor/VISUAL_DESIGN_REFERENCE.md` — Section 6 (Coffee Break target format), Sections 11-12 (daily state notes)
4. `tools/log_utils.py` — the `create_status_box` API you'll use for coffee breaks

Then read the actual source files you'll modify:
- `main_runners.py`
- `main_ui.py`
- `main.py`
- `strategies/flow_monitor/fm_session_stats.py`

## What You're Doing

Package 0 has 7 steps. Execute them in order:

1. **Remove duplicate `beautiful_log("SUCCESS")` lines** before completion boxes in main_runners.py (10 methods listed in the package). Also remove the blank `print("")` lines that follow each.

2. **Remove duplicate "Initializing/Starting/Running" announcements** in main_runners.py. These duplicate the mission box. The package lists exact content strings to search for in each method. **Keep** error-path beautiful_log calls and FM time-skip logic (e.g., "Market hours detected — skipping pre-market").

3. **Remove filler lines from completion boxes** — "Database secured", "Ready for safe operations", "Performance optimized", hardcoded approximate counts ("~750 symbols", "4 SQL views"). Replace hardcoded counts with success/fail status only.

4. **Add STEP_SEQUENCE constant and rewrite coffee_break()** — Add the class-level constant to the orchestrator class. Rewrite `coffee_break()` in main_ui.py to use `create_status_box` with dynamic "Up Next" lookup. The package has the exact code.

5. **Update all coffee_break() call sites** in main.py — Add `after_step=` parameter to every existing call. The package lists all 12 calls with exact parameter values.

6. **Add daily state persistence** — Create `_reset_daily_state()`, `_load_daily_state()`, `_save_orchestrator_result()`, `_save_fm_session()` helpers. Wire into `run_smart_endless_operation()`. The package has exact code.

7. **Wire FM session stats into daily_state.json** — Add `save_to_daily_state()` and `load_from_daily_state()` methods to `FMSessionStats` in fm_session_stats.py.

## Rules

- Do NOT touch any strategy file except `fm_session_stats.py`
- Do NOT touch any coordinator or component module
- Do NOT refactor business logic — only change what functions print and return
- Preserve error-path logging (lines in `except` blocks)
- Always read the actual code before making changes — verify patterns match

## Verification (run these when done)

1. `grep -rn "beautiful_log.*successfully\|beautiful_log.*COMPLETED\|beautiful_log.*COMPLETE\|beautiful_log.*Initializing\|beautiful_log.*Starting.*pipeline\|beautiful_log.*Running.*pipeline\|beautiful_log.*Beginning" main_runners.py` — should return only error-path and FM time-skip lines
2. `grep -rn "Database secured\|Ready for safe operations\|Ready for analysis\|Performance optimized\|~750 symbols\|4 SQL views" main_runners.py` — zero matches
3. Visual: coffee_break() uses `create_status_box` and resolves "Up Next"
4. STEP_SEQUENCE order matches execution order in `run_smart_endless_operation()`
5. `grep -rn "coffee_break" main.py` — every call has `after_step=`
6. `_reset_daily_state()` called at top of each daily cycle
7. `_save_orchestrator_result()` called after each phase result
8. `python -c "from strategies.flow_monitor.fm_session_stats import FMSessionStats; print('OK')"` — succeeds

## When Done

Update `docs/main_orchestrator_refactor/PROGRESS_TRACKER.md`: set Package 0 status to `complete`, fill in Coding Notes with a brief summary of changes.
