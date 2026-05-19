#!/usr/bin/env python3
"""
Paper Trade CLI
===============
Human (or agent) driver for the paper trading platform — submits orders against
the Tradier sandbox, queries positions and balance, computes realized P&L.
Phase 1 (State A) tool from docs/paper_trading/PHASE_1_PLAN.md.

Subcommands (mutually exclusive):
  --open               Submit an opening order (stock or option)
  --close              Submit a closing order for a tracked paper_positions row
  --cancel             Cancel an open Tradier order
  --update-conditions  Modify close-conditions on an open position
  --positions          List open paper positions
  --status             Same as --positions, optionally filtered by --tag
  --balance            Print current Tradier sandbox balance
  --pnl                Print realized P&L grouped by tag

After every order placement, run `python tools/paper_poll.py` to record the
fill into paper_executions / paper_positions.

Phase B close conditions (NULL by default — unmonitored unless flags given):
  --tp N             take_profit_pct          (close when pnl% >= N)
  --sl N             stop_loss_pct            (close when pnl% <= -N; pass negative)
  --max-hold N       max_hold_days            (close after N calendar days)
  --expire-before-dte N    close option at <= N DTE
  --target-above N   underlying_target_above  (close when underlying >= N)
  --target-below N   underlying_target_below  (close when underlying <= N)

Reads/writes: data/paper.db (paper_* tables)
Dependencies: core/tradier_paper.py, tools/paper_trading.py
"""

import argparse
import json
import logging
import os
import sqlite3
import sys

# Project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

sys.stdout.reconfigure(encoding='utf-8')

from core.tradier_paper import TradierPaperBroker, sanitize_tag
from tools.paper_trading import (
    get_connection,
    _ensure_schema,
    build_close_conditions,
    parse_close_conditions,
    summarize_close_conditions,
    set_pending_conditions,
)
from tools.timezone_utils import now_eastern

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(project_root, 'config.json')


def _load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def _fmt_money(v):
    if v is None:
        return '-'
    try:
        return "${:,.2f}".format(float(v))
    except (TypeError, ValueError):
        return str(v)


# ── Subcommand: --balance ────────────────────────────────────────────

def cmd_balance(broker):
    resp = broker.get_balances()
    if not resp:
        print("ERROR: no balance response from Tradier sandbox")
        return 1
    bal = resp.get('balances', resp)
    print("Tradier Sandbox Balance (account {})".format(broker.account_id))
    print("=" * 60)
    print("  account_type     : {}".format(bal.get('account_type')))
    print("  total_equity     : {}".format(_fmt_money(bal.get('total_equity'))))
    print("  total_cash       : {}".format(_fmt_money(bal.get('total_cash'))))
    print("  long_market_value: {}".format(_fmt_money(bal.get('long_market_value'))))
    print("  open_pl          : {}".format(_fmt_money(bal.get('open_pl'))))
    print("  close_pl         : {}".format(_fmt_money(bal.get('close_pl'))))
    # Stock / option buying power nested under cash/margin/pdt
    for sub in ('cash', 'margin', 'pdt'):
        s = bal.get(sub)
        if isinstance(s, dict):
            print("  {} sub-account:".format(sub))
            for k in ('cash_available', 'stock_buying_power', 'option_buying_power'):
                if k in s:
                    print("    {}: {}".format(k, _fmt_money(s.get(k))))
    print()
    print("NOTE: sandbox quotes are 15-min delayed; market-order fills will price against delayed quotes.")
    return 0


# ── Subcommand: --positions / --status ───────────────────────────────

