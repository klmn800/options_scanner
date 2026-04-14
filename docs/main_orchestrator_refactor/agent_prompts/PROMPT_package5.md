# Coding Agent Prompt — Package 5: FM Post-Market Research + Dict Return

You are a coding agent working on a console output refactor for the options scanner system. Your job is to execute Package 5 — researching FM post-market inner component returns, converting bool-returning wrappers to dicts, and converting `run_post_market()` to return a structured dict.

**This package has a research phase.** You must trace what components actually return before implementing.

## Before You Start

Read these files:
1. `docs/main_orchestrator_refactor/RETURN_DICT_CONTRACTS.md` — Section 3.4 (FM post-market contract spec with known gaps)
2. `docs/main_orchestrator_refactor/WORK_PACKAGES.md` — find Package 5 (4 steps)

Then read the actual source files (research targets):
- `strategies/flow_monitor/fm_main.py` — find `run_post_market()` and its 4 inner `run_*()` wrapper functions
- `strategies/flow_monitor/fm_backfill_handler.py` — trace what `run_daily_backfill()` returns
- `strategies/flow_monitor/fm_market_regime_summary.py` — subprocess, exit code only
- `strategies/flow_monitor/fm_symbol_rollup.py` — trace what `run_daily_rollup()` returns
- `strategies/flow_monitor/fm_daily_evaluation.py` — trace what `run_daily_evaluation()` returns
- `strategies/flow_monitor/fm_watchlist.py` — `archive_expired_entries()` already returns dict

## What You're Doing

4 steps:

### Step 1: Research — Trace Inner Component Returns

For each of these 4 components, document:
- Current return type
- What metrics are available (does it compute stats then discard them?)
- What the wrapper discards

Write a brief comment at the top of each changed function documenting what the component returns.

Components to trace:
- `fm_backfill_handler.run_daily_backfill()` — does it return a dict or bool?
- `fm_symbol_rollup.run_daily_rollup()` — same question
- `fm_daily_evaluation.run_daily_evaluation()` — same question
- `fm_market_regime_summary.py` — subprocess, confirm exit code is the only signal

### Step 2: Convert Inner Wrapper Functions

For each of the 4 `run_*_task()` wrappers inside `run_post_market()`:
- If component returns dict: pass it through, add `success` and `duration_seconds`
- If component returns bool but has stats attributes: read them
- If component returns bool with no stats: return minimal `{success, duration_seconds}`
- Subprocess (market regime): `{success, duration_seconds}` is all we can get

### Step 3: Convert `run_post_market()` to Return Dict

Aggregate all 5 sub-task results into the contract dict:
```python
{
    'success': bool,
    'duration_seconds': float,
    'tasks_successful': int,
    'tasks_total': int,
    'errors': int,
    'sub_tasks': {
        'backfill': {...},
        'market_regime': {...},
        'symbol_rollup': {...},
        'evaluation': {...},
        'watchlist_cleanup': {...},
    },
}
```

Remove DB diagnostic queries (the `SELECT COUNT(DISTINCT symbol)` and `SELECT COUNT(*)` queries after each task) — metrics should come from return dicts.

### Step 4: Update Orchestrator

In `run_flow_monitor()` in main_runners.py, change from `post_market_success = run_post_market(...)` to `post_market_result = run_post_market(...)`. Use the dict for the FM completion box.

## Rules

- Do NOT touch `run_pre_market()` (Package 4)
- Do NOT touch `run_market_hours()` (already correct)
- Do NOT touch FM visual output (Package 6)
- Preserve error-path logging
- Document your research findings as comments

## Verification

1. Research documented: each changed function has a comment documenting what the component returns
2. `run_post_market()` returns `dict` (not `bool`)
3. `python -c "from strategies.flow_monitor.fm_main import run_post_market; print('OK')"` — succeeds

## When Done

Update `docs/main_orchestrator_refactor/PROGRESS_TRACKER.md`: set Package 5 status to `complete`, fill in Coding Notes including research findings.
