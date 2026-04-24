#!/usr/bin/env python3
"""
Earnings Date Confirmation Tool (earnings_confirm.py)
-----------------------------------------------------
CLI tool for manually confirming earnings dates. Writes directly to
datalake.db (production). Designed for both human use (Ben) and
agent use (earnings researcher agent).

Usage:
  # Confirm with specific date and time
  python tools/earnings_confirm.py --symbol VZ --date 2026-04-27 --time bmo

  # Confirm current date/time as-is
  python tools/earnings_confirm.py --symbol VZ

  # List all confirmed symbols
  python tools/earnings_confirm.py --list

  # List unconfirmed within 21 days
  python tools/earnings_confirm.py --list-unconfirmed

  # Bulk import from CSV (symbol,date,time per line)
  python tools/earnings_confirm.py --bulk-file corrections.csv

Author: Ben (with Claude Code)
Created: 2026-04-23
"""

import os
import sys
import csv
import sqlite3
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add project root for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from tools.timezone_utils import now_eastern, eastern_isoformat, eastern_date_string
from tools.decimal_formatter import clean_database_row

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(project_root, 'data', 'datalake.db')
VALID_TIMES = {'bmo', 'amc', 'dmh', 'unknown'}


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def confirm_symbol(symbol, date_str=None, time_str=None, confirmed_by='ben', db_path=None):
    """Confirm an earnings date for a symbol.

    Args:
        symbol: Stock ticker
        date_str: Earnings date (YYYY-MM-DD) or None to keep current
        time_str: Earnings time (bmo/amc/dmh) or None to keep current
        confirmed_by: Who confirmed ('ben' or 'agent')
        db_path: Override database path

    Returns:
        dict with keys: success, message, changes
    """
    db = db_path or DB_PATH
    symbol = symbol.upper().strip()

    conn = sqlite3.connect(db, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")

    # Check symbol exists
    row = conn.execute(
        "SELECT earnings_date, earnings_time, date_confirmed, date_confirmed_by, date_confirmed_at "
        "FROM earnings_upcoming WHERE symbol = ?", (symbol,)
    ).fetchone()

    if not row:
        conn.close()
        return {'success': False, 'message': '{}: not found in earnings_upcoming'.format(symbol)}

    old_date, old_time, old_confirmed, old_confirmed_by, old_confirmed_at = row

    # Warn if overwriting someone else's confirmation with a different date
    if old_confirmed and old_confirmed_by and date_str:
        if old_confirmed_by != confirmed_by and date_str != old_date:
            print("  WARNING: Overwriting {} confirmation (was {}) with {}".format(
                old_confirmed_by, old_date, date_str))

    # Build update
    changes = []
    update_cols = []
    update_vals = []

    if date_str:
        # Validate date format
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            conn.close()
            return {'success': False, 'message': '{}: invalid date format: {}'.format(symbol, date_str)}

        if date_str != old_date:
            days_diff = (datetime.strptime(date_str, '%Y-%m-%d') - datetime.strptime(old_date, '%Y-%m-%d')).days
            changes.append('date changed {:+d}d'.format(days_diff))
        else:
            changes.append('date unchanged')
        update_cols.append('earnings_date = ?')
        update_vals.append(date_str)
    else:
        changes.append('date unchanged')

    if time_str:
        time_str = time_str.lower().strip()
        if time_str not in VALID_TIMES:
            conn.close()
            return {'success': False, 'message': '{}: invalid time: {} (use bmo/amc/dmh/unknown)'.format(
                symbol, time_str)}
        # Capitalize for DB storage (matches Finnhub format)
        time_val = time_str if time_str in ('bmo', 'amc', 'dmh') else 'Unknown'
        if time_val != old_time:
            changes.append('time updated')
        else:
            changes.append('time unchanged')
        update_cols.append('earnings_time = ?')
        update_vals.append(time_val)
    else:
        changes.append('time unchanged')

    # Always set confirmation fields
    update_cols.append('date_confirmed = 1')
    update_cols.append('date_confirmed_by = ?')
    update_vals.append(confirmed_by)
    update_cols.append('date_confirmed_at = ?')
    # Set timestamp AFTER clean_database_row would run (gotcha: it nullifies dates)
    update_vals.append(eastern_isoformat())

    sql = "UPDATE earnings_upcoming SET {} WHERE symbol = ?".format(', '.join(update_cols))
    update_vals.append(symbol)

    conn.execute(sql, update_vals)
    conn.commit()
    conn.close()

    final_date = date_str or old_date
    final_time = time_str or old_time
    msg = '{}: confirmed {} {} (was: {} {}) [{}]'.format(
        symbol, final_date, final_time, old_date, old_time, ', '.join(changes))

    return {'success': True, 'message': msg, 'changes': changes}


def list_confirmed(db_path=None):
    """List all confirmed earnings dates."""
    db = db_path or DB_PATH
    conn = sqlite3.connect(db, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")

    rows = conn.execute("""
        SELECT symbol, earnings_date, earnings_time, date_confirmed_by, date_confirmed_at
        FROM earnings_upcoming
        WHERE date_confirmed = 1
        ORDER BY earnings_date ASC, symbol ASC
    """).fetchall()
    conn.close()

    if not rows:
        print("No confirmed earnings dates.")
        return

    print("\nConfirmed Earnings Dates ({} symbols):".format(len(rows)))
    print("{:<8} {:<12} {:<8} {:<8} {}".format('Symbol', 'Date', 'Time', 'By', 'Confirmed At'))
    print("-" * 60)
    for sym, edate, etime, by, at in rows:
        print("{:<8} {:<12} {:<8} {:<8} {}".format(
            sym, edate or '?', etime or '?', by or '?', (at or '?')[:19]))


def list_unconfirmed(db_path=None, days_ahead=21):
    """List unconfirmed symbols within N days."""
    db = db_path or DB_PATH
    today = eastern_date_string()

    conn = sqlite3.connect(db, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")

    rows = conn.execute("""
        SELECT symbol, earnings_date, earnings_time,
               CAST(julianday(earnings_date) - julianday(?) AS INTEGER) as days_away
        FROM earnings_upcoming
        WHERE date_confirmed = 0
          AND earnings_date >= ?
          AND earnings_date <= DATE(?, '+{} days')
        ORDER BY earnings_date ASC, symbol ASC
    """.format(days_ahead), (today, today, today)).fetchall()
    conn.close()

    if not rows:
        print("No unconfirmed earnings within {} days.".format(days_ahead))
        return

    print("\nUnconfirmed Earnings ({} symbols, within {} days):".format(len(rows), days_ahead))
    print("{:<8} {:<12} {:<8} {}".format('Symbol', 'Date', 'Time', 'Days Away'))
    print("-" * 44)
    for sym, edate, etime, days in rows:
        time_flag = ' <-- Unknown' if etime == 'Unknown' else ''
        print("{:<8} {:<12} {:<8} {:>3}d{}".format(
            sym, edate or '?', etime or '?', days or 0, time_flag))


def bulk_import(csv_path, confirmed_by='ben', db_path=None):
    """Import confirmations from CSV file (symbol,date,time per line)."""
    if not os.path.exists(csv_path):
        print("ERROR: File not found: {}".format(csv_path))
        return

    success_count = 0
    error_count = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for line_num, row in enumerate(reader, 1):
            # Skip header/empty/comment lines
            if not row or row[0].strip().lower() == 'symbol' or row[0].strip().startswith('#'):
                continue

            symbol = row[0].strip()
            date_str = row[1].strip() if len(row) > 1 and row[1].strip() else None
            time_str = row[2].strip() if len(row) > 2 and row[2].strip() else None

            result = confirm_symbol(symbol, date_str, time_str,
                                    confirmed_by=confirmed_by, db_path=db_path)
            if result['success']:
                print("  {}".format(result['message']))
                success_count += 1
            else:
                print("  ERROR line {}: {}".format(line_num, result['message']))
                error_count += 1

    print("\nBulk import complete: {} confirmed, {} errors".format(success_count, error_count))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """Command-line interface for earnings date confirmation."""
    parser = argparse.ArgumentParser(
        description="Earnings Date Confirmation Tool — confirm, list, and bulk-import earnings dates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/earnings_confirm.py --symbol VZ --date 2026-04-27 --time bmo
  python tools/earnings_confirm.py --symbol VZ
  python tools/earnings_confirm.py --list
  python tools/earnings_confirm.py --list-unconfirmed
  python tools/earnings_confirm.py --bulk-file corrections.csv
        """
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--symbol', help='Symbol to confirm')
    mode.add_argument('--list', action='store_true', help='List all confirmed earnings dates')
    mode.add_argument('--list-unconfirmed', action='store_true',
                      help='List unconfirmed symbols within 21 days')
    mode.add_argument('--bulk-file', help='CSV file for batch import (symbol,date,time per line)')

    parser.add_argument('--date', help='Earnings date (YYYY-MM-DD)')
    parser.add_argument('--time', help='Earnings time (bmo/amc/dmh/unknown)')
    parser.add_argument('--by', default='ben', help='Confirmed by (default: ben)')
    parser.add_argument('--days', type=int, default=21,
                        help='Days ahead for --list-unconfirmed (default: 21)')

    args = parser.parse_args()

    # Reconfigure stdout for UTF-8 (Windows)
    sys.stdout.reconfigure(encoding='utf-8')

    if args.list:
        list_confirmed()
    elif args.list_unconfirmed:
        list_unconfirmed(days_ahead=args.days)
    elif args.bulk_file:
        bulk_import(args.bulk_file, confirmed_by=args.by)
    elif args.symbol:
        result = confirm_symbol(args.symbol, args.date, args.time, confirmed_by=args.by)
        if result['success']:
            print(result['message'])
        else:
            print("ERROR: {}".format(result['message']))
            sys.exit(1)


if __name__ == '__main__':
    main()