def cmd_positions(conn, tag=None, include_closed=False):
    cursor = conn.cursor()
    sql = """
        SELECT id, position_key, tag, instrument_type, symbol, option_symbol,
               option_type, strike, expiration_date, quantity,
               cost_basis_per_unit, total_cost, opened_at,
               closed_at, exit_price_per_unit, realized_pnl,
               close_reason, status
        FROM paper_positions
    """
    where = []
    params = []
    if not include_closed:
        where.append("status = 'open'")
    if tag:
        where.append("tag = ?")
        params.append(tag)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY opened_at DESC, id DESC"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    if not rows:
        print("No paper positions found.")
        return 0

    # Pull close_conditions_json in a second pass so the SELECT * stayed slim
    cursor.execute(
        "SELECT id, close_conditions_json FROM paper_positions WHERE id IN ({})".format(
            ','.join('?' * len(rows))
        ),
        tuple(r['id'] for r in rows),
    )
    conditions_by_id = {r['id']: r['close_conditions_json'] for r in cursor.fetchall()}

    header = "Paper Positions{}{}".format(
        " (tag={})".format(tag) if tag else "",
        " — including closed" if include_closed else " — open only",
    )
    print(header)
    print("=" * 120)
    print("{:>4}  {:<7}  {:<7}  {:<22}  {:>5}  {:>8}  {:>10}  {:<7}  {:<19}  {:<20}".format(
        "id", "tag", "inst", "symbol/contract", "qty", "cost", "total", "status", "opened_at", "conditions"))
    print("-" * 120)
    for r in rows:
        contract = r['option_symbol'] if r['instrument_type'] == 'option' else r['symbol']
        cond_str = summarize_close_conditions(conditions_by_id.get(r['id']))
        print("{:>4}  {:<7}  {:<7}  {:<22}  {:>5}  {:>8}  {:>10}  {:<7}  {:<19}  {:<20}".format(
            r['id'],
            (r['tag'] or '')[:7],
            r['instrument_type'][:7],
            (contract or '')[:22],
            r['quantity'],
            _fmt_money(r['cost_basis_per_unit']),
            _fmt_money(r['total_cost']),
            r['status'],
            (r['opened_at'] or '')[:19],
            cond_str[:20],
        ))
        if r['status'] == 'closed':
            print("       closed @ {} exit={} pnl={} reason={}".format(
                (r['closed_at'] or '')[:19],
                _fmt_money(r['exit_price_per_unit']),
                _fmt_money(r['realized_pnl']),
                r['close_reason'],
            ))
    return 0


# ── Subcommand: --open ───────────────────────────────────────────────

def cmd_open(broker, conn, args):
    if args.instrument == 'option' and not args.option_symbol:
        print("ERROR: --option-symbol is required when --instrument=option")
        return 2
    if args.type in ('limit', 'stop_limit') and args.price is None:
        print("ERROR: --price is required for limit / stop_limit orders")
        return 2

    raw_tag = args.tag or 'manual'
    tag = sanitize_tag(raw_tag)
    if tag != raw_tag:
        print("NOTE: tag '{}' sanitized to '{}' (Tradier allows letters/digits/'-' only)".format(
            raw_tag, tag))

    if args.instrument == 'stock':
        resp = broker.place_equity_order(
            symbol=args.symbol,
            side=args.side,
            qty=args.qty,
            type_=args.type,
            duration=args.duration,
            price=args.price,
            preview=args.preview,
            tag=tag,
            source_event_id=args.source_event_id,
        )
    else:
        resp = broker.place_option_order(
            underlying=args.symbol,
            option_symbol=args.option_symbol,
            side=args.side,
            qty=args.qty,
            type_=args.type,
            duration=args.duration,
            price=args.price,
            preview=args.preview,
            tag=tag,
            source_event_id=args.source_event_id,
        )

    if not resp:
        print("ERROR: no response from Tradier — check logs / credentials")
        return 1

    print("Tradier response:")
    print(json.dumps(resp, indent=2, default=str))
    order = resp.get('order') if isinstance(resp, dict) else None
    if not order:
        return 1
    order_id = order.get('id')
    status = order.get('status', '?')
    if args.preview:
        print()
        print("PREVIEW only — no order was placed.")
        return 0
    if status and str(status).lower() in ('rejected', 'error'):
        print()
        print("WARNING: order returned status={}".format(status))
        return 1
    # Stash close conditions (if any) keyed by tradier_order_id. The poller
    # pops these when the fill arrives and copies them onto paper_positions.
    # If the order is rejected/cancelled the pending row sits harmlessly.
    try:
        conditions_json = build_close_conditions(
            take_profit_pct=args.tp,
            stop_loss_pct=args.sl,
            max_hold_days=args.max_hold,
            expire_before_dte=args.expire_before_dte,
            underlying_target_above=args.target_above,
            underlying_target_below=args.target_below,
        )
    except ValueError as e:
        print("ERROR: invalid close condition: {}".format(e))
        return 2

    if conditions_json:
        set_pending_conditions(conn, order_id, conditions_json)
        print("    close conditions: {}".format(summarize_close_conditions(conditions_json)))
    else:
        print("    close conditions: unmonitored (no --tp/--sl/--max-hold/... flags)")

    print()
    print("ORDER SUBMITTED: id={} status={}".format(order_id, status))
    print("Next step: run `python tools/paper_poll.py` to record the fill once Tradier reports it.")
    return 0


