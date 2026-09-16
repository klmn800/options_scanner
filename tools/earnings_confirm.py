#!/usr/bin/env python3
"""
Earnings Date Confirmation Tool (earnings_confirm.py)
-----------------------------------------------------
CLI tool for manually confirming earnings dates. Writes directly to
datalake.db (production). Designed for both human use (Ben) and
agent use (earnings researcher agent).

Usage:
  # Confirm a date (time optional) -- --date and --by are required
  python tools/earnings_confirm.py --symbol VZ --date 2026-04-27 --time bmo --by ben

  # Fix only the time -- the date's confirmation state is left untouched
  python tools/earnings_confirm.py --symbol VZ --time bmo --time-only --by agent

  # List all confirmed symbols
  python tools/earnings_confirm.py --list

  # List unconfirmed within 21 days
  python tools/earnings_confirm.py --list-unconfirmed

  # Bulk import from CSV (symbol,date,time per line; every row needs a date)
  python tools/earnings_confirm.py --bulk-file corrections.csv --by ben

Safety rules (added 2026-09-14):
  - A confirmation always asserts the date, so --date is required. A bare
    --symbol used to confirm the row as-is; that is now an error. To read a
    row, query earnings_upcoming -- this tool only writes.
  - --by has no default. It used to default to 'ben', which stamped Ben's
    name on accidental agent confirms.
  - A row confirmed by ben can only be modified with --by ben.

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
VALID_BY = ('ben', 'agent')


def _normalize_time(time_str):
    """Return the DB form of a time ('bmo'/'amc'/'dmh'/'Unknown'), or None if invalid."""
    time_str = time_str.lower().strip()
    if time_str not in VALID_TIMES:
        return None
    # Capitalize for DB storage (matches Finnhub format)
    return time_str if time_str in ('bmo', 'amc', 'dmh') else 'Unknown'


def _ben_lock_error(symbol, old_confirmed, old_confirmed_by, by):
    """Error message if `by` would modify a row Ben confirmed, else None."""
    if old_confirmed and old_confirmed_by == 'ben' and by != 'ben':
        return '{}: confirmed by ben -- only --by ben may modify it'.format(symbol)
    return None


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def confirm_symbol(symbol, date_str, time_str=None, *, confirmed_by, db_path=None):
    """Confirm an earnings date for a symbol.

    A confirmation always asserts the date, so date_str is required. To fix
    only the time without confirming the date, use set_time().

    Args:
        symbol: Stock ticker
        date_str: Earnings date (YYYY-MM-DD) -- required
        time_str: Earnings time (bmo/amc/dmh/unknown) or None to keep current
        confirmed_by: Who confirmed ('ben' or 'agent') -- required, no default
        db_path: Override database path

    Returns:
        dict with keys: success, message, changes
    """
    db = db_path or DB_PATH
    symbol = symbol.upper().strip()

    if confirmed_by not in VALID_BY:
        return {'success': False, 'message': '{}: invalid confirmed_by: {!r} (use ben/agent)'.format(
            symbol, confirmed_by)}
    if not date_str:
        return {'success': False, 'message': '{}: a date is required to confirm '
                '(use set_time / --time-only for a time-only fix)'.format(symbol)}
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return {'success': False, 'message': '{}: invalid date format: {}'.format(symbol, date_str)}
    time_val = None
    if time_str:
        time_val = _normalize_time(time_str)
        if time_val is None:
            return {'success': False, 'message': '{}: invalid time: {} (use bmo/amc/dmh/unknown)'.format(
                symbol, time_str)}

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

    lock_err = _ben_lock_error(symbol, old_confirmed, old_confirmed_by, confirmed_by)
    if lock_err:
        conn.close()
        return {'success': False, 'message': lock_err}

    # Warn if overwriting someone else's confirmation with a different date
    if old_confirmed and old_confirmed_by and old_confirmed_by != confirmed_by and date_str != old_date:
        print("  WARNING: Overwriting {} confirmation (was {}) with {}".format(
            old_confirmed_by, old_date, date_str))

    # Build update
    changes = []
    update_cols = []
    update_vals = []

    if date_str != old_date:
        days_diff = (datetime.strptime(date_str, '%Y-%m-%d') - datetime.strptime(old_date, '%Y-%m-%d')).days
        changes.append('date changed {:+d}d'.format(days_diff))
    else:
        changes.append('date unchanged')
    update_cols.append('earnings_date = ?')
    update_vals.append(date_str)

    if time_val:
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

    final_time = time_val or old_time
    msg = '{}: confirmed {} {} (was: {} {}) [{}]'.format(
        symbol, date_str, final_time, old_date, old_time, ', '.join(changes))

    return {'success': True, 'message': msg, 'changes': changes}


def set_time(symbol, time_str, *, set_by, db_path=None):
    """Set only the earnings time for a symbol.

    Leaves earnings_date and every date_confirmed* field untouched: a time fix
    is not a date confirmation. (Routing time fixes through confirm_symbol is
    how unsourced dates got locked -- KMX/PAYX, 2026-09-08.)

    Args:
        symbol: Stock ticker
        time_str: Earnings time (bmo/amc/dmh/unknown)
        set_by: Who is writing ('ben' or 'agent') -- only used for the ben lock
        db_path: Override database path

    Returns:
        dict with keys: success, message
    """
    db = db_path or DB_PATH
    symbol = symbol.upper().strip()

    if set_by not in VALID_BY:
        return {'success': False, 'message': '{}: invalid set_by: {!r} (use ben/agent)'.format(symbol, set_by)}
    time_val = _normalize_time(time_str or '')
    if time_val is None:
        return {'success': False, 'message': '{}: invalid time: {} (use bmo/amc/dmh/unknown)'.format(
            symbol, time_str)}

    conn = sqlite3.connect(db, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")

    row = conn.execute(
        "SELECT earnings_date, earnings_time, date_confirmed, date_confirmed_by "
        "FROM earnings_upcoming WHERE symbol = ?", (symbol,)
    ).fetchone()
    if not row:
        conn.close()
        return {'success': False, 'message': '{}: not found in earnings_upcoming'.format(symbol)}

    old_date, old_time, old_confirmed, old_confirmed_by = row

    lock_err = _ben_lock_error(symbol, old_confirmed, old_confirmed_by, set_by)
    if lock_err:
        conn.close()
        return {'success': False, 'message': lock_err}

    conn.execute("UPDATE earnings_upcoming SET earnings_time = ? WHERE symbol = ?", (time_val, symbol))
    conn.commit()
    conn.close()

    state = 'date still confirmed by {}'.format(old_confirmed_by) if old_confirmed else 'date NOT confirmed'
    msg = '{}: time set to {} (was: {}) on {} [{}]'.format(symbol, time_val, old_time, old_date, state)
    return {'success': True, 'message': msg}


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


def bulk_import(csv_path, *, confirmed_by, db_path=None):
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
  python tools/earnings_confirm.py --symbol VZ --date 2026-04-27 --time bmo --by ben
  python tools/earnings_confirm.py --symbol VZ --time bmo --time-only --by agent
  python tools/earnings_confirm.py --list
  python tools/earnings_confirm.py --list-unconfirmed
  python tools/earnings_confirm.py --bulk-file corrections.csv --by ben

This tool only writes. To read a row, query earnings_upcoming.
A row confirmed by ben can only be modified with --by ben.
        """
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--symbol', help='Symbol to confirm (requires --date, or --time-only)')
    mode.add_argument('--list', action='store_true', help='List all confirmed earnings dates')
    mode.add_argument('--list-unconfirmed', action='store_true',
                      help='List unconfirmed symbols within 21 days')
    mode.add_argument('--bulk-file', help='CSV file for batch import (symbol,date,time per line)')

    parser.add_argument('--date', help='Earnings date (YYYY-MM-DD) -- required to confirm')
    parser.add_argument('--time', help='Earnings time (bmo/amc/dmh/unknown)')
    parser.add_argument('--time-only', action='store_true',
                        help='With --symbol and --time: set the time only; the date is NOT confirmed')
    parser.add_argument('--by', choices=VALID_BY,
                        help='Who is writing: ben or agent (required for --symbol and --bulk-file)')
    parser.add_argument('--days', type=int, default=21,
                        help='Days ahead for --list-unconfirmed (default: 21)')

    args = parser.parse_args()

    # Validate before touching the DB -- parser.error() exits with status 2
    if (args.symbol or args.bulk_file) and not args.by:
        parser.error('--by is required (ben or agent)')
    if args.time_only and not args.symbol:
        parser.error('--time-only requires --symbol')
    if args.symbol:
        if args.time_only:
            if not args.time or args.date:
                parser.error('--time-only takes --time and no --date')
        elif not args.date:
            parser.error('--date is required to confirm. For a time-only fix use '
                         '--time-only --time T. To read a row, query earnings_upcoming '
                         '-- this tool only writes.')

    # Reconfigure stdout for UTF-8 (Windows)
    sys.stdout.reconfigure(encoding='utf-8')

    if args.list:
        list_confirmed()
    elif args.list_unconfirmed:
        list_unconfirmed(days_ahead=args.days)
    elif args.bulk_file:
        bulk_import(args.bulk_file, confirmed_by=args.by)
    elif args.symbol:
        if args.time_only:
            result = set_time(args.symbol, args.time, set_by=args.by)
        else:
            result = confirm_symbol(args.symbol, args.date, args.time, confirmed_by=args.by)
        if result['success']:
            print(result['message'])
        else:
            print("ERROR: {}".format(result['message']))
            sys.exit(1)


if __name__ == '__main__':
    main()
