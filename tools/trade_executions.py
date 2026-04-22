"""
Trade Executions Enrichment Tool.

Narrow gateway for the Trading Advisor agent to enrich trade_executions rows.
Only allows UPDATE on whitelisted columns, single row by ID. No INSERT/DELETE.

Usage:
    python tools/trade_executions.py --show 42
    python tools/trade_executions.py --update 42 --notes "thesis note" --iv 0.35 --underlying 134.20
    python tools/trade_executions.py --list --symbol CC
    python tools/trade_executions.py --list --unreviewed
    python tools/trade_executions.py --latest-unreviewed
    python tools/trade_executions.py --link-trade-call "CC-2026-04-21" 42
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / 'data' / 'datalake.db'
AUDIT_LOG = PROJECT_DIR / 'logs' / 'trade_executions_edits.log'

# Only these columns can be modified
EDITABLE_COLUMNS = {
    'notes': str,
    'trade_call_ref': str,
    'review_status': str,
    'iv_at_fill': float,
    'underlying_price_at_fill': float,
}

# Display columns for --list and --show
LIST_COLUMNS = [
    'id', 'execution_timestamp', 'action', 'symbol', 'option_type',
    'strike', 'expiration_date', 'quantity', 'fill_price', 'review_status',
    'trade_call_ref', 'notes',
]

SHOW_COLUMNS = [
    'id', 'execution_timestamp', 'action', 'instrument_type', 'symbol',
    'quantity', 'fill_price', 'total_cost', 'option_type', 'strike',
    'expiration_date', 'position_key', 'broker', 'source', 'review_status',
    'trade_call_ref', 'notes', 'iv_at_fill', 'underlying_price_at_fill',
    'created_at',
]


def get_connection():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_row(conn, row_id):
    """Fetch a single row by ID. Returns dict or None."""
    row = conn.execute(
        'SELECT * FROM trade_executions WHERE id = ?', (row_id,)
    ).fetchone()
    return dict(row) if row else None


def print_row(row, label=None):
    """Print a single row in a readable format."""
    if label:
        print(f'\n--- {label} ---')
    for col in SHOW_COLUMNS:
        val = row.get(col)
        display = val if val is not None else '(null)'
        print(f'  {col:>25s}: {display}')


def print_list(rows):
    """Print rows in a compact table format."""
    if not rows:
        print('No rows found.')
        return
    # Header
    header = f'{"ID":>4}  {"Date":10}  {"Act":4}  {"Sym":5}  {"Type":4}  {"Strike":>7}  {"Exp":10}  {"Qty":>3}  {"Fill$":>7}  {"Status":12}  {"Ref":20}  Notes'
    print(header)
    print('-' * len(header))
    for r in rows:
        otype = (r['option_type'] or '-')[:4]
        strike = f'{r["strike"]:.1f}' if r['strike'] else '-'
        exp = r['expiration_date'] or '-'
        ts = (r['execution_timestamp'] or '')[:10]
        notes = (r['notes'] or '')[:40]
        ref = (r['trade_call_ref'] or '-')[:20]
        status = (r['review_status'] or '-')[:12]
        print(f'{r["id"]:>4}  {ts:10}  {r["action"]:4}  {r["symbol"]:5}  {otype:4}  {strike:>7}  {exp:10}  {r["quantity"]:>3}  {r["fill_price"]:>7.2f}  {status:12}  {ref:20}  {notes}')


def audit_log(row_id, changes, before):
    """Append one line per changed field to the audit log."""
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(AUDIT_LOG, 'a', encoding='utf-8') as f:
        for col, new_val in changes.items():
            old_val = before.get(col)
            f.write(f'{ts} | id={row_id} | {col}: {repr(old_val)} -> {repr(new_val)} | source=script\n')


def cmd_show(args):
    conn = get_connection()
    row = fetch_row(conn, args.show)
    conn.close()
    if not row:
        print(f'Error: no row with id={args.show}')
        return 1
    print_row(row)
    return 0


def cmd_list(args):
    conn = get_connection()
    cols = ', '.join(LIST_COLUMNS)
    if args.unreviewed:
        rows = conn.execute(
            f"SELECT {cols} FROM trade_executions WHERE review_status = 'unreviewed' ORDER BY id DESC"
        ).fetchall()
    elif args.symbol:
        rows = conn.execute(
            f'SELECT {cols} FROM trade_executions WHERE symbol = ? ORDER BY id DESC LIMIT 20',
            (args.symbol.upper(),)
        ).fetchall()
    else:
        rows = conn.execute(
            f'SELECT {cols} FROM trade_executions ORDER BY id DESC LIMIT 20'
        ).fetchall()
    conn.close()
    print_list([dict(r) for r in rows])
    return 0


def cmd_latest_unreviewed(args):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM trade_executions WHERE review_status = 'unreviewed' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        print('No unreviewed rows.')
        return 0
    print_row(dict(row), label='Latest unreviewed')
    return 0


def cmd_update(args):
    # Collect fields to update
    changes = {}
    if args.notes is not None:
        changes['notes'] = args.notes
    if args.trade_call_ref is not None:
        changes['trade_call_ref'] = args.trade_call_ref
    if args.review_status is not None:
        changes['review_status'] = args.review_status
    if args.iv is not None:
        changes['iv_at_fill'] = round(args.iv, 4)
    if args.underlying is not None:
        changes['underlying_price_at_fill'] = round(args.underlying, 2)

    if not changes:
        print('Error: no fields specified. Use --notes, --iv, --underlying, --trade-call-ref, or --review-status.')
        return 1

    conn = get_connection()
    before = fetch_row(conn, args.update)
    if not before:
        print(f'Error: no row with id={args.update}')
        conn.close()
        return 1

    print_row(before, label='BEFORE')

    set_clause = ', '.join(f'{col} = ?' for col in changes)
    values = list(changes.values()) + [args.update]
    conn.execute(f'UPDATE trade_executions SET {set_clause} WHERE id = ?', values)
    conn.commit()

    after = fetch_row(conn, args.update)
    conn.close()

    print_row(after, label='AFTER')
    audit_log(args.update, changes, before)
    print(f'\nUpdated {len(changes)} field(s) on id={args.update}. Audit log written.')
    return 0


def cmd_link_trade_call(args):
    ref = args.link_trade_call
    row_id = args.row_id
    if not row_id:
        print('Error: --link-trade-call requires a row ID argument.')
        print('Usage: python tools/trade_executions.py --link-trade-call "CC-2026-04-21" 42')
        return 1

    conn = get_connection()
    before = fetch_row(conn, row_id)
    if not before:
        print(f'Error: no row with id={row_id}')
        conn.close()
        return 1

    print_row(before, label='BEFORE')

    changes = {'trade_call_ref': ref, 'review_status': 'active'}
    conn.execute(
        'UPDATE trade_executions SET trade_call_ref = ?, review_status = ? WHERE id = ?',
        (ref, 'active', row_id)
    )
    conn.commit()

    after = fetch_row(conn, row_id)
    conn.close()

    print_row(after, label='AFTER')
    audit_log(row_id, changes, before)
    print(f'\nLinked id={row_id} to trade call "{ref}" and set status=active. Audit log written.')
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Trade executions enrichment tool. UPDATE only, whitelisted columns.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Modes (mutually exclusive)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--show', type=int, metavar='ID', help='Show full row by ID')
    group.add_argument('--update', type=int, metavar='ID', help='Update editable fields on a row')
    group.add_argument('--list', action='store_true', help='List rows (use with --symbol or --unreviewed)')
    group.add_argument('--latest-unreviewed', action='store_true', help='Show most recent unreviewed row')
    group.add_argument('--link-trade-call', type=str, metavar='REF', help='Set trade_call_ref + status=active')

    # Update fields
    parser.add_argument('--notes', type=str, help='Set notes field')
    parser.add_argument('--trade-call-ref', type=str, dest='trade_call_ref', help='Set trade_call_ref field')
    parser.add_argument('--review-status', type=str, dest='review_status', help='Set review_status field')
    parser.add_argument('--iv', type=float, help='Set iv_at_fill (decimal, e.g. 0.35)')
    parser.add_argument('--underlying', type=float, help='Set underlying_price_at_fill')

    # List filters
    parser.add_argument('--symbol', type=str, help='Filter by symbol (with --list)')
    parser.add_argument('--unreviewed', action='store_true', help='Show only unreviewed rows (with --list)')

    # Positional for --link-trade-call
    parser.add_argument('row_id', type=int, nargs='?', help='Row ID (used with --link-trade-call)')

    args = parser.parse_args()

    if args.show is not None:
        return cmd_show(args)
    elif args.update is not None:
        return cmd_update(args)
    elif args.list:
        return cmd_list(args)
    elif args.latest_unreviewed:
        return cmd_latest_unreviewed(args)
    elif args.link_trade_call:
        return cmd_link_trade_call(args)

    return 0


if __name__ == '__main__':
    sys.exit(main())
