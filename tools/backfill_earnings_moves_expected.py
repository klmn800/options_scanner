#!/usr/bin/env python3
"""
Backfill: Populate NULL earnings_moves.expected_move_pct using IV history
-------------------------------------------------------------------------
Implements TA Proposal 003 (earnings_moves NULL expected_move Investigation).

Problem: ~1,800 historical earnings events have NULL expected_move_pct
because the post-earnings calc's IV-based fallback only consulted production
DB. option_symbol_summary is Tier 2 of the sector archive (rows >30d are
MOVED out of datalake.db), so any event older than the rolling window
silently got NULL — even though the source IV existed in the appropriate
sector archive.

Now that ei_post_earnings_calc.py:_get_iv_before_earnings() consults sector
archives as a fallback, this script re-runs the IV-based reconstruction
for every NULL event and updates both:
  - earnings_moves.expected_move_pct (and move_vs_expected_pct cascade)
  - earnings_events.move_vs_expected_pct (denormalized outcome column)

Scope:
- Events with earnings_date >= 2025-07-01 (archive IV coverage starts ~2025-07)
- Events with NULL expected_move_pct
- Skips events where IV is genuinely unavailable (function returns None)

Pre-2025-07-01 events remain NULL — IV history doesn't exist anywhere for
them. This is structural and documented in TA reference.

Usage:
    python tools/backfill_earnings_moves_expected.py             # dry-run
    python tools/backfill_earnings_moves_expected.py --apply     # write
    python tools/backfill_earnings_moves_expected.py --since 2025-07-01 --apply
"""

import argparse
import math
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))

from strategies.earnings_intel.ei_post_earnings_calc import PostEarningsCalculator


def get_default_db_path():
    return PROJECT_ROOT / 'data' / 'datalake.db'


def find_candidates(db_path, since_date):
    """Return list of (move_id, event_id, symbol, earnings_date, actual_move_1day) for NULL events."""
    sql = """
        SELECT em.move_id, em.event_id, em.symbol, em.earnings_date, em.move_1day_pct
        FROM earnings_moves em
        WHERE em.expected_move_pct IS NULL
          AND em.earnings_date >= ?
        ORDER BY em.earnings_date DESC, em.symbol
    """
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(sql, (since_date,)).fetchall()]
    return rows


def run(db_path=None, since_date='2025-07-01', apply=False, quiet=False):
    db_path = Path(db_path) if db_path else get_default_db_path()
    candidates = find_candidates(db_path, since_date)

    if not quiet:
        print('DB: {}'.format(db_path))
        print('Mode: {}'.format('APPLY' if apply else 'DRY-RUN'))
        print('Since date: {}'.format(since_date))
        print('Candidates (NULL expected_move_pct): {}'.format(len(candidates)))
        print('')

    calc = PostEarningsCalculator(db_path=str(db_path))

    found_iv = 0
    no_iv = 0
    sample = []

    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        for c in candidates:
            symbol = c['symbol']
            earnings_date = c['earnings_date']
            actual_1day = c['move_1day_pct']

            iv_before = calc._get_iv_before_earnings(cur, symbol, earnings_date)
            if iv_before is None:
                no_iv += 1
                continue

            expected_move_pct = iv_before * math.sqrt(1.0 / 365.0) * 100
            move_vs_expected = None
            if actual_1day is not None and expected_move_pct > 0:
                move_vs_expected = (abs(actual_1day) / expected_move_pct) * 100

            found_iv += 1
            if len(sample) < 10:
                sample.append({
                    'symbol': symbol, 'date': earnings_date,
                    'iv': iv_before, 'exp': expected_move_pct,
                    'actual': actual_1day, 'vs_exp': move_vs_expected,
                })

            if apply:
                cur.execute("""
                    UPDATE earnings_moves
                    SET expected_move_pct = ?,
                        move_vs_expected_pct = COALESCE(?, move_vs_expected_pct)
                    WHERE move_id = ?
                """, (expected_move_pct, move_vs_expected, c['move_id']))

                if c['event_id'] and move_vs_expected is not None:
                    cur.execute("""
                        UPDATE earnings_events
                        SET move_vs_expected_pct = ?
                        WHERE event_id = ?
                    """, (move_vs_expected, c['event_id']))

        if apply:
            conn.commit()

    if not quiet:
        print('IV found (would update): {}'.format(found_iv))
        print('IV unavailable (skipped): {}'.format(no_iv))
        if sample:
            print('')
            print('Sample of computed values:')
            print('  {:<8s} {:<12s} {:>6s} {:>7s} {:>9s} {:>9s}'.format(
                'symbol', 'date', 'iv', 'exp%', 'actual%', 'vs_exp%'))
            for s in sample:
                print('  {:<8s} {:<12s} {:>6.3f} {:>7.2f} {:>9} {:>9}'.format(
                    s['symbol'], s['date'], s['iv'], s['exp'],
                    '{:.2f}'.format(s['actual']) if s['actual'] is not None else 'NULL',
                    '{:.1f}'.format(s['vs_exp']) if s['vs_exp'] is not None else 'NULL'))

    return {'candidates': len(candidates), 'found_iv': found_iv, 'no_iv': no_iv,
            'applied': found_iv if apply else 0}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', default=None, help='Path to datalake.db (default: data/datalake.db)')
    ap.add_argument('--since', default='2025-07-01', help='Min earnings_date (default: 2025-07-01)')
    ap.add_argument('--apply', action='store_true', help='Write changes (default: dry-run)')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    db_path = Path(args.db) if args.db else get_default_db_path()
    if not db_path.exists():
        print('ERROR: db not found: {}'.format(db_path))
        return 1

    run(db_path=db_path, since_date=args.since, apply=args.apply, quiet=args.quiet)
    return 0


if __name__ == '__main__':
    sys.exit(main())