# ── Subcommand: --close ──────────────────────────────────────────────

def cmd_close(broker, conn, args):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, position_key, tag, instrument_type, symbol, option_symbol,
               option_type, strike, expiration_date, quantity, status
        FROM paper_positions
        WHERE id = ?
    """, (args.position_id,))
    row = cursor.fetchone()
    if not row:
        print("ERROR: no paper_positions row with id={}".format(args.position_id))
        return 2
    if row['status'] not in ('open',):
        # 'closing' = previous close still pending; 'closed' = nothing to do
        print("ERROR: position id={} is status={} (must be 'open' to close)".format(
            row['id'], row['status']))
        return 2

    if row['instrument_type'] == 'option':
        # Determine close side based on a normal long-only paper trade pattern.
        # We don't track open vs short here — Phase 1 assumes long opens.
        close_side = 'sell_to_close'
        resp = broker.place_option_order(
            underlying=row['symbol'],
            option_symbol=row['option_symbol'],
            side=close_side,
            qty=int(row['quantity']),
            type_='market',
            duration='day',
            tag=row['tag'],
        )
    else:
        close_side = 'sell'
        resp = broker.place_equity_order(
            symbol=row['symbol'],
            side=close_side,
            qty=int(row['quantity']),
            type_='market',
            duration='day',
            tag=row['tag'],
        )

    if not resp:
        print("ERROR: no response from Tradier")
        return 1

    print("Tradier close response:")
    print(json.dumps(resp, indent=2, default=str))
    order = resp.get('order') if isinstance(resp, dict) else None
    if not order:
        return 1
    order_id = order.get('id')
    status = order.get('status', '?')
    if status and str(status).lower() in ('rejected', 'error'):
        print()
        print("WARNING: close order returned status={}".format(status))
        return 1

    # Phase B: flip status to 'closing' immediately so the engine doesn't
    # also fire a close on the next cycle (idempotency). The poller will
    # complete the transition to 'closed' when the fill is recorded.
    closing_submitted_at = now_eastern().isoformat(sep=' ', timespec='seconds')
    cursor.execute(
        "UPDATE paper_positions SET status='closing', close_reason=?, "
        "closing_submitted_at=? WHERE id=?",
        (args.reason or 'manual', closing_submitted_at, row['id']),
    )
    conn.commit()

    print()
    print("CLOSE ORDER SUBMITTED: id={} status={} side={}".format(order_id, status, close_side))
    print("Position id={} → status='closing' (poll to flip to 'closed' on fill)".format(row['id']))
    print("Next step: run `python tools/paper_poll.py` to record the closing fill.")
    return 0


# ── Subcommand: --update-conditions ──────────────────────────────────

def cmd_update_conditions(conn, args):
    """Modify close-conditions on an existing open position.

    Pass condition flags to overwrite, OR --clear to wipe all conditions
    back to NULL (= unmonitored). Without any condition flags or --clear,
    just prints current conditions.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, status, close_conditions_json FROM paper_positions WHERE id=?",
        (args.position_id,),
    )
    row = cursor.fetchone()
    if not row:
        print("ERROR: no paper_positions row with id={}".format(args.position_id))
        return 2
    if row['status'] != 'open':
        print("ERROR: position id={} is status={} (must be 'open' to update conditions)".format(
            row['id'], row['status']))
        return 2

    current = row['close_conditions_json']
    print("Position id={} — current conditions: {}".format(
        row['id'], summarize_close_conditions(current)))

    if args.clear:
        cursor.execute(
            "UPDATE paper_positions SET close_conditions_json=NULL WHERE id=?",
            (row['id'],),
        )
        conn.commit()
        print("CLEARED — position is now unmonitored.")
        return 0

    # Any condition flag set?
    has_any = any(getattr(args, k) is not None for k in
                  ('tp', 'sl', 'max_hold', 'expire_before_dte', 'target_above', 'target_below'))
    if not has_any:
        print("(no condition flags passed; nothing changed. Use --clear to wipe, or pass --tp/--sl/etc.)")
        return 0

    try:
        new_json = build_close_conditions(
            take_profit_pct=args.tp,
            stop_loss_pct=args.sl,
            max_hold_days=args.max_hold,
            expire_before_dte=args.expire_before_dte,
            underlying_target_above=args.target_above,
            underlying_target_below=args.target_below,
        )
    except ValueError as e:
        print("ERROR: invalid close condition: {}".format(e))
        return 2

    cursor.execute(
        "UPDATE paper_positions SET close_conditions_json=? WHERE id=?",
        (new_json, row['id']),
    )
    conn.commit()
    print("UPDATED — new conditions: {}".format(summarize_close_conditions(new_json)))
    return 0


