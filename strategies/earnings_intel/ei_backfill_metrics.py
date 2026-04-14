#!/usr/bin/env python3
"""
Earnings Moves: IV & Expected Move Backfill (ei_backfill_metrics.py)
--------------------------------------------------------------------
One-time backfill script to populate iv_collapse_pct, expected_move_pct,
and move_vs_expected_pct for existing earnings_moves rows.

These columns exist in the schema but were never computed (all NULL across
9,323 rows as of 2026-02-10). This script computes them from production
data (option_symbol_summary) for events that have matching IV data.

Scope:
- Only processes rows where iv_collapse_pct IS NULL (idempotent — safe to re-run)
- Only queries production database (no archive access)
- Matchable events: ~27 (events with both earnings_events records AND
  option_symbol_summary data in production)
- Orphaned rows (event_ids not in earnings_events) are skipped and counted
- Archive-spanning backfill is a future enhancement (see plan notes)

Usage:
    python strategies/earnings_intel/ei_backfill_metrics.py              # Execute
    python strategies/earnings_intel/ei_backfill_metrics.py --dry-run    # Preview only
    python strategies/earnings_intel/ei_backfill_metrics.py --verbose    # Detailed logging

Author: Ben (with Claude)
Date: 2026-02-10
"""

import os
import sys
import sqlite3
import logging
import math
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'tools'))

from decimal_formatter import clean_database_row


def get_database_path():
    """Get path to production datalake.db"""
    return project_root / 'data' / 'datalake.db'


def get_iv_at_date(cursor, symbol, target_date, direction):
    """Get iv_front_month near a target date from option_symbol_summary.

    Uses iv_front_month (7-21 DTE bucket) because it's consistently populated
    across all symbols, unlike iv_30dte which has many NULLs.

    Args:
        cursor: Database cursor
        symbol: Stock symbol
        target_date: Target date string (YYYY-MM-DD)
        direction: 'before' = last trading day < target,
                   'after' = first trading day > target

    Returns:
        tuple: (iv_value, trade_date) or (None, None)
    """
    if direction == 'before':
        cursor.execute("""
            SELECT iv_front_month, trade_date FROM option_symbol_summary
            WHERE symbol = ? AND trade_date < ?
            AND iv_front_month IS NOT NULL AND iv_front_month > 0
            ORDER BY trade_date DESC LIMIT 1
        """, (symbol, target_date))
    else:
        cursor.execute("""
            SELECT iv_front_month, trade_date FROM option_symbol_summary
            WHERE symbol = ? AND trade_date > ?
            AND iv_front_month IS NOT NULL AND iv_front_month > 0
            ORDER BY trade_date ASC LIMIT 1
        """, (symbol, target_date))

    row = cursor.fetchone()
    return (row[0], row[1]) if row else (None, None)


