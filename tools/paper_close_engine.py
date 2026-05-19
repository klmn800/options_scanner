#!/usr/bin/env python3
"""
Paper Close Engine (Phase B)
============================
Standalone reconciliation script. For each open monitored position in
`paper_positions`, fetches fresh Tradier quotes, evaluates the position's
`close_conditions_json`, and submits closing orders for any condition that
trips. Runs as a Task Scheduler job every ~2 minutes during market hours.

Phase B end-state from `docs/paper_trading/DESIGN.md`.

Key design points
-----------------
- **Standalone, not integrated with FM.** Paper writes go to `data/paper.db`
  to eliminate the FM-vs-paper write-lock contention found in State A.
- **NULL conditions = unmonitored.** Positions with `close_conditions_json`
  null are ignored. This is the deliberate default — see PHASE_B_PLAN.md.
- **3-state status machine: open → closing → closed.** Engine flips
  `open → closing` on close submit; `paper_poll.py` completes the
  transition to `closed` when it records the fill.
- **Idempotent.** Won't re-submit a close for a position already in
  `closing` state — that's exactly why the intermediate state exists.
- **Tradier-direct quotes.** Doesn't read `flow_options_scans`. Sandbox
  feed is 15-min delayed but refreshes minute-by-minute.

Usage
-----
    python tools/paper_close_engine.py                  # live, market hours only
    python tools/paper_close_engine.py --dry-run        # evaluate, log, don't submit
    python tools/paper_close_engine.py --ignore-market-hours  # for after-hours testing
    python tools/paper_close_engine.py --position-id N  # one position only (testing)
    python tools/paper_close_engine.py --verbose        # log every position, not just trips

Reads/writes: data/paper.db (paper_* tables) + Tradier sandbox API.
Dependencies: core/tradier_paper.py, core/tradier_api.py, tools/paper_trading.py
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, date


def _parse_opened_at(s):
    """Parse an opened_at string. Returns a tz-aware datetime when possible.

    Two stored shapes seen in the wild:
      - now_eastern().isoformat() → '2026-05-19 13:39:56-04:00' (Eastern, aware)
      - Tradier transaction_date  → '2026-05-19T17:39:05.364Z'  (UTC, aware)
    The caller subtracts from now_eastern() (tz-aware Eastern), so naive
    datetimes get tagged with the local tz of the existing now value.
    """
    if not s:
        return None
    raw = str(s).strip().replace('Z', '+00:00').replace(' ', 'T')
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None

# Project root + import shims
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from core.tradier_paper import TradierPaperBroker
from tools.paper_trading import (
    OPTION_MULTIPLIER,
    _ensure_schema,
    get_connection,
    parse_close_conditions,
)
from tools.timezone_utils import now_eastern

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(project_root, 'config.json')


# ── Instance guard ───────────────────────────────────────────────────

def is_already_running():
    """Return True if another paper_close_engine.py process is running.

    Mirrors `main.py:is_main_already_running()` to use the same idiom
    Ben already trusts.
    """
    import psutil
    current_pid = os.getpid()
    current_script = os.path.abspath(__file__)
    target_name = os.path.basename(current_script)
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['pid'] == current_pid:
                continue
            if proc.info['name'] not in ('python.exe', 'python3.exe', 'python'):
                continue
            cmdline = proc.info.get('cmdline') or []
            for arg in cmdline:
                if target_name in arg:
                    try:
                        if os.path.abspath(arg) == current_script:
                            return True
                    except Exception:
                        if arg.endswith(target_name):
                            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False


# ── Config + broker setup ────────────────────────────────────────────

def _load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


# ── Quote batching ───────────────────────────────────────────────────

def _collect_symbols(positions):
    """Build a deduped list of symbols we need quotes for.

    For stock positions: underlying ticker.
    For option positions: option symbol AND underlying (for underlying-target
    conditions).
    """
    needed = set()
    for p in positions:
        if p['instrument_type'] == 'option':
            if p.get('option_symbol'):
                needed.add(p['option_symbol'])
            if p.get('symbol'):
                needed.add(p['symbol'])
        else:
            if p.get('symbol'):
                needed.add(p['symbol'])
    return sorted(needed)


def _fetch_quotes_batched(broker, symbols):
    """Call /markets/quotes with comma-joined symbols. Returns dict keyed by symbol.

    Tradier returns either {'quotes': {'quote': {...}}} (single) or
    {'quotes': {'quote': [{...}, ...]}} (multiple). Normalize to dict.
    """
    if not symbols:
        return {}
    resp = broker.api.get_quotes(symbols)
    if not resp:
        return {}
    quotes_obj = resp.get('quotes') or {}
    q = quotes_obj.get('quote')
    if q is None:
        return {}
    if isinstance(q, dict):
        q = [q]
    out = {}
    for entry in q:
        sym = entry.get('symbol')
        if sym:
            out[sym] = entry
    return out


def _current_price(quote_entry):
    """Best-effort current price from a Tradier quote dict.

    Prefer `last`, fall back to bid/ask midpoint, then `close`.
    """
    if not quote_entry:
        return None
    last = quote_entry.get('last')
    if last is not None:
        try:
            v = float(last)
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    bid = quote_entry.get('bid')
    ask = quote_entry.get('ask')
    try:
        bid = float(bid) if bid is not None else None
        ask = float(ask) if ask is not None else None
    except (TypeError, ValueError):
        bid = ask = None
    if bid is not None and ask is not None and (bid + ask) > 0:
        return (bid + ask) / 2.0
    close = quote_entry.get('close')
    try:
        if close is not None:
            return float(close)
    except (TypeError, ValueError):
        pass
    return None


# ── Condition evaluation ─────────────────────────────────────────────

def _evaluate_position(position, conditions, quotes, now):
    """Return (trip_reason, detail_str) if a condition trips, else (None, None).

    Condition order = priority (first hit wins). Stop loss is evaluated
    before take profit so a position that's tripping both (shouldn't
    normally happen but possible with extreme intraday swings) gets the
    safer exit reason logged.
    """
    instrument_type = position['instrument_type']
    cost_basis = position['cost_basis_per_unit']

    # Pick the price for P&L calc — option mid for options, stock price for stocks
    if instrument_type == 'option':
        price_quote = quotes.get(position.get('option_symbol'))
    else:
        price_quote = quotes.get(position.get('symbol'))
    current_price = _current_price(price_quote)

    underlying_quote = quotes.get(position.get('symbol'))
    underlying_price = _current_price(underlying_quote)

    # ── stop loss (price-based, needs current_price)
    sl = conditions.get('stop_loss_pct')
    if sl is not None and current_price is not None and cost_basis:
        pnl_pct = (current_price - cost_basis) / cost_basis * 100.0
        if pnl_pct <= sl:
            return 'stop_loss_pct', "pnl%={:.2f} <= {:.2f}".format(pnl_pct, sl)

    # ── take profit (price-based)
    tp = conditions.get('take_profit_pct')
    if tp is not None and current_price is not None and cost_basis:
        pnl_pct = (current_price - cost_basis) / cost_basis * 100.0
        if pnl_pct >= tp:
            return 'take_profit_pct', "pnl%={:.2f} >= {:.2f}".format(pnl_pct, tp)

    # ── underlying target above (price-based, uses underlying)
    ut_above = conditions.get('underlying_target_above')
    if ut_above is not None and underlying_price is not None:
        if underlying_price >= ut_above:
            return 'underlying_target_above', "underlying={:.2f} >= {:.2f}".format(
                underlying_price, ut_above)

    # ── underlying target below
    ut_below = conditions.get('underlying_target_below')
    if ut_below is not None and underlying_price is not None:
        if underlying_price <= ut_below:
            return 'underlying_target_below', "underlying={:.2f} <= {:.2f}".format(
                underlying_price, ut_below)

    # ── max hold days (time-based, no quote needed)
    max_hold = conditions.get('max_hold_days')
    if max_hold is not None and position.get('opened_at'):
        opened = _parse_opened_at(position['opened_at'])
        if opened is not None:
            # Match tz-awareness so subtraction works regardless of stored format
            if opened.tzinfo is None and now.tzinfo is not None:
                opened = opened.replace(tzinfo=now.tzinfo)
            elif opened.tzinfo is not None and now.tzinfo is None:
                opened = opened.replace(tzinfo=None)
            elapsed = (now - opened).days
            if elapsed >= max_hold:
                return 'max_hold_days', "held {} day(s) >= {}".format(elapsed, max_hold)

    # ── expire-before-dte (time-based, option only)
    ebd = conditions.get('expire_before_dte')
    if ebd is not None and instrument_type == 'option' and position.get('expiration_date'):
        try:
            exp = date.fromisoformat(str(position['expiration_date']))
            dte = (exp - now.date()).days
            if dte <= ebd:
                return 'expire_before_dte', "dte={} <= {}".format(dte, ebd)
        except (ValueError, TypeError):
            pass

    return None, None


# ── Close submission ─────────────────────────────────────────────────

def _submit_close(broker, position, reason):
    """Submit a close order via Tradier and return the Tradier response dict.

    Returns None on broker failure.
    """
    if position['instrument_type'] == 'option':
        resp = broker.place_option_order(
            underlying=position['symbol'],
            option_symbol=position['option_symbol'],
            side='sell_to_close',
            qty=int(position['quantity']),
            type_='market',
            duration='day',
            tag=position['tag'],
        )
    else:
        resp = broker.place_equity_order(
            symbol=position['symbol'],
            side='sell',
            qty=int(position['quantity']),
            type_='market',
            duration='day',
            tag=position['tag'],
        )
    return resp


def _mark_closing(conn, position_id, reason, now_iso):
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE paper_positions SET status='closing', close_reason=?, "
        "closing_submitted_at=? WHERE id=?",
        (reason, now_iso, position_id),
    )
    conn.commit()


# ── Main engine cycle ────────────────────────────────────────────────

def run_engine(broker, conn, args):
    """One pass of the close engine. Returns counts dict."""
    cursor = conn.cursor()

    # Market hours check (Tradier authoritative). get_market_clock() returns
    # {"clock": {"state": "open"|"closed"|"premarket"|"postmarket", ...}}.
    market_open = False
    clock_resp = broker.api.get_market_clock()
    if clock_resp:
        clock = clock_resp.get('clock') if isinstance(clock_resp, dict) else None
        market_open = bool(clock and clock.get('state') == 'open')
    if not market_open and not args.ignore_market_hours:
        print("Market closed (per Tradier clock). Skipping price-based eval.")
        print("Pass --ignore-market-hours to override (e.g. for testing).")
        return {'evaluated': 0, 'tripped': 0, 'submitted': 0, 'skipped_closed': True}

    # Pull all open monitored positions
    sql = """
        SELECT id, position_key, tag, instrument_type, symbol, option_symbol,
               option_type, strike, expiration_date, quantity,
               cost_basis_per_unit, opened_at, close_conditions_json, status
        FROM paper_positions
        WHERE status = 'open' AND close_conditions_json IS NOT NULL
    """
    params = []
    if args.position_id is not None:
        sql += " AND id = ?"
        params.append(args.position_id)
    cursor.execute(sql, params)
    rows = [dict(r) for r in cursor.fetchall()]

    if not rows:
        print("No open monitored positions. (Unmonitored positions are ignored by design.)")
        return {'evaluated': 0, 'tripped': 0, 'submitted': 0}

    print("Engine cycle: {} monitored open position(s)".format(len(rows)))
    if args.dry_run:
        print("  --dry-run: closes will be evaluated and logged but NOT submitted.")

    # Batch-fetch all needed quotes in one Tradier call
    symbols_needed = _collect_symbols(rows)
    quotes = _fetch_quotes_batched(broker, symbols_needed)
    if args.verbose:
        print("  quotes fetched for: {} symbol(s)".format(len(quotes)))

    now = now_eastern()
    counts = {'evaluated': 0, 'tripped': 0, 'submitted': 0, 'errors': 0}

    for pos in rows:
        counts['evaluated'] += 1
        conditions = parse_close_conditions(pos.get('close_conditions_json'))
        if conditions is None:
            if args.verbose:
                print("  pos id={} — malformed conditions, skipping".format(pos['id']))
            continue

        reason, detail = _evaluate_position(pos, conditions, quotes, now)
        contract = pos.get('option_symbol') or pos.get('symbol')

        if reason is None:
            if args.verbose:
                print("  pos id={} {} — no trip".format(pos['id'], contract))
            continue

        counts['tripped'] += 1
        print("  TRIP pos id={} tag={} {} qty={} cost={:.4f}".format(
            pos['id'], pos['tag'], contract, pos['quantity'], pos['cost_basis_per_unit'] or 0))
        print("       reason={} ({})".format(reason, detail))

        if args.dry_run:
            continue

        # Submit the close
        try:
            resp = _submit_close(broker, pos, reason)
        except Exception as e:
            logger.exception("Close submit raised for pos id=%s", pos['id'])
            print("       ERROR submitting close: {}".format(e))
            counts['errors'] += 1
            continue

        if not resp:
            print("       ERROR: no response from Tradier (close not submitted)")
            counts['errors'] += 1
            continue

        order = resp.get('order') if isinstance(resp, dict) else None
        if not order:
            print("       ERROR: unexpected Tradier response shape: {}".format(resp))
            counts['errors'] += 1
            continue

        order_id = order.get('id')
        status = order.get('status', '?')
        if str(status).lower() in ('rejected', 'error'):
            print("       Tradier rejected close (status={}). Position left in 'open' state.".format(status))
            counts['errors'] += 1
            continue

        _mark_closing(conn, pos['id'], reason, now.isoformat(sep=' ', timespec='seconds'))
        counts['submitted'] += 1
        print("       SUBMITTED close order_id={} status={} -> position status='closing'".format(
            order_id, status))

    print()
    print("Engine summary: evaluated={evaluated} tripped={tripped} submitted={submitted} errors={errors}".format(
        evaluated=counts.get('evaluated', 0),
        tripped=counts.get('tripped', 0),
        submitted=counts.get('submitted', 0),
        errors=counts.get('errors', 0),
    ))
    if counts.get('submitted', 0) > 0 and not args.dry_run:
        print("Next: run `python tools/paper_poll.py` to record closing fills "
              "(or wait for the next scheduled poll).")
    return counts


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Paper Close Engine — evaluates conditions and fires closes',
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Evaluate + log trips but DO NOT submit close orders')
    parser.add_argument('--ignore-market-hours', action='store_true',
                        help='Run price-based eval even when market is closed (testing)')
    parser.add_argument('--position-id', type=int, default=None,
                        help='Evaluate only one paper_positions.id (testing)')
    parser.add_argument('--verbose', action='store_true',
                        help='Log every position evaluation, not just trips')
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    if is_already_running():
        print("paper_close_engine.py is already running. This instance will exit.")
        return 0

    config = _load_config()
    broker = TradierPaperBroker(config)
    conn = get_connection()
    _ensure_schema(conn)
    try:
        counts = run_engine(broker, conn, args)
        return 0 if counts.get('errors', 0) == 0 else 1
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
