#!/usr/bin/env python3
"""
Backfill: Refresh stale derived columns on earnings_events
----------------------------------------------------------
Implements SA Proposal 016 (Refresh Stale `earnings_events` Derived Columns).

Problem: Proposal 012 (4/23) cleaned `earnings_moves` (deleted 8K bogus zero-move
rows, recomputed 3K). But `earnings_events.historical_avg_move_pct` and its cascade
columns (relative_underpricing_pct, earnings_play_signal, move_vs_historical_pct,
signal_accuracy) were written at signal-generation time and frozen — they still
reflect math against the pre-cleanup `earnings_moves` data. ~80 events affected.

Concrete canary: MMM 4/21 stored hist=8.77 -> recomputed ~5.96, flipping the signal
from STRONG BUY (relative_underpricing 69%) to no-actionable-signal (~14.8%).

Fix: For every earnings_events row with historical_avg_move_pct IS NOT NULL,
recompute the derived columns from current source data, using as_of_date semantics
(exclude the event's own earnings_moves row from its hist baseline).

Usage:
    python tools/backfill_earnings_events_derived.py            # dry-run, show transitions
    python tools/backfill_earnings_events_derived.py --apply    # write to DB
    python tools/backfill_earnings_events_derived.py --symbol MMM --apply
    python tools/backfill_earnings_events_derived.py --symbols META,AAPL --apply

When called with --symbols, useful as a Part B prevention hook (call from any code
path that adds/recomputes earnings_moves rows so cascade columns refresh automatically).
"""

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))

from strategies.earnings_intel.ei_moves_upcoming import (
    get_historical_avg_move,
    determine_earnings_play_signal,
    load_config,
)
from strategies.earnings_intel.ei_post_earnings_calc import compute_move_vs_historical


def get_default_db_path():
    return PROJECT_ROOT / 'data' / 'datalake.db'


def fetch_candidates(db_path, symbols=None):
    """Return list of dicts for events needing recompute."""
    sql = """
        SELECT event_id, symbol, earnings_date,
               historical_avg_move_pct, historical_avg_move_alltime_pct,
               historical_quarters_used, straddle_expected_move_pct,
               relative_underpricing_pct, earnings_play_signal,
               actual_move_1day_pct, move_vs_historical_pct, signal_accuracy
        FROM earnings_events
        WHERE historical_avg_move_pct IS NOT NULL
    """
    params = []
    if symbols:
        placeholders = ','.join(['?'] * len(symbols))
        sql += " AND symbol IN ({})".format(placeholders)
        params.extend(symbols)
    sql += " ORDER BY earnings_date DESC, symbol"
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    return rows


def recompute_row(row, db_path, config):
    """Recompute all derived columns for one event. Returns dict with new values + diff metadata."""
    symbol = row['symbol']
    earnings_date = row['earnings_date']
    straddle_pct = row['straddle_expected_move_pct']
    actual_1d = row['actual_move_1day_pct']

    hist = get_historical_avg_move(symbol, str(db_path), recent_quarters=6, as_of_date=earnings_date)

    if hist is None:
        new_hist = None
        new_alltime = None
        new_quarters = 0
    else:
        new_hist = hist['recent']
        new_alltime = hist['alltime']
        new_quarters = hist['quarters_used']

    if new_hist is not None and straddle_pct and straddle_pct > 0:
        new_relative = ((new_hist - straddle_pct) / straddle_pct) * 100
    else:
        new_relative = None

    new_signal = determine_earnings_play_signal(new_relative, config)
    actual_abs = abs(actual_1d) if actual_1d is not None else None
    new_move_vs_hist, new_signal_acc = compute_move_vs_historical(actual_abs, new_hist)

    return {
        'event_id': row['event_id'],
        'symbol': symbol,
        'earnings_date': earnings_date,
        'old_hist': row['historical_avg_move_pct'],
        'new_hist': new_hist,
        'old_alltime': row['historical_avg_move_alltime_pct'],
        'new_alltime': new_alltime,
        'old_quarters': row['historical_quarters_used'],
        'new_quarters': new_quarters,
        'old_relative': row['relative_underpricing_pct'],
        'new_relative': new_relative,
        'old_signal': row['earnings_play_signal'],
        'new_signal': new_signal,
        'old_move_vs_hist': row['move_vs_historical_pct'],
        'new_move_vs_hist': new_move_vs_hist,
        'old_signal_acc': row['signal_accuracy'],
        'new_signal_acc': new_signal_acc,
    }


