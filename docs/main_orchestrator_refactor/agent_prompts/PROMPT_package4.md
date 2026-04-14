# Coding Agent Prompt — Package 4: FM Pre-Market Dict Return

You are a coding agent working on a console output refactor for the options scanner system. Your job is to execute Package 4 — converting FM `run_pre_market()` from `bool` to structured `dict` return. This is a small, focused package.

## Before You Start

Read these files:
1. `docs/main_orchestrator_refactor/RETURN_DICT_CONTRACTS.md` — Section 3.2 (FM pre-market contract spec)
2. `docs/main_orchestrator_refactor/WORK_PACKAGES.md` — find Package 4 (2 steps)

Then read the actual source files:
- `strategies/flow_monitor/fm_main.py` — find `run_pre_market()` function
- `strategies/flow_monitor/fm_alert_resolver.py` — verify what `resolve_yesterday_alerts()` and `update_watchlist_sentiment()` return
- `main_runners.py` — find `run_flow_monitor()` where pre-market result is used

## What You're Doing

2 steps:

1. **Convert `run_pre_market()` in fm_main.py** — Capture `resolution_stats` from `resolve_yesterday_alerts()` and `sentiment_stats` from `update_watchlist_sentiment()`. Instead of returning `True`/`False`, return the contract dict:

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

On failure: `{'success': False, 'failure_reason': str(e), 'duration_seconds': ..., 'alerts_resolved': 0, 'symbols_updated': 0}` with zeros.

2. **Update orchestrator** (main_runners.py `run_flow_monitor()`) — Find where `pre_market_success` is set from `run_pre_market()`. Change to capture the dict. Use it in the FM completion box to show actual metrics (alerts resolved, building/closing/neutral, symbols updated) instead of just a success/fail flag.

## Rules

- Do NOT touch `run_market_hours()` (already returns dict)
- Do NOT touch `run_post_market()` (that's Package 5)
- Do NOT touch FM visual output (that's Package 6)
- Preserve error-path logging

## Verification

1. Confirm `run_pre_market()` returns `dict` (not `bool`)
2. Confirm the FM completion box in main_runners.py shows "Alerts resolved: N" with breakdown, not just "Pre-Market: Success"
3. `python -c "from strategies.flow_monitor.fm_main import run_pre_market; print('OK')"` — succeeds

## When Done

Update `docs/main_orchestrator_refactor/PROGRESS_TRACKER.md`: set Package 4 status to `complete`, fill in Coding Notes.
