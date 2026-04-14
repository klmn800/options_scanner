#!/usr/bin/env python3
"""
Earnings Scenario Calculator
==============================

Models post-earnings option values accounting for IV crush, helping decide
"sell now vs hold through earnings."

Given a position (contract hash + cost basis), produces a scenario table showing
estimated option value and P/L across a range of post-earnings stock prices,
accounting for IV crush via second-order Greek approximation.

CORE MATH (Second-Order Greek Approximation):
    new_value = current_value + delta*dS + 0.5*gamma*(dS)^2 + vega*dIV + theta*dt

Where:
    dS  = stock price change in dollars (scenario % x current price)
    dIV = -(current_iv x crush_fraction)  [always negative]
    dt  = days until earnings (minimum 1)

USAGE:
    python tools/earnings_scenario.py "TOST|30|2026-02-20|CALL" --cost 1.04
    python tools/earnings_scenario.py "DAY|62.5|2026-02-20|CALL" --cost 2.15 --live
    python tools/earnings_scenario.py "NVDA|150|2026-03-05|PUT" --cost 3.50 --crush 60

Author: Ben (with assistance from Claude)
Date: 2026-02-28
"""

import sqlite3
import argparse
import sys
import os
import math
from datetime import datetime, date


# Default IV crush percentage (median from available data)
DEFAULT_CRUSH_PCT = 46.0

# IV crush sensitivity tiers (EI 5-tier scale midpoints)
CRUSH_TIERS = [
    ('Minimal', 20.0),
    ('Mild', 32.0),
    ('Normal', 46.0),
    ('High', 57.0),
    ('Severe', 70.0),
]

# Database path (anchored to project root, works from any working directory)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(_PROJECT_ROOT, 'data', 'datalake_query.db')


def infer_counterpart(parsed):
    """Infer the opposite-side contract from a parsed contract dict.

    Flips CALL<->PUT, keeping all other fields identical.

    Args:
        parsed: dict from parse_contract_hash() with symbol, strike, expiration, option_type

    Returns:
        New dict with option_type flipped
    """
    flipped = parsed.copy()
    flipped['option_type'] = 'PUT' if parsed['option_type'] == 'CALL' else 'CALL'
    return flipped


def parse_contract_hash(contract_str):
    """Parse a contract hash string into component parts.

    Args:
        contract_str: Pipe-delimited string "SYMBOL|STRIKE|EXPIRY|TYPE"

    Returns:
        dict with keys: symbol, strike, expiration, option_type

    Raises:
        ValueError: If format is invalid
    """
    parts = contract_str.split('|')
    if len(parts) != 4:
        raise ValueError(
            "Contract hash must have 4 pipe-delimited parts: SYMBOL|STRIKE|EXPIRY|TYPE, "
            "got {} parts: '{}'".format(len(parts), contract_str)
        )

    symbol, strike_str, expiry, opt_type = parts

    # Validate symbol
    if not symbol or not symbol.isalpha():
        raise ValueError("Invalid symbol: '{}'".format(symbol))

    # Validate strike
    try:
        strike = float(strike_str)
    except ValueError:
        raise ValueError("Strike must be numeric, got: '{}'".format(strike_str))
    if strike <= 0:
        raise ValueError("Strike must be positive, got: {}".format(strike))

    # Validate expiration format
    try:
        datetime.strptime(expiry, '%Y-%m-%d')
    except ValueError:
        raise ValueError("Expiration must be YYYY-MM-DD, got: '{}'".format(expiry))

    # Validate option type
    opt_type = opt_type.upper()
    if opt_type not in ('CALL', 'PUT'):
        raise ValueError("Option type must be CALL or PUT, got: '{}'".format(opt_type))

    return {
        'symbol': symbol.upper(),
        'strike': strike,
        'expiration': expiry,
        'option_type': opt_type,
    }


def get_contract_from_db(contract, db_path=None):
    """Fetch contract Greeks and pricing from database.

    Reads: option_contracts (most recent trade_date for matching contract)

    Args:
        contract: dict from parse_contract_hash()
        db_path: Path to database (default: data/datalake_query.db)

    Returns:
        dict with Greeks, pricing, and metadata, or None if not found
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("""
            SELECT delta, gamma, vega, theta, iv, bid, ask, last_price,
                   underlying_price, trade_date
            FROM option_contracts
            WHERE symbol = ?
              AND strike = ?
              AND expiration_date = ?
              AND option_type = ?
            ORDER BY trade_date DESC
            LIMIT 1
        """, (contract['symbol'], contract['strike'],
              contract['expiration'], contract['option_type'])).fetchone()

        if row is None:
            return None

        return {
            'delta': row['delta'] or 0.0,
            'gamma': row['gamma'] or 0.0,
            'vega': row['vega'] or 0.0,
            'theta': row['theta'] or 0.0,
            'iv': row['iv'] or 0.0,
            'bid': row['bid'] or 0.0,
            'ask': row['ask'] or 0.0,
            'last_price': row['last_price'] or 0.0,
            'underlying_price': row['underlying_price'] or 0.0,
            'trade_date': row['trade_date'],
        }
    finally:
        conn.close()


def get_earnings_data(symbol, db_path=None):
    """Fetch earnings data for a symbol from database.

    Reads: earnings_upcoming (expected/historical moves, earnings date/time)

    Args:
        symbol: Stock symbol
        db_path: Path to database (default: data/datalake_query.db)

    Returns:
        dict with earnings_date, earnings_time, expected/historical moves,
        or None if no upcoming earnings
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("""
            SELECT earnings_date, earnings_time,
                   straddle_expected_move_pct, historical_avg_move_pct,
                   relative_underpricing_pct
            FROM earnings_upcoming
            WHERE symbol = ?
        """, (symbol,)).fetchone()

        if row is None:
            return None

        return {
            'earnings_date': row['earnings_date'],
            'earnings_time': row['earnings_time'],
            'straddle_expected_move_pct': row['straddle_expected_move_pct'],
            'historical_avg_move_pct': row['historical_avg_move_pct'],
            'relative_underpricing_pct': row['relative_underpricing_pct'],
        }
    finally:
        conn.close()