def compute_iv_metrics(cursor, symbol, earnings_date):
    """Compute IV metrics for a single earnings event.

    Args:
        cursor: Database cursor
        symbol: Stock symbol
        earnings_date: Earnings date string (YYYY-MM-DD)

    Returns:
        dict: {iv_buildup_pct, iv_collapse_pct, iv_recovery_pct, iv_crush_severity}
              or empty dict if insufficient data
    """
    earnings_dt = datetime.strptime(earnings_date, '%Y-%m-%d')

    # T-7: ~7 calendar days before (use -5 to skip weekends)
    t_minus_7 = (earnings_dt - timedelta(days=5)).strftime('%Y-%m-%d')
    iv_t7, _ = get_iv_at_date(cursor, symbol, t_minus_7, 'before')

    # T-1: last trading day before earnings
    iv_before, date_before = get_iv_at_date(cursor, symbol, earnings_date, 'before')

    # T+1: first trading day after earnings
    iv_after, date_after = get_iv_at_date(cursor, symbol, earnings_date, 'after')

    # T+3: ~3 trading days after
    t_plus_3 = (earnings_dt + timedelta(days=3)).strftime('%Y-%m-%d')
    iv_t3, _ = get_iv_at_date(cursor, symbol, t_plus_3, 'after')

    metrics = {}

    # IV Buildup: T-7 to T-1
    if iv_t7 and iv_before:
        metrics['iv_buildup_pct'] = ((iv_before - iv_t7) / iv_t7) * 100

    # IV Collapse: T-1 to T+1
    if iv_before and iv_after:
        metrics['iv_collapse_pct'] = ((iv_after - iv_before) / iv_before) * 100

    # IV Recovery: T+1 to T+3
    if iv_after and iv_t3:
        metrics['iv_recovery_pct'] = ((iv_t3 - iv_after) / iv_after) * 100

    # Crush severity (5-tier scale centered around ~45% typical post-earnings crush)
    if metrics.get('iv_collapse_pct') is not None:
        collapse = abs(metrics['iv_collapse_pct'])
        if collapse > 65:
            metrics['iv_crush_severity'] = 'severe'
        elif collapse >= 50:
            metrics['iv_crush_severity'] = 'high'
        elif collapse >= 40:
            metrics['iv_crush_severity'] = 'normal'
        elif collapse >= 25:
            metrics['iv_crush_severity'] = 'mild'
        else:
            metrics['iv_crush_severity'] = 'minimal'

    return metrics


def compute_expected_move(cursor, symbol, earnings_date):
    """Compute 1-day expected move from pre-earnings IV.

    This is the 1-day expected move for comparison with move_1day_pct.
    Uses the Black-Scholes formula: IV * sqrt(1/365) * 100

    Args:
        cursor: Database cursor
        symbol: Stock symbol
        earnings_date: Earnings date string (YYYY-MM-DD)

    Returns:
        float: Expected 1-day move percentage, or None
    """
    iv_before, _ = get_iv_at_date(cursor, symbol, earnings_date, 'before')

    if iv_before and iv_before > 0:
        return iv_before * math.sqrt(1.0 / 365.0) * 100

    return None


