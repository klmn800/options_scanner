#!/usr/bin/env python3
"""
Paper Poll
==========
Polls Tradier sandbox for fill status on orders we submitted and writes
fills into `paper_executions` / updates `paper_positions`. Also takes the
daily balance snapshot when invoked with --snapshot.

Phase 1 (State A) tool. Run by hand after placing orders. Phase B's
close engine fires its own close orders and this poller picks them up
on the next run (or you can chain `paper_close_engine.py && paper_poll.py`).

Usage:
    python tools/paper_poll.py                # Poll all unrecorded fills
    python tools/paper_poll.py --snapshot     # Record today's balance row
    python tools/paper_poll.py --verbose      # Verbose logging
    python tools/paper_poll.py --order-id ID  # Poll a single Tradier order id

Reads/writes: data/paper.db (paper_* tables)
Dependencies: core/tradier_paper.py, tools/paper_trading.py
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

# Project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

sys.stdout.reconfigure(encoding='utf-8')

from core.tradier_paper import TradierPaperBroker
from tools.paper_trading import (
    _ensure_schema,
    _is_closing_action,
    get_connection,
    open_or_update_position,
    pop_pending_conditions,
    record_execution,
    snapshot_balance,
)

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(project_root, 'config.json')

# Tradier order statuses considered terminal (no further fills expected)
TERMINAL_STATUSES = {'filled', 'partially_filled', 'canceled', 'rejected', 'expired', 'error'}
FILL_STATUSES = {'filled', 'partially_filled'}


def _load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def _occ_to_components(option_symbol):
    """Parse an OCC option symbol like 'SPY260619C00500000' into components.

    Returns dict with: underlying, expiration_date (YYYY-MM-DD), option_type
    ('call'/'put'), strike (float).
    Returns None if parsing fails.
    """
    if not option_symbol or not isinstance(option_symbol, str):
        return None
    s = option_symbol.upper().strip()
    # Walk from the right to find the C/P flag at position -9 from end
    # OCC format: ROOT(1-6) + YYMMDD(6) + C/P(1) + STRIKE*1000(8) = 15+ chars
    if len(s) < 15:
        return None
    try:
        strike_raw = s[-8:]
        flag = s[-9]
        date_raw = s[-15:-9]
        root = s[:-15]
        if flag not in ('C', 'P'):
            return None
        year = int(date_raw[0:2]) + 2000
        month = int(date_raw[2:4])
        day = int(date_raw[4:6])
        strike = int(strike_raw) / 1000.0
        return {
            'underlying': root,
            'expiration_date': "{:04d}-{:02d}-{:02d}".format(year, month, day),
            'option_type': 'call' if flag == 'C' else 'put',
            'strike': strike,
        }
    except (ValueError, IndexError):
        return None


def _normalize_side(side, instrument_class):
    """Tradier returns side as-is. We keep stock as buy/sell and option as
    the four-state form. Already in the right format — just lowercase."""
    return (side or '').lower()


def _recorded_qty(conn, tradier_order_id):
    """Sum of quantities already recorded against this Tradier order id.

    Used so partial fills that complete later can be recorded as incremental
    delta rows rather than skipped wholesale.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM paper_executions WHERE tradier_order_id = ?",
        (str(tradier_order_id),),
    )
    row = cur.fetchone()
    return float(row[0] or 0) if row else 0.0


