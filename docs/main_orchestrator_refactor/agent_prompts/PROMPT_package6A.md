# Coding Agent Prompt — Package 6A: FM Formatting Functions + Coffee Break Rewrite

You are a coding agent working on a console output refactor for the options scanner system. Your job is to execute Package 6A — deleting the 9 beautification/formatting function definitions from `fm_main.py` and rewriting `coffee_break()` to use the standard `create_status_box()` from `log_utils.py`.

**This is the prerequisite for all other FM visual cleanup (6B/6C/6D).** The formatting functions must be gone before the call sites can be triaged.

## Before You Start

Read these files:
1. `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md` — delegated orchestrator rules (FM market hours section)
2. `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_AUDIT.md` — Section 2 (FM violation inventory)
3. `docs/main_orchestrator_refactor/WORK_PACKAGES.md` — find Package 6A (2 steps + structure map)

Then read the actual source file:
- `strategies/flow_monitor/fm_main.py` — the only file you modify

Also read for reference (do NOT modify):
- `strategies/flow_monitor/fm_session_stats.py` — exemplary file (modified by Package 0, do NOT touch)

## What You're Doing

2 steps:

### Step 1: Delete formatting functions from fm_main.py

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

### Step 2: Rewrite `coffee_break()` to use standard formatting

The current `coffee_break()` calls the now-deleted `contextual_coffee_break()` and `beautiful_log()`. Rewrite it to use `create_status_box` from `log_utils.py`:

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

**Note:** This is a different function from the orchestrator's `self.coffee_break(seconds, context)` in `main_ui.py`. FM's version is a module-level function with its own signature and its own interruptible sleep logic using `shutdown_event`. They are independent implementations in different files.

## Rules

- Do NOT touch `fm_session_stats.py` (modified by Package 0)
- Do NOT touch `fm_watchlist.py`, `fm_baseline_generator.py`
- Do NOT touch return values (fixed in Packages 4-5)
- Do NOT touch `main_runners.py`
- Do NOT touch call sites to `beautiful_log()`, `safe_log()`, etc. — those are triaged in Packages 6B/6C/6D
- Only modify the function definitions and `coffee_break()` in this package

## Verification

1. `grep -rn "def get_display_settings\|def colorize\|def beautiful_log\|def create_phase_header\|def create_task_box\|def create_error_box\|def create_success_celebration\|def create_section_divider\|def contextual_coffee_break" strategies/flow_monitor/fm_main.py` — zero matches (all 9 function definitions deleted)
2. `grep -rn "create_status_box" strategies/flow_monitor/fm_main.py` — at least 1 match (in the rewritten `coffee_break()`)
3. Coffee break callers: `grep -rn "coffee_break(" strategies/flow_monitor/fm_main.py` — should show the rewritten function definition and its callers. Verify callers still pass valid `context=` values
4. `python -c "from strategies.flow_monitor.fm_main import run_pre_market, run_market_hours, run_post_market; print('OK')"` — succeeds. Note: `beautiful_log()` etc. call sites still exist but will fail at runtime — that's expected until 6B/6C/6D complete the triage

## When Done

Update `docs/main_orchestrator_refactor/PROGRESS_TRACKER.md`: set Package 6A status to `complete`, fill in Coding Notes.