def get_contract_live(symbol, strike, expiration, option_type):
    """Fetch live contract Greeks from Tradier API.

    Args:
        symbol: Stock symbol
        strike: Strike price
        expiration: Expiration date (YYYY-MM-DD)
        option_type: CALL or PUT

    Returns:
        dict with Greeks, pricing, and metadata, or None if not found
    """
    import json
    from core.tradier_api import TradierDataClient

    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)

    cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
    client = TradierDataClient(config, cache_dir)

    result = client.get_contract_greeks(symbol, strike, expiration, option_type)
    if result is None:
        return None

    # Add trade_date as current timestamp for live data
    result['trade_date'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    return result


def _make_leg(contract_data, option_type, cost_basis):
    """Build a leg dict from contract data.

    Args:
        contract_data: dict with Greeks, pricing, trade_date
        option_type: CALL or PUT
        cost_basis: Cost basis per contract

    Returns:
        dict with all leg fields including direction=+1
    """
    bid = contract_data.get('bid', 0.0)
    ask = contract_data.get('ask', 0.0)
    if bid > 0 and ask > 0:
        current_value = (bid + ask) / 2.0
    else:
        current_value = contract_data.get('last_price', 0.0)

    return {
        'option_type': option_type,
        'delta': contract_data.get('delta', 0.0),
        'gamma': contract_data.get('gamma', 0.0),
        'vega': contract_data.get('vega', 0.0),
        'theta': contract_data.get('theta', 0.0),
        'iv': contract_data.get('iv', 0.0),
        'bid': bid,
        'ask': ask,
        'last_price': contract_data.get('last_price', 0.0),
        'underlying_price': contract_data.get('underlying_price', 0.0),
        'trade_date': contract_data.get('trade_date'),
        'cost_basis': cost_basis,
        'current_value': current_value,
        'direction': +1,
    }


def _fetch_contract(parsed, live):
    """Fetch contract data from DB or live, with fallback prompt.

    Args:
        parsed: dict from parse_contract_hash()
        live: If True, fetch from Tradier API

    Returns:
        (contract_data, live_flag) tuple

    Raises:
        ValueError: If contract not found
    """
    contract_str = "{}|{}|{}|{}".format(
        parsed['symbol'], parsed['strike'], parsed['expiration'], parsed['option_type'])

    if live:
        contract_data = get_contract_live(
            parsed['symbol'], parsed['strike'], parsed['expiration'], parsed['option_type'])
        if contract_data is None:
            raise ValueError("Contract not found via Tradier API: {}".format(contract_str))
        return contract_data, True

    contract_data = get_contract_from_db(parsed)
    if contract_data is None:
        try:
            answer = input("{} not found in database. Fetch live from Tradier? (y/n): ".format(contract_str))
        except EOFError:
            answer = 'n'
        if answer.strip().lower() in ('y', 'yes'):
            contract_data = get_contract_live(
                parsed['symbol'], parsed['strike'], parsed['expiration'], parsed['option_type'])
            if contract_data is None:
                raise ValueError("Contract not found via Tradier API either: {}".format(contract_str))
            return contract_data, True
        else:
            raise ValueError("Contract not found in database: {}".format(contract_str))

    return contract_data, live


def build_legs(parsed, cost_basis, live=False, straddle=False,
               put_cost=None, call_cost=None):
    """Encapsulate all data retrieval and build leg list.

    For single mode: fetches one contract, returns [leg].
    For straddle: fetches both contracts, returns [call_leg, put_leg].

    Args:
        parsed: dict from parse_contract_hash()
        cost_basis: Cost of the primary leg
        live: Fetch from Tradier API
        straddle: Build a straddle position
        put_cost: Cost of put leg (when primary is CALL)
        call_cost: Cost of call leg (when primary is PUT)

    Returns:
        (legs_list, position_type, warnings_list, live_flag)
    """
    warnings = []
    primary_data, live = _fetch_contract(parsed, live)

    # Stale data warning
    if not live and primary_data.get('trade_date'):
        try:
            trade_dt = datetime.strptime(primary_data['trade_date'], '%Y-%m-%d').date()
            days_stale = (date.today() - trade_dt).days
            if days_stale > 1:
                warnings.append("Data is {} days old (from {}). Consider using --live for current Greeks.".format(
                    days_stale, primary_data['trade_date']))
        except ValueError:
            pass

    # Zero Greeks warning
    if primary_data.get('delta', 0.0) == 0.0 and primary_data.get('gamma', 0.0) == 0.0:
        warnings.append("Greeks are zero -- estimates may be unreliable.")

    if not straddle:
        leg = _make_leg(primary_data, parsed['option_type'], cost_basis)
        return [leg], 'single', warnings, live

    # --- Straddle mode ---
    counter_parsed = infer_counterpart(parsed)
    counter_data, live = _fetch_contract(counter_parsed, live)

    # Determine call/put costs
    if parsed['option_type'] == 'CALL':
        call_leg_cost = cost_basis
        put_leg_cost = put_cost
    else:
        put_leg_cost = cost_basis
        call_leg_cost = call_cost

    # Build legs — always [call, put] order
    if parsed['option_type'] == 'CALL':
        call_leg = _make_leg(primary_data, 'CALL', call_leg_cost)
        put_leg = _make_leg(counter_data, 'PUT', put_leg_cost)
    else:
        call_leg = _make_leg(counter_data, 'CALL', call_leg_cost)
        put_leg = _make_leg(primary_data, 'PUT', put_leg_cost)

    # Zero Greeks warning for counter leg
    counter_delta = counter_data.get('delta', 0.0)
    counter_gamma = counter_data.get('gamma', 0.0)
    if counter_delta == 0.0 and counter_gamma == 0.0:
        warnings.append("{} leg Greeks are zero -- estimates may be unreliable.".format(
            counter_parsed['option_type']))

    return [call_leg, put_leg], 'straddle', warnings, live


def estimate_position_value(legs, stock_price, move_pct, crush_pct,
                            days_to_earnings):
    """Compute per-leg estimated values and combined sum.

    Args:
        legs: list of leg dicts
        stock_price: Current underlying price
        move_pct: Stock move percentage
        crush_pct: IV crush percentage
        days_to_earnings: Days until earnings

    Returns:
        (combined_value, per_leg_list) where per_leg_list is
        [{'option_type': 'CALL', 'est_value': X}, ...]
    """
    per_leg = []
    combined = 0.0
    for leg in legs:
        est = estimate_option_value(
            leg['current_value'], leg['delta'], leg['gamma'],
            leg['vega'], leg['theta'], leg['iv'],
            stock_price, move_pct, crush_pct, days_to_earnings
        )
        per_leg.append({
            'option_type': leg['option_type'],
            'est_value': est,
        })
        combined += est
    return combined, per_leg


def calculate_combined_breakeven(legs, crush_pct, days_to_earnings, stock_price):
    """Calculate breakeven stock move(s) for a multi-leg position.

    Sums per-leg quadratic coefficients and solves the combined quadratic.
    For straddles, both roots are meaningful.

    Args:
        legs: list of leg dicts
        crush_pct: IV crush percentage
        days_to_earnings: Days until earnings
        stock_price: Current underlying price

    Returns:
        Sorted list of valid breakeven move percentages within +/-30%.
        Empty list if no solutions.
    """
    dt = max(1, days_to_earnings)
    sum_a = 0.0
    sum_b = 0.0
    sum_c = 0.0

    for leg in legs:
        iv = leg['iv']
        dIV_pp = -(iv * crush_pct)
        sum_a += 0.5 * leg['gamma']
        sum_b += leg['delta']
        sum_c += leg['vega'] * dIV_pp + leg['theta'] * dt

    # Solve: sum_a * (dS)^2 + sum_b * (dS) + sum_c = 0
    roots = []
    if abs(sum_a) < 1e-12:
        # Linear case
        if abs(sum_b) > 1e-12:
            dS = -sum_c / sum_b
            if stock_price > 0:
                pct = (dS / stock_price) * 100.0
                if abs(pct) <= 30.0:
                    roots.append(pct)
    else:
        discriminant = sum_b * sum_b - 4 * sum_a * sum_c
        if discriminant >= 0:
            sqrt_disc = math.sqrt(discriminant)
            for sign in (+1, -1):
                dS = (-sum_b + sign * sqrt_disc) / (2 * sum_a)
                if stock_price > 0:
                    pct = (dS / stock_price) * 100.0
                    if abs(pct) <= 30.0:
                        roots.append(pct)

    return sorted(roots)


def estimate_option_value(current_value, delta, gamma, vega, theta,
                          iv, stock_price, move_pct, crush_pct,
                          days_to_earnings):
    """Estimate post-earnings option value using second-order Greek approximation.

    Formula: new_value = current_value + delta*dS + 0.5*gamma*(dS)^2 + vega*dIV + theta*dt

    Args:
        current_value: Current option mid-price
        delta, gamma, vega, theta: Option Greeks
        iv: Current implied volatility (decimal, e.g. 0.942)
        stock_price: Current underlying price
        move_pct: Stock price move percentage (e.g. 5.0 for +5%)
        crush_pct: IV crush percentage (e.g. 46.0 for 46% crush)
        days_to_earnings: Days until earnings event (minimum 1)

    Returns:
        float: Estimated option value (floored at 0.00)
    """
    dS = stock_price * move_pct / 100.0
    # dIV in percentage points (Tradier vega is per 1pp = per 0.01 change in sigma)
    dIV_pp = -(iv * crush_pct)  # iv is decimal (0.516), crush_pct is % (46) → pp
    dt = max(1, days_to_earnings)

    new_value = (current_value
                 + delta * dS
                 + 0.5 * gamma * dS * dS
                 + vega * dIV_pp
                 + theta * dt)

    return max(0.0, new_value)


def calculate_breakeven(delta, gamma, vega, theta, iv, crush_pct,
                        days_to_earnings, stock_price, option_type):
    """Calculate the breakeven stock move where hold-through equals sell-now.

    Solves: 0.5*gamma*(dS)^2 + delta*(dS) + (vega*dIV + theta*dt) = 0
    Standard quadratic: a*(dS)^2 + b*(dS) + c = 0

    Args:
        delta, gamma, vega, theta: Option Greeks
        iv: Current implied volatility (decimal)
        crush_pct: IV crush percentage
        days_to_earnings: Days until earnings
        stock_price: Current underlying price
        option_type: CALL or PUT

    Returns:
        float: Breakeven move percentage, or None if not achievable within +/-30%
    """
    # dIV in percentage points (Tradier vega is per 1pp = per 0.01 change in sigma)
    dIV_pp = -(iv * crush_pct)  # iv is decimal, crush_pct is % → result in pp
    dt = max(1, days_to_earnings)

    a = 0.5 * gamma
    b = delta
    c = vega * dIV_pp + theta * dt

    # If gamma is essentially zero, degenerate to linear
    if abs(a) < 1e-12:
        if abs(b) < 1e-12:
            return None  # No solution
        dS = -c / b
    else:
        discriminant = b * b - 4 * a * c
        if discriminant < 0:
            return None  # No real solution

        sqrt_disc = math.sqrt(discriminant)
        root1 = (-b + sqrt_disc) / (2 * a)
        root2 = (-b - sqrt_disc) / (2 * a)

        # For calls: take the positive root (stock needs to go up)
        # For puts: take the negative root (stock needs to go down)
        if option_type == 'CALL':
            # Pick the smallest positive root
            candidates = [r for r in (root1, root2) if r > 0]
            dS = min(candidates) if candidates else None
        else:
            # Pick the largest negative root (closest to zero)
            candidates = [r for r in (root1, root2) if r < 0]
            dS = max(candidates) if candidates else None

        if dS is None:
            return None

    # Convert dollar move to percentage
    if stock_price <= 0:
        return None
    move_pct = (dS / stock_price) * 100.0

    # Cap at +/-30%
    if abs(move_pct) > 30.0:
        return None

    return move_pct


def build_scenario_rows(legs, position_type, earnings_data, cost_basis, crush_pct,
                        current_value, days_to_earnings, breakeven_pcts):
    """Build the list of scenario rows for the table.

    Args:
        legs: list of leg dicts
        position_type: 'single' or 'straddle'
        earnings_data: dict with expected/historical moves, or None
        cost_basis: Combined cost per contract
        crush_pct: IV crush percentage
        current_value: Combined current option mid-price
        days_to_earnings: Days until earnings
        breakeven_pcts: list of breakeven move percentages

    Returns:
        list of dicts, each with: label, move_pct, stock_price, est_value,
        pnl, pnl_pct, vs_sell_now, is_breakeven, and per_leg (for straddle)
    """
    stock_price = legs[0]['underlying_price']

    # For single-leg backward compat, extract Greeks from the single leg
    if position_type == 'single':
        leg = legs[0]
        delta = leg['delta']
        gamma = leg['gamma']
        vega = leg['vega']
        theta = leg['theta']
        iv = leg['iv']

    # Build list of (move_pct, label) tuples
    scenarios = []

    if earnings_data:
        exp_move = earnings_data.get('straddle_expected_move_pct')
        hist_move = earnings_data.get('historical_avg_move_pct')

        # Check if expected and historical are within 1% of each other
        consolidate = (exp_move is not None and hist_move is not None
                       and abs(exp_move - hist_move) < 1.0)

        if consolidate:
            # Use average of the two, labeled as both
            avg = (exp_move + hist_move) / 2.0
            scenarios.append((-avg, "Down {:.1f}% (exp/hist)".format(avg)))
        else:
            if hist_move is not None:
                scenarios.append((-hist_move, "Down {:.1f}% (hist)".format(hist_move)))
            if exp_move is not None:
                scenarios.append((-exp_move, "Down {:.1f}% (exp)".format(exp_move)))

        scenarios.append((-5.0, "Down 5%"))
        scenarios.append((0.0, "Flat"))
        scenarios.append((5.0, "Up 5%"))

        # Insert breakeven(s) if available
        for bp in breakeven_pcts:
            be_dir = "Up" if bp >= 0 else "Down"
            scenarios.append((bp, "{} {:.1f}%".format(be_dir, abs(bp))))

        if consolidate:
            avg = (exp_move + hist_move) / 2.0
            scenarios.append((avg, "Up {:.1f}% (exp/hist)".format(avg)))
        else:
            if exp_move is not None:
                scenarios.append((exp_move, "Up {:.1f}% (exp)".format(exp_move)))
            if hist_move is not None:
                scenarios.append((hist_move, "Up {:.1f}% (hist)".format(hist_move)))
    else:
        # No earnings data -- use fixed intervals
        for pct in [-10.0, -5.0, -3.0]:
            scenarios.append((pct, "Down {:.0f}%".format(abs(pct))))
        scenarios.append((0.0, "Flat"))
        for pct in [3.0, 5.0]:
            scenarios.append((pct, "Up {:.0f}%".format(pct)))
        for bp in breakeven_pcts:
            be_dir = "Up" if bp >= 0 else "Down"
            scenarios.append((bp, "{} {:.1f}%".format(be_dir, abs(bp))))
        scenarios.append((10.0, "Up 10%"))

    # Sort by move_pct
    scenarios.sort(key=lambda x: x[0])

    # Deduplicate scenarios that are very close (within 0.3%)
    # This prevents breakeven from overlapping with a named scenario
    deduped = []
    for move_pct, label in scenarios:
        is_dup = False
        for existing_pct, existing_label in deduped:
            if abs(move_pct - existing_pct) < 0.3:
                is_dup = True
                break
        if not is_dup:
            deduped.append((move_pct, label))
    scenarios = deduped

    # Build scenario rows
    rows = []
    for move_pct, label in scenarios:
        if position_type == 'single':
            est_value = estimate_option_value(
                current_value, delta, gamma, vega, theta,
                iv, stock_price, move_pct, crush_pct, days_to_earnings
            )
            per_leg = None
        else:
            est_value, per_leg = estimate_position_value(
                legs, stock_price, move_pct, crush_pct, days_to_earnings
            )

        pnl = est_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0
        vs_sell_now = est_value - current_value

        is_breakeven = any(abs(move_pct - bp) < 0.3 for bp in breakeven_pcts)

        row = {
            'label': label,
            'move_pct': move_pct,
            'stock_price': stock_price * (1 + move_pct / 100.0),
            'est_value': est_value,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'vs_sell_now': vs_sell_now,
            'is_breakeven': is_breakeven,
        }
        if per_leg is not None:
            row['per_leg'] = per_leg

        rows.append(row)

    return rows


def build_crush_matrix(legs, position_type, earnings_data, cost_basis,
                       current_value, days_to_earnings):
    """Build IV crush sensitivity matrix across 5 EI tiers.

    Args:
        legs: list of leg dicts
        position_type: 'single' or 'straddle'
        earnings_data: dict with expected/historical moves, or None
        cost_basis: Combined cost per contract
        current_value: Combined current option mid-price
        days_to_earnings: Days until earnings

    Returns:
        (matrix, exp_move_label) where matrix is list of dicts, one per tier,
        with: tier_name, crush_pct, breakeven_pct(s), flat_pnl, expected_move_pnl
    """
    stock_price = legs[0]['underlying_price']

    if position_type == 'single':
        leg = legs[0]
        delta = leg['delta']
        gamma = leg['gamma']
        vega = leg['vega']
        theta = leg['theta']
        iv = leg['iv']
        option_type = leg['option_type']

    # Determine the expected move for P/L column
    exp_move_pct = None
    exp_move_label = None
    if earnings_data:
        exp = earnings_data.get('straddle_expected_move_pct')
        hist = earnings_data.get('historical_avg_move_pct')
        # Prefer expected, fall back to historical
        exp_move_pct = exp if exp is not None else hist
        if exp_move_pct is not None:
            if position_type == 'single':
                # For calls use up move, for puts use down move
                if option_type == 'PUT':
                    exp_move_pct = -exp_move_pct
                direction = "Down" if exp_move_pct < 0 else "Up"
                exp_move_label = "{} {:.1f}%".format(direction, abs(exp_move_pct))
            else:
                # Straddle profits from movement in either direction — use abs
                exp_move_label = "{:.1f}%".format(abs(exp_move_pct))

    matrix = []
    for tier_name, tier_crush in CRUSH_TIERS:
        if position_type == 'single':
            # Single-leg breakeven
            be = calculate_breakeven(
                delta, gamma, vega, theta, iv, tier_crush,
                days_to_earnings, stock_price, option_type
            )
            breakeven_pcts = [be] if be is not None else []

            # Flat P/L (0% move)
            flat_value = estimate_option_value(
                current_value, delta, gamma, vega, theta,
                iv, stock_price, 0.0, tier_crush, days_to_earnings
            )
            flat_pnl = flat_value - cost_basis

            # Expected move P/L
            exp_pnl = None
            if exp_move_pct is not None:
                exp_value = estimate_option_value(
                    current_value, delta, gamma, vega, theta,
                    iv, stock_price, exp_move_pct, tier_crush, days_to_earnings
                )
                exp_pnl = exp_value - cost_basis
        else:
            # Straddle — combined breakeven
            breakeven_pcts = calculate_combined_breakeven(
                legs, tier_crush, days_to_earnings, stock_price
            )

            # Flat P/L
            flat_combined, _ = estimate_position_value(
                legs, stock_price, 0.0, tier_crush, days_to_earnings
            )
            flat_pnl = flat_combined - cost_basis

            # Expected move P/L — straddle profits from abs(move)
            exp_pnl = None
            if exp_move_pct is not None:
                exp_combined, _ = estimate_position_value(
                    legs, stock_price, abs(exp_move_pct), tier_crush, days_to_earnings
                )
                exp_pnl = exp_combined - cost_basis

        # Backward compat: single-leg uses breakeven_pct (singular)
        tier_dict = {
            'tier_name': tier_name,
            'crush_pct': tier_crush,
            'flat_pnl': flat_pnl,
            'expected_move_pnl': exp_pnl,
        }
        if position_type == 'single':
            tier_dict['breakeven_pct'] = breakeven_pcts[0] if breakeven_pcts else None
        else:
            tier_dict['breakeven_pcts'] = breakeven_pcts

        matrix.append(tier_dict)

    return matrix, exp_move_label


def calculate_scenarios(contract, cost_basis, quantity=1, crush_pct=None,
                        live=False, straddle=False, put_cost=None,
                        call_cost=None):
    """Top-level calculation orchestrator.

    Args:
        contract: Contract hash string "SYMBOL|STRIKE|EXPIRY|TYPE"
        cost_basis: Cost basis per contract in dollars
        quantity: Number of contracts (default 1)
        crush_pct: IV crush override (None = use default 46%)
        live: If True, fetch live Greeks from Tradier
        straddle: If True, build a straddle position
        put_cost: Cost of put leg (when primary is CALL + straddle)
        call_cost: Cost of call leg (when primary is PUT + straddle)

    Returns:
        dict with scenarios, breakeven, crush_matrix, warnings, etc.
        Straddle adds: position_type, legs keys.
    """
    parsed = parse_contract_hash(contract)
    symbol = parsed['symbol']
    strike = parsed['strike']
    expiration = parsed['expiration']
    option_type = parsed['option_type']

    # --- Data retrieval via build_legs ---
    legs, position_type, warnings, live = build_legs(
        parsed, cost_basis, live=live, straddle=straddle,
        put_cost=put_cost, call_cost=call_cost
    )

    # Earnings data (always from DB, even in live mode)
    earnings_data = get_earnings_data(symbol)
    if earnings_data is None:
        warnings.append("No earnings data found for {}. Using fixed price intervals.".format(symbol))

    # --- Compute values ---
    effective_crush = crush_pct if crush_pct is not None else DEFAULT_CRUSH_PCT

    # Combined cost_basis and current_value across legs
    combined_cost = sum(leg['cost_basis'] for leg in legs)
    combined_current = sum(leg['current_value'] for leg in legs)
    stock_price = legs[0]['underlying_price']

    # Days to earnings
    if earnings_data and earnings_data.get('earnings_date'):
        try:
            earnings_dt = datetime.strptime(earnings_data['earnings_date'], '%Y-%m-%d').date()
            days_to_earnings = max(1, (earnings_dt - date.today()).days)
        except ValueError:
            days_to_earnings = 1
    else:
        days_to_earnings = 1

    # For single-leg, use primary leg Greeks (backward compatible)
    # For straddle, use combined Greeks for reference
    primary_leg = legs[0]
    if position_type == 'single':
        iv = primary_leg['iv']
        delta = primary_leg['delta']
        gamma = primary_leg['gamma']
        vega = primary_leg['vega']
        theta = primary_leg['theta']
    else:
        # Combined Greeks for straddle
        iv = primary_leg['iv']  # Use call leg IV for header display
        delta = sum(leg['delta'] for leg in legs)
        gamma = sum(leg['gamma'] for leg in legs)
        vega = sum(leg['vega'] for leg in legs)
        theta = sum(leg['theta'] for leg in legs)

    # Breakeven calculation
    if position_type == 'single':
        breakeven_pct = calculate_breakeven(
            delta, gamma, vega, theta, iv, effective_crush,
            days_to_earnings, stock_price, option_type
        )
        breakeven_pcts = [breakeven_pct] if breakeven_pct is not None else []
    else:
        breakeven_pcts = calculate_combined_breakeven(
            legs, effective_crush, days_to_earnings, stock_price
        )
        breakeven_pct = breakeven_pcts if breakeven_pcts else None

    # Scenario rows
    scenario_rows = build_scenario_rows(
        legs, position_type, earnings_data, combined_cost, effective_crush,
        combined_current, days_to_earnings, breakeven_pcts
    )

    # Check for >15% move scenarios
    has_extreme = any(abs(r['move_pct']) > 15.0 for r in scenario_rows)
    if has_extreme:
        warnings.append("Estimates for moves >15% may be less accurate (Greek approximation limits).")

    # Crush sensitivity matrix
    crush_matrix, exp_move_label = build_crush_matrix(
        legs, position_type, earnings_data, combined_cost, combined_current,
        days_to_earnings
    )

    # Post-earnings IV estimate (use call leg IV for display)
    post_earnings_iv = iv * (1 - effective_crush / 100.0)

    # Breakeven price(s)
    if position_type == 'single':
        be_pct_for_result = breakeven_pcts[0] if breakeven_pcts else None
        breakeven_price = stock_price * (1 + be_pct_for_result / 100.0) if be_pct_for_result is not None else None
    else:
        be_pct_for_result = breakeven_pcts if breakeven_pcts else None
        breakeven_price = [stock_price * (1 + bp / 100.0) for bp in breakeven_pcts] if breakeven_pcts else None

    result = {
        'symbol': symbol,
        'strike': strike,
        'expiration': expiration,
        'option_type': option_type,
        'position_type': position_type,
        'legs': legs,
        'cost_basis': combined_cost,
        'quantity': quantity,
        'current_value': combined_current,
        'stock_price': stock_price,
        'iv': iv,
        'post_earnings_iv': post_earnings_iv,
        'crush_pct': effective_crush,
        'days_to_earnings': days_to_earnings,
        'trade_date': legs[0].get('trade_date'),
        'earnings_date': earnings_data.get('earnings_date') if earnings_data else None,
        'earnings_time': earnings_data.get('earnings_time') if earnings_data else None,
        'relative_underpricing_pct': earnings_data.get('relative_underpricing_pct') if earnings_data else None,
        'breakeven_move_pct': be_pct_for_result,
        'breakeven_price': breakeven_price,
        'scenarios': scenario_rows,
        'crush_matrix': crush_matrix,
        'crush_matrix_exp_label': exp_move_label,
        'warnings': warnings,
        'live': live,
        'delta': delta,
        'gamma': gamma,
        'vega': vega,
        'theta': theta,
    }

    return result


def _format_dollar(value):
    """Format a dollar value with sign."""
    if value >= 0:
        return "+${:.2f}".format(value)
    else:
        return "-${:.2f}".format(abs(value))


def _format_pct(value):
    """Format a percentage with sign."""
    if value >= 0:
        return "+{:.0f}%".format(value)
    else:
        return "{:.0f}%".format(value)


def format_header(result):
    """Format the multi-line header block.

    Branches on position_type for straddle vs single-leg display.

    Returns:
        str: Header lines including contract description, cost/value/IV,
        data timestamp, post-earnings IV estimate, breakeven summary.
    """
    lines = []
    symbol = result['symbol']
    strike = result['strike']
    exp_parts = result['expiration'].split('-')
    exp_short = "{}/{}".format(int(exp_parts[1]), int(exp_parts[2]))
    strike_str = "{:.0f}".format(strike) if strike == int(strike) else "{:g}".format(strike)
    position_type = result.get('position_type', 'single')

    if position_type == 'straddle':
        legs = result['legs']
        call_leg = next(l for l in legs if l['option_type'] == 'CALL')
        put_leg = next(l for l in legs if l['option_type'] == 'PUT')

        # Line 1: Straddle description with per-leg costs
        lines.append("{} {} Straddle {} | Call: ${:.2f} | Put: ${:.2f} | Combined: ${:.2f}".format(
            symbol, strike_str, exp_short,
            call_leg['cost_basis'], put_leg['cost_basis'], result['cost_basis']))

        # Line 2: Current values per-leg
        lines.append("Current: ${:.2f} (${:.2f} call + ${:.2f} put) | Stock: ${:.2f} | IV: {:.1f}%".format(
            result['current_value'], call_leg['current_value'], put_leg['current_value'],
            result['stock_price'], result['iv'] * 100))
    else:
        # Single-leg header (unchanged)
        opt_type = result['option_type'][0]  # C or P
        contract_desc = "{} {}{} {}".format(symbol, strike_str, opt_type, exp_short)
        lines.append("{} | Cost: ${:.2f} | Current: ${:.2f} | Stock: ${:.2f} | IV: {:.1f}%".format(
            contract_desc, result['cost_basis'], result['current_value'],
            result['stock_price'], result['iv'] * 100))

    # Data timestamp + earnings date
    data_parts = []
    if result.get('trade_date'):
        source = "Live" if result.get('live') else "Option Pipeline"
        data_parts.append("Data: {} ({})".format(result['trade_date'], source))
    if result.get('earnings_date'):
        earnings_str = "Earnings: {}".format(result['earnings_date'])
        if result.get('earnings_time') and result['earnings_time'] != 'Unknown':
            earnings_str += " {}".format(result['earnings_time'])
        data_parts.append(earnings_str)
    if data_parts:
        lines.append(" | ".join(data_parts))

    # Estimated post-earnings IV + underpricing context
    iv_line = "Estimated post-earnings IV: ~{:.0f}% ({:.0f}% crush)".format(
        result['post_earnings_iv'] * 100, result['crush_pct'])
    underpricing = result.get('relative_underpricing_pct')
    if underpricing is not None:
        iv_line += " | Underpricing: {:.1f}%".format(underpricing)
    lines.append(iv_line)

    # Breakeven summary
    be_pct = result.get('breakeven_move_pct')
    be_price = result.get('breakeven_price')
    if isinstance(be_pct, list) and isinstance(be_price, list):
        # Straddle: dual breakevens
        if len(be_pct) >= 2:
            lines.append("Breakeven vs sell now: stock needs to move {:.1f}% (${:.2f}) or +{:.1f}% (${:.2f})".format(
                be_pct[0], be_price[0], be_pct[1], be_price[1]))
        elif len(be_pct) == 1:
            sign = "+" if be_pct[0] >= 0 else ""
            lines.append("Breakeven vs sell now: stock needs to move {}{:.1f}% (${:.2f})".format(
                sign, be_pct[0], be_price[0]))
        else:
            lines.append("Breakeven vs sell now: not achievable within +/-30% move")
    elif be_pct is not None and be_price is not None:
        sign = "+" if be_pct >= 0 else ""
        lines.append("Breakeven vs sell now: stock needs to move {}{:.1f}% (${:.2f})".format(
            sign, be_pct, be_price))
    else:
        lines.append("Breakeven vs sell now: not achievable within +/-30% move")

    return "\n".join(lines)


def format_scenario_rows(result):
    """Format the scenario table with aligned columns.

    For straddle, adds Call Est and Put Est columns before Combined.

    Returns:
        str: Formatted scenario table with headers, data rows, and SELL NOW footer.
    """
    scenarios = result['scenarios']
    quantity = result.get('quantity', 1)
    show_total = quantity > 1
    position_type = result.get('position_type', 'single')
    is_straddle = position_type == 'straddle'

    # Column headers
    if is_straddle:
        if show_total:
            header = "{:<20s}| {:>8s} | {:>9s} | {:>9s} | {:>9s} | {:>8s} | {:>6s} | {:>10s} | {:>10s}".format(
                "Scenario", "Stock", "Call Est", "Put Est", "Combined", "P/L", "P/L %", "vs Sell Now", "Total P/L")
        else:
            header = "{:<20s}| {:>8s} | {:>9s} | {:>9s} | {:>9s} | {:>8s} | {:>6s} | {:>10s}".format(
                "Scenario", "Stock", "Call Est", "Put Est", "Combined", "P/L", "P/L %", "vs Sell Now")
    else:
        if show_total:
            header = "{:<20s}| {:>8s} | {:>9s} | {:>8s} | {:>6s} | {:>10s} | {:>10s}".format(
                "Scenario", "Stock", "Est Value", "P/L", "P/L %", "vs Sell Now", "Total P/L")
        else:
            header = "{:<20s}| {:>8s} | {:>9s} | {:>8s} | {:>6s} | {:>10s}".format(
                "Scenario", "Stock", "Est Value", "P/L", "P/L %", "vs Sell Now")

    sep_len = len(header)
    sep = "-" * sep_len

    lines = [header, sep]

    for row in scenarios:
        pnl_str = _format_dollar(row['pnl'])
        pnl_pct_str = _format_pct(row['pnl_pct'])
        vs_sell_str = _format_dollar(row['vs_sell_now'])
        marker = "  <-- BREAKEVEN" if row.get('is_breakeven') else ""

        if is_straddle:
            per_leg = row.get('per_leg', [])
            call_est = next((pl['est_value'] for pl in per_leg if pl['option_type'] == 'CALL'), 0.0)
            put_est = next((pl['est_value'] for pl in per_leg if pl['option_type'] == 'PUT'), 0.0)
            if show_total:
                total_pnl = row['pnl'] * quantity * 100
                total_str = _format_dollar(total_pnl)
                lines.append("{:<20s}| ${:>7.2f} | ${:>8.2f} | ${:>8.2f} | ${:>8.2f} | {:>8s} | {:>6s} | {:>10s} | {:>10s}{}".format(
                    row['label'], row['stock_price'], call_est, put_est, row['est_value'],
                    pnl_str, pnl_pct_str, vs_sell_str, total_str, marker))
            else:
                lines.append("{:<20s}| ${:>7.2f} | ${:>8.2f} | ${:>8.2f} | ${:>8.2f} | {:>8s} | {:>6s} | {:>10s}{}".format(
                    row['label'], row['stock_price'], call_est, put_est, row['est_value'],
                    pnl_str, pnl_pct_str, vs_sell_str, marker))
        else:
            if show_total:
                total_pnl = row['pnl'] * quantity * 100
                total_str = _format_dollar(total_pnl)
                lines.append("{:<20s}| ${:>7.2f} | ${:>8.2f} | {:>8s} | {:>6s} | {:>10s} | {:>10s}{}".format(
                    row['label'], row['stock_price'], row['est_value'],
                    pnl_str, pnl_pct_str, vs_sell_str, total_str, marker))
            else:
                lines.append("{:<20s}| ${:>7.2f} | ${:>8.2f} | {:>8s} | {:>6s} | {:>10s}{}".format(
                    row['label'], row['stock_price'], row['est_value'],
                    pnl_str, pnl_pct_str, vs_sell_str, marker))

    # SELL NOW footer row
    lines.append(sep)
    sell_pnl = result['current_value'] - result['cost_basis']
    sell_pnl_pct = (sell_pnl / result['cost_basis'] * 100) if result['cost_basis'] > 0 else 0

    if is_straddle:
        legs = result['legs']
        call_cv = next((l['current_value'] for l in legs if l['option_type'] == 'CALL'), 0.0)
        put_cv = next((l['current_value'] for l in legs if l['option_type'] == 'PUT'), 0.0)
        if show_total:
            total_sell = sell_pnl * quantity * 100
            lines.append("{:<20s}| {:>8s} | ${:>8.2f} | ${:>8.2f} | ${:>8.2f} | {:>8s} | {:>6s} | {:>10s} | {:>10s}".format(
                "SELL NOW", "--", call_cv, put_cv, result['current_value'],
                _format_dollar(sell_pnl), _format_pct(sell_pnl_pct), "--",
                _format_dollar(total_sell)))
        else:
            lines.append("{:<20s}| {:>8s} | ${:>8.2f} | ${:>8.2f} | ${:>8.2f} | {:>8s} | {:>6s} | {:>10s}".format(
                "SELL NOW", "--", call_cv, put_cv, result['current_value'],
                _format_dollar(sell_pnl), _format_pct(sell_pnl_pct), "--"))
    else:
        if show_total:
            total_sell = sell_pnl * quantity * 100
            lines.append("{:<20s}| {:>8s} | ${:>8.2f} | {:>8s} | {:>6s} | {:>10s} | {:>10s}".format(
                "SELL NOW", "--", result['current_value'],
                _format_dollar(sell_pnl), _format_pct(sell_pnl_pct), "--",
                _format_dollar(total_sell)))
        else:
            lines.append("{:<20s}| {:>8s} | ${:>8.2f} | {:>8s} | {:>6s} | {:>10s}".format(
                "SELL NOW", "--", result['current_value'],
                _format_dollar(sell_pnl), _format_pct(sell_pnl_pct), "--"))

    return "\n".join(lines)


def format_crush_matrix(result):
    """Format the crush sensitivity matrix.

    For straddle, shows dual breakeven columns (BE Down / BE Up).

    Returns:
        str: Formatted matrix with breakeven, flat P/L, expected move P/L per tier.
    """
    matrix = result['crush_matrix']
    exp_label = result.get('crush_matrix_exp_label')
    chosen_crush = result['crush_pct']
    position_type = result.get('position_type', 'single')
    is_straddle = position_type == 'straddle'

    # Build header
    exp_col = "{} P/L".format(exp_label) if exp_label else "Exp Move P/L"
    if is_straddle:
        header = "{:<17s}| {:>9s} | {:>9s} | {:>9s} | {:>12s}".format(
            "Crush ", "BE Down", "BE Up", "Flat P/L", exp_col)
    else:
        header = "{:<17s}| {:>9s} | {:>9s} | {:>12s}".format(
            "Crush ", "Breakeven", "Flat P/L", exp_col)
    sep = "-" * len(header)

    lines = ["Crush Sensitivity:", header, sep]

    # Find the tier closest to the chosen crush for the arrow marker
    closest_tier_crush = min((t['crush_pct'] for t in matrix),
                             key=lambda c: abs(c - chosen_crush))

    for tier in matrix:
        name = tier['tier_name']
        crush = tier['crush_pct']

        # Flat P/L
        flat_str = _format_dollar(tier['flat_pnl'])

        # Expected move P/L
        if tier['expected_move_pnl'] is not None:
            exp_str = _format_dollar(tier['expected_move_pnl'])
        else:
            exp_str = "N/A"

        # Arrow marker on closest tier
        marker = "  <-- default" if crush == closest_tier_crush else ""

        if is_straddle:
            be_pcts = tier.get('breakeven_pcts', [])
            # Separate into down (negative) and up (positive) roots
            down_roots = [bp for bp in be_pcts if bp < 0]
            up_roots = [bp for bp in be_pcts if bp >= 0]
            be_down_str = "{:.1f}%".format(down_roots[0]) if down_roots else "N/A"
            be_up_str = "+{:.1f}%".format(up_roots[0]) if up_roots else "N/A"

            lines.append("{:<10s} ({:>2.0f}%)  | {:>9s} | {:>9s} | {:>9s} | {:>12s}{}".format(
                name, crush, be_down_str, be_up_str, flat_str, exp_str, marker))
        else:
            # Single-leg breakeven
            if tier['breakeven_pct'] is not None:
                be_val = tier['breakeven_pct']
                be_sign = "+" if be_val >= 0 else ""
                be_str = "{}{:.1f}%".format(be_sign, be_val)
            else:
                be_str = "N/A"

            lines.append("{:<10s} ({:>2.0f}%)  | {:>9s} | {:>9s} | {:>12s}{}".format(
                name, crush, be_str, flat_str, exp_str, marker))

    return "\n".join(lines)


def format_footnotes(result):
    """Format warning footnotes.

    Returns:
        str: Footnote lines, or empty string if none.
    """
    warnings = result.get('warnings', [])
    if not warnings:
        return ""

    lines = [""]
    for w in warnings:
        lines.append("* {}".format(w))
    return "\n".join(lines)


def format_guide():
    """Format the interpretive guide section.

    Returns:
        str: Educational helper text explaining how to read the output.
    """
    return """
How to Read This:
------------------------------------------------------------------------------
SCENARIOS: "exp" = the move the options market is currently pricing in
(from straddle pricing). "hist" = average move from past earnings. If
hist > exp, the market may be underpricing the move (check Underpricing %
in the header). If they're close, the move is fairly priced.

UNDERPRICING: How much the market is underestimating this stock's typical
earnings move, as a percentage. This is primarily used to drive buy
signals; 15%+ is notable (WATCH), 30%+ is significant (BUY), 50%+ is
rare (STRONG BUY). This may change over time.

BREAKEVEN: The minimum stock move for holding through earnings to beat
selling now. Compare this to exp and hist --if both exceed your breakeven,
holding has historically favorable odds. If breakeven exceeds both, the
math favors selling.

VS SELL NOW: The real decision column. Negative = selling now is better
by that amount. Positive = holding through wins by that amount. This is
the comparison that matters --not P/L vs cost basis.

CRUSH SENSITIVITY: IV crush is not always 46%. Stocks that barely move
tend to see severe crush (60-70%+). Stocks with big gaps can see mild
crush (20-30%) because uncertainty persists. The matrix shows your P/L
across these possibilities so you can assess your risk range.

STRADDLE MODE: When using --straddle, both legs are modeled independently
with their own Greeks and IV. Key differences from single-leg:

  CALL EST / PUT EST: What each leg is worth post-earnings. One leg
  usually goes to ~$0 while the other carries the position. This is
  normal -- the straddle profits when the winning leg gains more than
  the losing leg gives up (after crush eats both).

  COMBINED: The sum of both legs -- your actual position value. P/L
  and vs Sell Now are based on this combined value vs combined cost.

  DUAL BREAKEVENS: The stock must move enough in EITHER direction to
  overcome IV crush on both legs. If you see "move -7% or +8%", those
  are the two hurdles. Compare to exp/hist -- if the typical move
  exceeds your breakevens, the straddle is underpriced.

  BE DOWN / BE UP (crush matrix): Shows both breakevens at each crush
  tier. "N/A" means no breakeven exists in that direction within 30%
  -- common for off-center straddles where one leg is far OTM.

  EXP MOVE P/L (crush matrix): For straddles, this uses the absolute
  expected move (either direction), since straddles profit from
  magnitude regardless of direction.

CAVEATS: Estimates use Greeks from the data timestamp shown above --use
--live for current data. Moves beyond 15% are less precise (Greek
approximation limits). Actual crush varies by stock, sector, and market
conditions. This tool estimates, it does not predict.
------------------------------------------------------------------------------
Suppress this guide with --no-guide"""


def format_scenario_table(result, show_guide=True):
    """Format the complete scenario output as a printable string.

    Concatenates: header + scenario table + crush matrix + footnotes + guide.

    Args:
        result: dict from calculate_scenarios()
        show_guide: If True, append the interpretive guide section

    Returns:
        str: Complete formatted output
    """
    thick_sep = "=" * 78

    parts = [
        "",
        format_header(result),
        "",
        thick_sep,
        format_scenario_rows(result),
        "",
        format_crush_matrix(result),
        format_footnotes(result),
    ]

    if show_guide:
        parts.append(format_guide())

    return "\n".join(parts)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Earnings Scenario Calculator -- model post-earnings option values with IV crush",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Directional play (single call or put):
  earnings_scenario.py "SYMBOL|STRIKE|EXPIRY|TYPE" --cost COST
  earnings_scenario.py "MRVL|85|2026-03-20|CALL" --cost 4.60
  earnings_scenario.py "NVDA|150|2026-03-05|PUT" --cost 3.50 --crush 60
  earnings_scenario.py "TOST|25|2026-04-17|CALL" --cost 1.04 --live --qty 2

Straddle play (call + put at same strike):
  earnings_scenario.py "SYMBOL|STRIKE|EXPIRY|CALL" --cost CALL_COST --straddle --put-cost PUT_COST
  earnings_scenario.py "TOST|25|2026-04-17|CALL" --cost 1.04 --straddle --put-cost 0.50
  earnings_scenario.py "TOST|25|2026-04-17|PUT" --cost 0.50 --straddle --call-cost 1.04
        """
    )
    parser.add_argument("contract", help="Contract hash: SYMBOL|STRIKE|EXPIRY|TYPE")
    parser.add_argument("--cost", type=float, required=True,
                        help="Cost basis per contract (dollars)")
    parser.add_argument("--qty", type=int, default=1,
                        help="Number of contracts (default: 1)")
    parser.add_argument("--crush", type=float, default=None,
                        help="Override IV crush %% (default: 46%%)")
    parser.add_argument("--live", action="store_true",
                        help="Fetch live Greeks from Tradier API")
    parser.add_argument("--no-guide", action="store_true",
                        help="Suppress the interpretive guide section")
    parser.add_argument("--straddle", action="store_true",
                        help="Model a straddle (infer opposite leg at same strike/expiry)")
    parser.add_argument("--put-cost", type=float, default=None,
                        help="Cost of the put leg (required with --straddle when primary is CALL)")
    parser.add_argument("--call-cost", type=float, default=None,
                        help="Cost of the call leg (required with --straddle when primary is PUT)")

    args = parser.parse_args()

    # Validate straddle args
    if args.straddle:
        try:
            parsed_check = parse_contract_hash(args.contract)
        except ValueError as e:
            print("Error: {}".format(e))
            sys.exit(1)
        if parsed_check['option_type'] == 'CALL' and args.put_cost is None:
            print("Error: --straddle with a CALL contract requires --put-cost")
            sys.exit(1)
        if parsed_check['option_type'] == 'PUT' and args.call_cost is None:
            print("Error: --straddle with a PUT contract requires --call-cost")
            sys.exit(1)

    try:
        result = calculate_scenarios(
            contract=args.contract,
            cost_basis=args.cost,
            quantity=args.qty,
            crush_pct=args.crush,
            live=args.live,
            straddle=args.straddle,
            put_cost=args.put_cost,
            call_cost=args.call_cost,
        )
        print(format_scenario_table(result, show_guide=not args.no_guide))
    except ValueError as e:
        print("Error: {}".format(e))
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)
    except Exception as e:
        print("Error: {}".format(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