def _process_order(conn, order, verbose=False):
    """Record fills from a single Tradier order response if not already recorded.

    Returns dict with: order_id, status, action_taken.
    """
    order_id = order.get('id')
    status = (order.get('status') or '').lower()
    instrument_class = (order.get('class') or '').lower()

    if not order_id:
        return {'order_id': None, 'status': status, 'action_taken': 'skip_no_id'}

    if status in ('canceled', 'rejected', 'expired', 'error'):
        msg = "Tradier order {} status={} reason={}".format(
            order_id, status, order.get('reason') or '-'
        )
        print(msg)
        return {'order_id': order_id, 'status': status, 'action_taken': 'log_terminal'}

    if status not in FILL_STATUSES:
        if verbose:
            print("Order {} status={} — not filled yet, skipping".format(order_id, status))
        return {'order_id': order_id, 'status': status, 'action_taken': 'skip_pending'}

    # Build execution dict from order. Idempotency tracks cumulative quantity:
    # record only the delta between Tradier's reported exec_quantity and what
    # we've already persisted. This catches partial fills that complete later.
    tradier_exec_qty = order.get('exec_quantity') or 0
    try:
        tradier_exec_qty = float(tradier_exec_qty)
    except (TypeError, ValueError):
        tradier_exec_qty = 0
    if tradier_exec_qty <= 0:
        # Tradier marked filled but reported no exec_quantity — fall back to quantity
        try:
            tradier_exec_qty = float(order.get('quantity') or 0)
        except (TypeError, ValueError):
            tradier_exec_qty = 0
    if tradier_exec_qty <= 0:
        return {'order_id': order_id, 'status': status, 'action_taken': 'skip_zero_qty'}

    already_recorded = _recorded_qty(conn, order_id)
    exec_qty = tradier_exec_qty - already_recorded
    if exec_qty <= 0:
        if verbose:
            print("Order {} fully recorded ({} of {}) — skipping".format(
                order_id, already_recorded, tradier_exec_qty))
        return {'order_id': order_id, 'status': status, 'action_taken': 'skip_recorded'}

    fill_price = order.get('avg_fill_price') or order.get('price') or 0
    try:
        fill_price = float(fill_price)
    except (TypeError, ValueError):
        fill_price = 0

    tag = order.get('tag')  # Tradier echoes our tag back if we sent one
    side = _normalize_side(order.get('side'), instrument_class)
    symbol = order.get('symbol')
    option_symbol = order.get('option_symbol')

    if instrument_class == 'option':
        instrument_type = 'option'
        parsed = _occ_to_components(option_symbol) if option_symbol else None
        option_type = parsed['option_type'] if parsed else None
        strike = parsed['strike'] if parsed else None
        expiration_date = parsed['expiration_date'] if parsed else None
        underlying = parsed['underlying'] if parsed else symbol
    else:
        instrument_type = 'stock'
        option_type = None
        strike = None
        expiration_date = None
        underlying = symbol
        option_symbol = None

    # Tradier order timestamp — try a few field names
    ts = (
        order.get('transaction_date')
        or order.get('create_date')
        or order.get('last_fill_time')
    )

    execution = {
        'execution_timestamp': ts,
        'action': side,
        'instrument_type': instrument_type,
        'symbol': underlying,
        'quantity': exec_qty,
        'fill_price': fill_price,
        'option_type': option_type,
        'strike': strike,
        'expiration_date': expiration_date,
        'option_symbol': option_symbol,
        'tag': tag or 'manual',
        'tradier_order_id': str(order_id),
        'broker': 'tradier_sandbox',
    }

    # Phase B: opening orders may have close conditions stashed by cmd_open.
    # Pop them now so open_or_update_position attaches them to the new
    # paper_positions row. No-op for closing orders.
    if not _is_closing_action(side):
        pending = pop_pending_conditions(conn, order_id)
        if pending:
            execution['close_conditions_json'] = pending
            if verbose:
                print("  applied pending conditions for order_id={}".format(order_id))

    exec_id = record_execution(conn, execution)
    pos_id = open_or_update_position(conn, execution, exec_id)

    print(
        "RECORDED order_id={} side={} {} {}{} @ ${:.4f} -> execution_id={} position_id={}".format(
            order_id,
            side,
            exec_qty,
            symbol,
            " ({})".format(option_symbol) if option_symbol else "",
            fill_price,
            exec_id,
            pos_id,
        )
    )
    return {'order_id': order_id, 'status': status, 'action_taken': 'recorded',
            'execution_id': exec_id, 'position_id': pos_id}


def cmd_poll(broker, conn, target_order_id=None, verbose=False):
    """Poll Tradier for orders and record any new fills."""
    if target_order_id:
        order = broker.get_order(target_order_id)
        if not order:
            print("No order found for id={}".format(target_order_id))
            return 1
        _process_order(conn, order, verbose=verbose)
        return 0

    orders = broker.get_orders()
    if not orders:
        print("No orders on Tradier sandbox.")
        return 0

    counts = {'recorded': 0, 'skip_recorded': 0, 'skip_pending': 0, 'skip_zero_qty': 0,
              'log_terminal': 0, 'skip_no_id': 0}
    for o in orders:
        result = _process_order(conn, o, verbose=verbose)
        action = result.get('action_taken', 'unknown')
        counts[action] = counts.get(action, 0) + 1

    print()
    print("Poll summary: {} order(s) seen".format(len(orders)))
    for k, v in counts.items():
        if v:
            print("  {}: {}".format(k, v))
    return 0


def cmd_snapshot(broker, conn):
    """Take the daily balance snapshot."""
    resp = broker.get_balances()
    if not resp:
        print("ERROR: no balance response from Tradier")
        return 1
    snapshot_date = snapshot_balance(conn, resp)
    print("Snapshot recorded for {}".format(snapshot_date))
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Paper trading poller — records fills from Tradier sandbox',
    )
    parser.add_argument('--snapshot', action='store_true',
                        help='Record today\'s paper_account_snapshots row (instead of polling fills)')
    parser.add_argument('--order-id', help='Poll a single Tradier order id')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    config = _load_config()
    broker = TradierPaperBroker(config)
    conn = get_connection()
    _ensure_schema(conn)
    try:
        if args.snapshot:
            return cmd_snapshot(broker, conn)
        return cmd_poll(broker, conn, target_order_id=args.order_id, verbose=args.verbose)
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
