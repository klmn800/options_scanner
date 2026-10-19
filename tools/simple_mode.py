"""
Simple Mode (PRD 0014) - headless, collection-only daily cycle.

Opt-in per run with `python main.py --simple-mode` (launched by
scheduled_tasks/start_main_simple.bat). Without the flag nothing here changes
behavior: is_simple_mode() is False and every skip check returns False.

The skip list is fixed in code on purpose - Simple Mode is one switch, not a
per-step menu. Names match the orchestrator's result keys and the Flow
Monitor task names they guard.
"""

import logging

# Steps that do not run in Simple Mode. Everything not listed runs as usual:
# 2 Flow Monitor collection, 3.2 Evening OP, 4.1 Daily Backup, 4.2 Autofix
# Review, 5.1 Weekly Backup, 5.4 Sector Archive, 6.1 Performance Collection,
# FM historical backfill.
SIMPLE_MODE_SKIPS = frozenset({
    # Orchestrator (main.py / main_runners.py)
    '1.1 Morning Option Pipeline',
    '1.2 Earnings Intelligence',
    '1.3 Metadata Collection',
    '1.4 Trade Ingest',
    '1.5 Query Sync (Morning)',
    '2.2 Trading Advisor',
    '3.1 Trade Ingest',
    '3.4 Query Sync (Final)',
    '5.2 FM Baseline',
    '5.3 Earnings Refresh',
    '6.2 Symbol Health',

    # Flow Monitor pre-market (alert resolution, sentiment, pre-market sync)
    'FM Pre-Market',

    # Flow Monitor market-hours cycle (collector, session stats, health
    # reporter, market snapshot and diagnostic log still run).
    # FM Watchlist also covers news enrichment and dip detection (they run inside it).
    # FM Alerts also covers email digests, X posting and the alert summary display.
    'FM Analyzer',
    'FM Alerts',
    'FM Watchlist',
    'FM Earnings Signals',
    'FM Intraday Trade Ingest',
    'FM Quick Sync',
    'FM Cycle Break',  # successful cycles only; failed cycles keep the 60s break

    # Flow Monitor post-market: regime summary, symbol rollup, daily aggregate,
    # evaluation, watchlist cleanup / news backfill (historical backfill still runs)
    'FM Post-Market Analysis',
})

_enabled = False
_logged_skips = set()


def enable():
    """Turn Simple Mode on for this process. Called once from argparse handling."""
    global _enabled
    _enabled = True
    logging.info("Simple Mode enabled (PRD 0014) - collection-only, %d steps skipped", len(SIMPLE_MODE_SKIPS))


def is_simple_mode():
    """True if this process was started with --simple-mode."""
    return _enabled


def run_mode():
    """'simple' or 'full' - recorded in daily_state.json so Autofix restarts the same mode."""
    return 'simple' if _enabled else 'full'


def should_skip(step_name):
    """True if step_name is skipped in Simple Mode and Simple Mode is on.

    Logs one line per step name per process (the FM cycle checks every
    cycle, so repeats would flood the log).
    """
    if not _enabled or step_name not in SIMPLE_MODE_SKIPS:
        return False
    if step_name not in _logged_skips:
        _logged_skips.add(step_name)
        logging.info("Skipped (simple mode): %s", step_name)
    return True