def fmt(v, places=2):
    if v is None:
        return 'NULL'
    return '{:.{}f}'.format(v, places)


def is_changed(diff):
    """True if any tracked field differs (with float tolerance)."""
    def neq(a, b, tol=0.001):
        if a is None and b is None:
            return False
        if a is None or b is None:
            return True
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(a - b) > tol
        return a != b
    return (
        neq(diff['old_hist'], diff['new_hist'])
        or neq(diff['old_alltime'], diff['new_alltime'])
        or neq(diff['old_quarters'], diff['new_quarters'])
        or neq(diff['old_relative'], diff['new_relative'])
        or neq(diff['old_signal'], diff['new_signal'])
        or neq(diff['old_move_vs_hist'], diff['new_move_vs_hist'])
        or neq(diff['old_signal_acc'], diff['new_signal_acc'])
    )


def print_summary(diffs, verbose_signal_changes=True, verbose_canary=True):
    total = len(diffs)
    changed = [d for d in diffs if is_changed(d)]
    signal_changed = [d for d in changed if (d['old_signal'] or '') != (d['new_signal'] or '')]
    null_alltime_filled = [d for d in changed if d['old_alltime'] is None and d['new_alltime'] is not None]

    print('')
    print('=' * 70)
    print('BACKFILL SUMMARY')
    print('=' * 70)
    print('Events with historical_avg_move_pct IS NOT NULL : {}'.format(total))
    print('Events with at least one column change          : {}'.format(len(changed)))
    print('Events with signal-label change                 : {}'.format(len(signal_changed)))
    print('NULL alltime_pct populated by this run          : {}'.format(len(null_alltime_filled)))
    print('')

    transitions = Counter(((d['old_signal'] or 'NULL'), (d['new_signal'] or 'NULL')) for d in signal_changed)
    if transitions:
        print('Signal-label transitions:')
        for (old, new), n in sorted(transitions.items(), key=lambda kv: -kv[1]):
            print('  {:>11s}  ->  {:<11s}  : {} events'.format(old, new, n))
        print('')

    if verbose_signal_changes and signal_changed:
        print('Signal-changing events (top 25 by abs hist drift):')
        ranked = sorted(signal_changed,
                        key=lambda d: abs((d['new_hist'] or 0) - (d['old_hist'] or 0)),
                        reverse=True)[:25]
        print('  {:<8s} {:<12s} {:>8s} {:>8s} {:>10s} {:>10s} {:>11s} {:>11s}'.format(
            'symbol', 'earn_date', 'old_hst', 'new_hst', 'old_rel%', 'new_rel%', 'old_signal', 'new_signal'))
        for d in ranked:
            print('  {:<8s} {:<12s} {:>8s} {:>8s} {:>10s} {:>10s} {:>11s} {:>11s}'.format(
                d['symbol'], d['earnings_date'],
                fmt(d['old_hist']), fmt(d['new_hist']),
                fmt(d['old_relative']), fmt(d['new_relative']),
                d['old_signal'] or 'NULL', d['new_signal'] or 'NULL'))
        print('')

    if verbose_canary:
        canary = next((d for d in diffs if d['symbol'] == 'MMM' and d['earnings_date'] == '2026-04-21'), None)
        if canary:
            print('Canary check (MMM 2026-04-21):')
            print('  hist_pct       : {} -> {}'.format(fmt(canary['old_hist']), fmt(canary['new_hist'])))
            print('  alltime_pct    : {} -> {}'.format(fmt(canary['old_alltime']), fmt(canary['new_alltime'])))
            print('  quarters_used  : {} -> {}'.format(canary['old_quarters'], canary['new_quarters']))
            print('  relative_upr%  : {} -> {}'.format(fmt(canary['old_relative']), fmt(canary['new_relative'])))
            print('  signal         : {} -> {}'.format(canary['old_signal'], canary['new_signal']))
            print('  move_vs_hist%  : {} -> {}'.format(fmt(canary['old_move_vs_hist']), fmt(canary['new_move_vs_hist'])))
            print('  signal_accuracy: {} -> {}'.format(canary['old_signal_acc'], canary['new_signal_acc']))
            expected_hist = 5.96
            ok = canary['new_hist'] is not None and abs(canary['new_hist'] - expected_hist) < 0.1
            print('  CANARY PASS    : {}  (expected new_hist ~{:.2f})'.format(ok, expected_hist))
            print('')