def run_backfill(dry_run=False, verbose=False):
    """Execute the backfill.

    Args:
        dry_run: If True, preview only — no writes
        verbose: If True, log details for each event

    Returns:
        dict: {updated, skipped_no_iv, skipped_no_event, orphaned, errors}
    """
    db_path = get_database_path()
    stats = {
        'total_null': 0,
        'matched': 0,
        'updated': 0,
        'skipped_no_iv': 0,
        'skipped_already_has': 0,
        'orphaned': 0,
        'errors': 0
    }

    logging.info("Backfill target: {}".format(db_path))
    logging.info("Mode: {}".format("DRY RUN" if dry_run else "LIVE"))

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA busy_timeout = 30000")
        cursor = conn.cursor()

        # Step 1: Find all earnings_moves rows needing backfill
        cursor.execute("""
            SELECT em.move_id, em.event_id, em.symbol, em.move_1day_pct,
                   ee.earnings_date
            FROM earnings_moves em
            LEFT JOIN earnings_events ee ON em.event_id = ee.event_id
            WHERE em.iv_collapse_pct IS NULL
            ORDER BY ee.earnings_date DESC NULLS LAST
        """)

        rows = cursor.fetchall()
        stats['total_null'] = len(rows)
        logging.info("Found {} earnings_moves rows with NULL iv_collapse_pct".format(len(rows)))

        for move_id, event_id, symbol, move_1day_pct, earnings_date in rows:
            # Skip orphaned rows (no matching earnings_events record)
            if not earnings_date:
                stats['orphaned'] += 1
                continue

            stats['matched'] += 1

            try:
                # Compute IV metrics
                iv_metrics = compute_iv_metrics(cursor, symbol, earnings_date)

                if not iv_metrics.get('iv_collapse_pct') and iv_metrics.get('iv_collapse_pct') != 0:
                    stats['skipped_no_iv'] += 1
                    if verbose:
                        logging.debug("  {} - No IV data around {}".format(symbol, earnings_date))
                    continue

                # Compute expected move
                expected_move_pct = compute_expected_move(cursor, symbol, earnings_date)

                # Compute move vs expected
                move_vs_expected_pct = None
                if expected_move_pct and expected_move_pct > 0 and move_1day_pct is not None:
                    move_vs_expected_pct = (abs(move_1day_pct) / expected_move_pct) * 100

                # Build update data
                update_data = {
                    'iv_buildup_pct': iv_metrics.get('iv_buildup_pct'),
                    'iv_collapse_pct': iv_metrics.get('iv_collapse_pct'),
                    'iv_recovery_pct': iv_metrics.get('iv_recovery_pct'),
                    'iv_crush_severity': iv_metrics.get('iv_crush_severity'),
                    'expected_move_pct': expected_move_pct,
                    'move_vs_expected_pct': move_vs_expected_pct
                }
                update_data = clean_database_row(update_data)

                if verbose:
                    logging.info("  {} ({}) - collapse: {:.1f}%, severity: {}, "
                                 "expected: {:.2f}%, vs_expected: {:.0f}%".format(
                        symbol, earnings_date,
                        update_data.get('iv_collapse_pct') or 0,
                        update_data.get('iv_crush_severity') or 'N/A',
                        update_data.get('expected_move_pct') or 0,
                        update_data.get('move_vs_expected_pct') or 0
                    ))

                if not dry_run:
                    cursor.execute("""
                        UPDATE earnings_moves
                        SET iv_buildup_pct = ?,
                            iv_collapse_pct = ?,
                            iv_recovery_pct = ?,
                            iv_crush_severity = ?,
                            expected_move_pct = ?,
                            move_vs_expected_pct = ?
                        WHERE move_id = ?
                    """, (
                        update_data.get('iv_buildup_pct'),
                        update_data.get('iv_collapse_pct'),
                        update_data.get('iv_recovery_pct'),
                        update_data.get('iv_crush_severity'),
                        update_data.get('expected_move_pct'),
                        update_data.get('move_vs_expected_pct'),
                        move_id
                    ))
                    conn.commit()

                stats['updated'] += 1

            except Exception as e:
                logging.error("  Error processing {} (move_id={}): {}".format(symbol, move_id, e))
                stats['errors'] += 1

    return stats


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Backfill IV metrics and expected moves in earnings_moves table')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview what would be updated without writing')
    parser.add_argument('--verbose', action='store_true',
                        help='Show details for each event')

    args = parser.parse_args()

    # Setup logging
    sys.stdout.reconfigure(encoding='utf-8')
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    print("=" * 60)
    print("EARNINGS MOVES: IV & EXPECTED MOVE BACKFILL")
    print("=" * 60)

    if args.dry_run:
        print("*** DRY RUN MODE — no database writes ***\n")

    stats = run_backfill(dry_run=args.dry_run, verbose=args.verbose)

    print("\n" + "=" * 60)
    print("BACKFILL RESULTS")
    print("=" * 60)
    print("Total rows with NULL iv_collapse: {:,}".format(stats['total_null']))
    print("  Matched to earnings_events:     {:,}".format(stats['matched']))
    print("  Orphaned (no events record):    {:,}".format(stats['orphaned']))
    print("  Updated successfully:           {:,}".format(stats['updated']))
    print("  Skipped (no IV data):           {:,}".format(stats['skipped_no_iv']))
    print("  Errors:                         {:,}".format(stats['errors']))
    print("=" * 60)

    if args.dry_run and stats['updated'] > 0:
        print("\nTo apply these changes, run without --dry-run")

    if stats['orphaned'] > 0:
        print("\nNOTE: {:,} rows have event_ids not in production earnings_events".format(
            stats['orphaned']))
        print("  These events were archived to sector databases.")
        print("  Archive-spanning backfill is a future enhancement.")

    return 0 if stats['errors'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