# ── Subcommand: --cancel ─────────────────────────────────────────────

def cmd_cancel(broker, args):
    resp = broker.cancel_order(args.order_id)
    if not resp:
        print("ERROR: cancel failed — check order id and logs")
        return 1
    print(json.dumps(resp, indent=2, default=str))
    return 0


# ── Subcommand: --pnl ────────────────────────────────────────────────

def cmd_pnl(conn, tag=None, since=None):
    """Realized P&L by tag.

    Counts every row with a non-null realized_pnl — that includes closed
    positions AND open positions where partial closes have accumulated P&L.
    `--since` filters by closed_at when present; open partial-close rows have
    closed_at NULL so they're only filtered out when --since is set.
    """
    cursor = conn.cursor()
    sql = """
        SELECT tag,
               COUNT(*) AS n_rows,
               SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) AS n_closed,
               SUM(realized_pnl) AS total_pnl,
               AVG(realized_pnl) AS avg_pnl
        FROM paper_positions
        WHERE realized_pnl IS NOT NULL
    """
    params = []
    if tag:
        sql += " AND tag = ?"
        params.append(tag)
    if since:
        sql += " AND closed_at >= ?"
        params.append(since)
    sql += " GROUP BY tag ORDER BY total_pnl DESC"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    if not rows:
        print("No realized paper P&L yet.")
        return 0
    print("Realized P&L by tag (n_rows includes open positions with partial-close P&L)")
    print("=" * 72)
    print("{:<24} {:>6} {:>8} {:>14} {:>14}".format(
        "tag", "n_rows", "closed", "total_pnl", "avg_pnl"))
    print("-" * 72)
    grand_total = 0.0
    for r in rows:
        total = float(r['total_pnl'] or 0)
        grand_total += total
        print("{:<24} {:>6} {:>8} {:>14} {:>14}".format(
            (r['tag'] or '(none)')[:24],
            r['n_rows'],
            r['n_closed'],
            _fmt_money(total),
            _fmt_money(r['avg_pnl']),
        ))
    print("-" * 72)
    print("{:<24} {:>6} {:>8} {:>14}".format("TOTAL", "", "", _fmt_money(grand_total)))
    return 0


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Paper Trading CLI (Tradier sandbox)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --balance
  %(prog)s --positions
  %(prog)s --positions --tag manual_test
  %(prog)s --open --instrument stock --symbol SPY --side buy --qty 10 --type market --tag manual_test
  %(prog)s --open --instrument option --symbol SPY --option-symbol SPY260619C00500000 \\
           --side buy_to_open --qty 1 --type market --tag manual_test
  %(prog)s --close --position-id 3 --reason manual
  %(prog)s --cancel --order-id 12345
  %(prog)s --pnl --tag manual_test
        """
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--open', action='store_true', help='Submit an opening order')
    group.add_argument('--close', action='store_true', help='Submit a closing order for a tracked position')
    group.add_argument('--cancel', action='store_true', help='Cancel an open Tradier order')
    group.add_argument('--update-conditions', dest='update_conditions', action='store_true',
                       help='Modify close-conditions on an open position')
    group.add_argument('--positions', action='store_true', help='List paper positions (open by default)')
    group.add_argument('--status', action='store_true', help='Alias for --positions')
    group.add_argument('--balance', action='store_true', help='Print current Tradier sandbox balance')
    group.add_argument('--pnl', action='store_true', help='Print realized P&L grouped by tag')

    # Shared flags
    parser.add_argument('--tag', default=None,
                        help="Position tag. For --open, defaults to 'manual' if omitted. "
                             "For --positions / --pnl, None means 'no filter'.")

    # --open flags
    parser.add_argument('--instrument', choices=['stock', 'option'], help='Instrument type for --open')
    parser.add_argument('--symbol', help='Underlying ticker')
    parser.add_argument('--option-symbol', help='OCC option symbol (for --instrument option)')
    parser.add_argument('--side', help='Order side (buy/sell/buy_to_open/sell_to_close/...)')
    parser.add_argument('--qty', type=int, help='Quantity (shares or contracts)')
    parser.add_argument('--type', dest='type', choices=['market', 'limit', 'stop', 'stop_limit'],
                        help='Order type')
    parser.add_argument('--duration', default='day', choices=['day', 'gtc', 'pre', 'post'],
                        help='Order duration (default: day)')
    parser.add_argument('--price', type=float, help='Limit price (required for limit/stop_limit)')
    parser.add_argument('--preview', action='store_true', help='Validate via Tradier preview, do not submit')
    parser.add_argument('--source-event-id', help='Optional idempotency key (e.g. flow_alerts.id)')

    # --close flags
    parser.add_argument('--position-id', type=int, help='paper_positions.id to close')
    parser.add_argument('--reason', default='manual',
                        help='Close reason (manual/take_profit/stop_loss/max_hold/signal_event)')

    # --cancel flags
    parser.add_argument('--order-id', help='Tradier order id to cancel')

    # --pnl flags
    parser.add_argument('--since', help='Only count closed positions after this YYYY-MM-DD')

    # --positions flag
    parser.add_argument('--include-closed', action='store_true',
                        help='Include closed positions in --positions listing')

    # Phase B close-condition flags (used by --open and --update-conditions)
    parser.add_argument('--tp', type=float, default=None,
                        help='take_profit_pct — close when pnl%% >= N')
    parser.add_argument('--sl', type=float, default=None,
                        help='stop_loss_pct — close when pnl%% <= N (pass negative, e.g. -30)')
    parser.add_argument('--max-hold', type=int, default=None,
                        help='max_hold_days — close after N calendar days')
    parser.add_argument('--expire-before-dte', type=int, default=None,
                        help='close option position when DTE drops <= N')
    parser.add_argument('--target-above', type=float, default=None,
                        help='underlying_target_above — close when underlying >= N')
    parser.add_argument('--target-below', type=float, default=None,
                        help='underlying_target_below — close when underlying <= N')
    parser.add_argument('--clear', action='store_true',
                        help='(--update-conditions only) wipe all conditions to NULL')

    args = parser.parse_args()

    # Canonicalize --tag once so filter queries match the form we persisted
    # (Tradier-sanitized: letters/digits/hyphen). cmd_open re-sanitizes its
    # own raw_tag and prints a notice; this pre-pass only affects filters.
    if args.tag and not args.open:
        canon = sanitize_tag(args.tag)
        if canon != args.tag:
            print("NOTE: filtering by tag '{}' (sanitized from '{}')".format(canon, args.tag))
        args.tag = canon

    config = _load_config()

    # Read-only subcommands don't need the broker for DB queries, but balance does.
    needs_broker = args.balance or args.open or args.close or args.cancel
    broker = TradierPaperBroker(config) if needs_broker else None

    conn = get_connection()
    _ensure_schema(conn)

    try:
        if args.balance:
            return cmd_balance(broker)
        if args.positions or args.status:
            return cmd_positions(conn, tag=args.tag, include_closed=args.include_closed)
        if args.open:
            required = ['instrument', 'symbol', 'side', 'qty', 'type']
            missing = [r for r in required if getattr(args, r) is None]
            if missing:
                print("ERROR: --open requires --{}".format(', --'.join(missing)))
                return 2
            return cmd_open(broker, conn, args)
        if args.close:
            if args.position_id is None:
                print("ERROR: --close requires --position-id")
                return 2
            return cmd_close(broker, conn, args)
        if args.cancel:
            if not args.order_id:
                print("ERROR: --cancel requires --order-id")
                return 2
            return cmd_cancel(broker, args)
        if args.update_conditions:
            if args.position_id is None:
                print("ERROR: --update-conditions requires --position-id")
                return 2
            return cmd_update_conditions(conn, args)
        if args.pnl:
            return cmd_pnl(conn, tag=args.tag, since=args.since)
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