def apply_updates(db_path, diffs):
    changed = [d for d in diffs if is_changed(d)]
    if not changed:
        print('No changes to apply.')
        return 0

    sql = """
        UPDATE earnings_events
        SET historical_avg_move_pct = ?,
            historical_avg_move_alltime_pct = ?,
            historical_quarters_used = ?,
            relative_underpricing_pct = ?,
            earnings_play_signal = ?,
            move_vs_historical_pct = ?,
            signal_accuracy = ?
        WHERE event_id = ?
    """
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.execute("PRAGMA busy_timeout = 30000")
        cur = conn.cursor()
        for d in changed:
            cur.execute(sql, (
                d['new_hist'], d['new_alltime'], d['new_quarters'],
                d['new_relative'], d['new_signal'],
                d['new_move_vs_hist'], d['new_signal_acc'],
                d['event_id'],
            ))
        conn.commit()
    return len(changed)


def parse_symbols(arg):
    if not arg:
        return None
    return [s.strip().upper() for s in arg.split(',') if s.strip()]


def run(db_path=None, symbols=None, apply=False, quiet=False):
    """Programmatic entry point. Used by Part B prevention hook.

    Args:
        db_path: Path to datalake.db (default: data/datalake.db)
        symbols: Optional list of symbols to scope the refresh
        apply: If True, write changes; if False, dry-run
        quiet: Suppress verbose tables (Part B hook usage)

    Returns:
        dict with 'total', 'changed', 'signal_changed', 'applied'
    """
    db_path = Path(db_path) if db_path else get_default_db_path()
    config = load_config()
    rows = fetch_candidates(db_path, symbols=symbols)
    diffs = [recompute_row(r, db_path, config) for r in rows]
    changed = [d for d in diffs if is_changed(d)]
    signal_changed = [d for d in changed if (d['old_signal'] or '') != (d['new_signal'] or '')]

    if not quiet:
        print_summary(diffs)

    applied = 0
    if apply:
        applied = apply_updates(db_path, diffs)
        if not quiet:
            print('Applied updates to {} event rows.'.format(applied))

    return {
        'total': len(diffs),
        'changed': len(changed),
        'signal_changed': len(signal_changed),
        'applied': applied,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', default=None, help='Path to datalake.db (default: data/datalake.db)')
    ap.add_argument('--symbol', default=None, help='Restrict to one symbol')
    ap.add_argument('--symbols', default=None, help='Restrict to comma-separated symbols')
    ap.add_argument('--apply', action='store_true', help='Write changes (default: dry-run)')
    ap.add_argument('--quiet', action='store_true', help='Suppress verbose tables')
    args = ap.parse_args()

    symbols = parse_symbols(args.symbols)
    if args.symbol:
        symbols = (symbols or []) + [args.symbol.upper()]

    db_path = Path(args.db) if args.db else get_default_db_path()
    if not db_path.exists():
        print('ERROR: db not found: {}'.format(db_path))
        return 1

    print('DB: {}'.format(db_path))
    print('Mode: {}'.format('APPLY' if args.apply else 'DRY-RUN'))
    if symbols:
        print('Symbols: {}'.format(', '.join(symbols)))

    run(db_path=db_path, symbols=symbols, apply=args.apply, quiet=args.quiet)
    return 0


if __name__ == '__main__':
    sys.exit(main())
