#!/usr/bin/env python3
"""
Earnings Moves Upcoming (ei_moves_upcoming.py)
----------------------------------------------
Processes upcoming earnings data and calculates expected moves, historical averages,
relative underpricing, and triggers earnings alerts.

Features:
- Calculate earnings_days_ahead from current date
- Calculate expected move from current IV (if available)
- Calculate straddle-based expected move (primary method)
- Retrieve historical average move from earnings_moves table (recent 6Q + all-time)
- Calculate relative underpricing: (recent_6Q_avg - expected) / expected * 100
  Answers: "By what % is the market underpricing this stock's recent earnings move pattern?"
- Signal classification based on relative underpricing (configurable thresholds)
- Set earnings_alert flag when relative underpricing >= threshold AND OI >= minimum
- Decimal formatting compliance

Signal Thresholds (configurable in config.json -> earnings_play -> signal_thresholds):
  AVOID:      relative_underpricing < 0%  (market overprices historical move)
  NEUTRAL:    0% to watch threshold       (default: 15%)
  WATCH:      watch to buy threshold      (default: 30%)
  BUY:        buy to strong_buy threshold (default: 50%)
  STRONG BUY: >= strong_buy threshold

  NOTE: These thresholds are provisional (set 2026-02-10). After accumulating 100+
  events with move_vs_expected_pct data (~early March 2026), validate whether these
  thresholds predict profitable trades and adjust accordingly.

Usage:
    python ei_moves_upcoming.py --symbol AAPL    # Test single symbol
    python ei_moves_upcoming.py                  # Process all symbols
    python ei_moves_upcoming.py --debug          # Enable debug logging

Author: Ben (with assistance from Claude)
Date: 2025-09-29 (relative underpricing + threshold recalibration: 2026-02-10)
"""

import os
import sys
import sqlite3
import logging
import argparse
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path for timezone utilities
sys.path.append(str(Path(__file__).parent.parent.parent))
from tools.timezone_utils import now_eastern

# Add tools directory to path for decimal formatter
sys.path.append(str(Path(__file__).parent.parent.parent / 'tools'))
from decimal_formatter import clean_database_row
from log_utils import beautiful_log

# Configuration constants (can be overridden by config.json)
DEFAULT_MOVE_DIFFERENCE_THRESHOLD = -2.0
DEFAULT_MIN_OPEN_INTEREST = 4000
DEFAULT_ALERT_UNDERPRICING_THRESHOLD = 15.0
DEFAULT_RECENT_QUARTERS = 6
DEFAULT_SIGNAL_THRESHOLDS = {
    'watch': 15.0,
    'buy': 30.0,
    'strong_buy': 50.0
}

def load_config():
    """Load configuration from project root"""
    try:
        config_path = Path(__file__).parent.parent.parent / 'config.json'
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Get earnings play specific config
        earnings_config = config.get('earnings_play', {})
        return {
            'move_difference_threshold': earnings_config.get('move_difference_threshold', DEFAULT_MOVE_DIFFERENCE_THRESHOLD),
            'min_open_interest': earnings_config.get('min_open_interest', DEFAULT_MIN_OPEN_INTEREST),
            'alert_underpricing_threshold': earnings_config.get('alert_underpricing_threshold', DEFAULT_ALERT_UNDERPRICING_THRESHOLD),
            'recent_quarters': earnings_config.get('recent_quarters', DEFAULT_RECENT_QUARTERS),
            'signal_thresholds': {
                'watch': earnings_config.get('signal_thresholds', {}).get('watch', DEFAULT_SIGNAL_THRESHOLDS['watch']),
                'buy': earnings_config.get('signal_thresholds', {}).get('buy', DEFAULT_SIGNAL_THRESHOLDS['buy']),
                'strong_buy': earnings_config.get('signal_thresholds', {}).get('strong_buy', DEFAULT_SIGNAL_THRESHOLDS['strong_buy']),
            }
        }
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logging.debug("Could not load config (using defaults): {}".format(e))
        return {
            'move_difference_threshold': DEFAULT_MOVE_DIFFERENCE_THRESHOLD,
            'min_open_interest': DEFAULT_MIN_OPEN_INTEREST,
            'alert_underpricing_threshold': DEFAULT_ALERT_UNDERPRICING_THRESHOLD,
            'recent_quarters': DEFAULT_RECENT_QUARTERS,
            'signal_thresholds': DEFAULT_SIGNAL_THRESHOLDS.copy()
        }

def get_database_path():
    """Get path to datalake.db"""
    return Path(__file__).parent.parent.parent / 'data' / 'datalake.db'

def calculate_earnings_days_ahead(earnings_date, current_date=None):
    """Calculate days until earnings from current date"""
    if not earnings_date:
        return None

    if current_date is None:
        current_date = now_eastern().strftime('%Y-%m-%d')

    try:
        earnings_dt = datetime.strptime(earnings_date, '%Y-%m-%d')
        current_dt = datetime.strptime(current_date, '%Y-%m-%d')
        days_ahead = (earnings_dt - current_dt).days
        return max(0, days_ahead)  # Don't return negative days
    except (ValueError, TypeError) as e:
        logging.debug("Date calculation error for {}: {}".format(earnings_date, e))
        return None

def get_historical_avg_move(symbol, db_path, recent_quarters=6):
    """Get historical average move percentages from earnings_moves table.

    Calculates both the all-time average and the recent-N-quarter average of
    absolute 1-day moves. The recent average drives the underpricing signal;
    the all-time average is stored for transparency.

    Args:
        symbol: Stock ticker symbol
        db_path: Path to database
        recent_quarters: Number of recent quarters to average (default: 6)

    Returns:
        dict: {'recent': float, 'alltime': float, 'quarters_used': int}
        Returns None if no historical data exists.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # All-time average
            cursor.execute("""
                SELECT AVG(ABS(move_1day_pct)) as avg_move_pct,
                       COUNT(*) as cnt
                FROM earnings_moves
                WHERE symbol = ?
                AND move_1day_pct IS NOT NULL
            """, (symbol,))

            alltime_row = cursor.fetchone()
            if not alltime_row or alltime_row[1] == 0:
                return None

            alltime_avg = alltime_row[0]

            # Recent N-quarter average (ordered by earnings_date DESC)
            cursor.execute("""
                SELECT AVG(abs_move) as avg_move_pct,
                       COUNT(*) as cnt
                FROM (
                    SELECT ABS(move_1day_pct) as abs_move
                    FROM earnings_moves
                    WHERE symbol = ?
                    AND move_1day_pct IS NOT NULL
                    AND earnings_date IS NOT NULL
                    ORDER BY earnings_date DESC
                    LIMIT ?
                )
            """, (symbol, recent_quarters))

            recent_row = cursor.fetchone()
            recent_avg = recent_row[0] if recent_row and recent_row[1] > 0 else alltime_avg
            quarters_used = recent_row[1] if recent_row else 0

            return {
                'recent': recent_avg,
                'alltime': alltime_avg,
                'quarters_used': quarters_used,
            }

    except (sqlite3.Error, ValueError, TypeError) as e:
        logging.debug("Historical move lookup error for {}: {}".format(symbol, e))
        return None

def get_expected_move_from_iv(symbol, earnings_days_ahead, db_path):
    """
    Calculate expected move from current IV (FALLBACK method).
    Expected Move = IV × √(Days to Earnings / 365) × 100

    Uses iv_front_month from option_symbol_summary, which is only populated for ~43%
    of symbols (strict DTE bucketing). This is the secondary method — the straddle method
    (get_straddle_expected_move) is preferred and has better coverage for near-term earnings.

    Coverage note (audited 2026-02-24): iv_front_month is NULL for ~57% of symbols, but
    this does NOT cause a real coverage gap. In the actionable 0-30 day window, between
    this method and the straddle method, 96-100% of symbols have expected move data.
    The gaps are only in the 31-90 day horizon where earnings aren't actionable anyway.
    iv_30dte (99.9% populated) could be used as a fallback but isn't worth the change
    since distant earnings aren't traded.

    Args:
        symbol: Stock symbol
        earnings_days_ahead: Number of days until earnings
        db_path: Path to database
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # Get latest IV data and current price
            cursor.execute("""
                SELECT
                    oss.iv_front_month,
                    hp.close_price
                FROM option_symbol_summary oss
                JOIN historical_prices hp ON oss.symbol = hp.symbol
                WHERE oss.symbol = ?
                    AND oss.trade_date = (SELECT MAX(trade_date) FROM option_symbol_summary)
                    AND hp.trade_date = (SELECT MAX(trade_date) FROM historical_prices WHERE symbol = ?)
            """, (symbol, symbol))

            result = cursor.fetchone()
            if not result or not result[0] or not result[1]:
                return None

            iv_front_month, current_price = result

            if iv_front_month > 0 and current_price > 0 and earnings_days_ahead > 0:
                # Calculate expected move: IV × √(Days to Earnings / 365) × 100
                # Note: IV should already be in decimal form (e.g., 0.25 for 25%)
                expected_move_pct = iv_front_month * math.sqrt(earnings_days_ahead / 365.0) * 100
                return expected_move_pct

            return None

    except Exception as e:
        logging.debug("Expected move calculation error for {}: {}".format(symbol, e))
        return None

def get_open_interest_for_symbol(symbol, db_path):
    """Get latest total open interest for symbol"""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT total_open_interest
                FROM option_symbol_summary
                WHERE symbol = ?
                    AND trade_date = (SELECT MAX(trade_date) FROM option_symbol_summary)
            """, (symbol,))

            result = cursor.fetchone()
            return result[0] if result and result[0] is not None else 0

    except Exception as e:
        logging.debug("Open interest lookup error for {}: {}".format(symbol, e))
        return 0

def get_straddle_expected_move(symbol, earnings_date, db_path):
    """
    Calculate expected move using ATM straddle method (PRIMARY method).
    Expected Move = (ATM Call Price + ATM Put Price) × 0.85 / Stock Price × 100

    Uses options expiring AFTER earnings date, sourced from option_contracts table.
    This is preferred over the IV-based method because it directly reflects what the
    market is pricing for the earnings move.

    Coverage note (audited 2026-02-24): This method requires option_contracts with
    expiration_date >= earnings_date. The Option Pipeline collects contracts ~2 months
    out, so symbols with earnings more than ~60 days away won't have post-earnings
    expirations yet. This is expected — straddle coverage fills in naturally as earnings
    dates approach. In the 0-14 day window, straddle coverage is excellent.

    Args:
        symbol: Stock symbol
        earnings_date: Date of earnings announcement (YYYY-MM-DD)
        db_path: Path to database

    Returns:
        Expected move percentage, or None if calculation not possible
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # Get latest trade date and stock price
            cursor.execute("""
                SELECT trade_date, close_price
                FROM historical_prices
                WHERE symbol = ?
                    AND trade_date = (SELECT MAX(trade_date) FROM historical_prices WHERE symbol = ?)
            """, (symbol, symbol))

            result = cursor.fetchone()
            if not result:
                logging.debug("No price data found for {} in straddle calculation".format(symbol))
                return None

            trade_date, stock_price = result
            if not stock_price or stock_price <= 0:
                logging.debug("Invalid stock price for {} in straddle calculation".format(symbol))
                return None

            # Find first expiration date after earnings
            cursor.execute("""
                SELECT DISTINCT expiration_date
                FROM option_contracts
                WHERE symbol = ?
                    AND trade_date = ?
                    AND expiration_date >= ?
                    AND last_price IS NOT NULL
                ORDER BY expiration_date ASC
                LIMIT 1
            """, (symbol, trade_date, earnings_date))

            result = cursor.fetchone()
            if not result:
                logging.debug("No post-earnings expiration found for {} (earnings: {})".format(symbol, earnings_date))
                return None

            expiration_date = result[0]

            # Find ATM strike (closest to stock price) for both call and put
            cursor.execute("""
                SELECT strike, option_type, last_price
                FROM option_contracts
                WHERE symbol = ?
                    AND trade_date = ?
                    AND expiration_date = ?
                    AND last_price > 0
                    AND option_type IN ('CALL', 'PUT')
                ORDER BY ABS(strike - ?) ASC
            """, (symbol, trade_date, expiration_date, stock_price))

            contracts = cursor.fetchall()
            if not contracts:
                logging.debug("No ATM contracts found for {} at expiration {}".format(symbol, expiration_date))
                return None

            # Find closest strike and get both call and put at that strike
            atm_strike = contracts[0][0]  # Closest strike to stock price

            call_price = None
            put_price = None

            for strike, option_type, price in contracts:
                if strike == atm_strike:
                    if option_type == 'CALL':
                        call_price = price
                    elif option_type == 'PUT':
                        put_price = price

            # Need both call and put to form straddle
            if not call_price or not put_price:
                logging.debug("Incomplete straddle for {} (strike: {}, call: {}, put: {})".format(
                    symbol, atm_strike, call_price, put_price))
                return None

            # Calculate straddle expected move
            straddle_price = call_price + put_price
            expected_move_dollars = straddle_price * 0.85  # Industry standard multiplier
            expected_move_pct = (expected_move_dollars / stock_price) * 100

            logging.debug("Straddle for {} at ${:.2f} strike (exp: {}): Call=${:.2f}, Put=${:.2f}, Move={:.2f}%".format(
                symbol, atm_strike, expiration_date, call_price, put_price, expected_move_pct))

            return expected_move_pct

    except Exception as e:
        logging.debug("Straddle calculation error for {}: {}".format(symbol, e))
        return None

def determine_earnings_play_signal(relative_underpricing_pct, config):
    """Determine earnings play signal based on relative underpricing.

    Relative underpricing = (historical_avg - straddle_expected) / straddle_expected * 100
    Answers: "By what % is the market underpricing this stock's typical earnings move?"

    NOTE: The straddle_expected_move_pct denominator already includes a 0.85 industry-
    standard slippage/spread multiplier (see get_straddle_expected_move). This makes
    relative underpricing values slightly higher than they would be using raw straddle
    prices. This is intentional — we're comparing against the tradeable expected move.

    Args:
        relative_underpricing_pct: (historical - expected) / expected * 100
        config: Dict with 'signal_thresholds' sub-dict (watch/buy/strong_buy)

    Returns:
        Signal string: UNKNOWN, AVOID, NEUTRAL, WATCH, BUY, STRONG BUY
    """
    if relative_underpricing_pct is None:
        return "UNKNOWN"

    thresholds = config.get('signal_thresholds', DEFAULT_SIGNAL_THRESHOLDS)
    watch_threshold = thresholds.get('watch', 15.0)
    buy_threshold = thresholds.get('buy', 30.0)
    strong_buy_threshold = thresholds.get('strong_buy', 50.0)

    if relative_underpricing_pct < 0:
        return "AVOID"
    elif relative_underpricing_pct < watch_threshold:
        return "NEUTRAL"
    elif relative_underpricing_pct < buy_threshold:
        return "WATCH"
    elif relative_underpricing_pct < strong_buy_threshold:
        return "BUY"
    else:
        return "STRONG BUY"

def should_trigger_earnings_alert(relative_underpricing_pct, total_open_interest, config):
    """Determine if earnings alert should be triggered.

    Alert fires when relative underpricing exceeds threshold AND open interest
    meets minimum. Aligned with signal system — default threshold matches WATCH level.

    Args:
        relative_underpricing_pct: (historical - expected) / expected * 100
        total_open_interest: Current total OI from option_symbol_summary
        config: Dict with 'alert_underpricing_threshold' and 'min_open_interest'

    Returns:
        bool: True if alert should fire
    """
    if relative_underpricing_pct is None:
        return False

    alert_threshold = config.get('alert_underpricing_threshold', DEFAULT_ALERT_UNDERPRICING_THRESHOLD)
    min_oi = config.get('min_open_interest', DEFAULT_MIN_OPEN_INTEREST)

    return (relative_underpricing_pct >= alert_threshold and
            total_open_interest >= min_oi)

def _ensure_earnings_upcoming_schema(cursor):
    """Add recent-6Q columns to earnings_upcoming if missing (idempotent).

    Migration: April 2026 — added historical_avg_move_alltime_pct and
    historical_quarters_used for transparent recent-vs-alltime reporting.
    """
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(earnings_upcoming)")}

    if 'historical_avg_move_alltime_pct' not in existing:
        cursor.execute("ALTER TABLE earnings_upcoming ADD COLUMN historical_avg_move_alltime_pct REAL")
        logging.debug("Added column historical_avg_move_alltime_pct to earnings_upcoming")

    if 'historical_quarters_used' not in existing:
        cursor.execute("ALTER TABLE earnings_upcoming ADD COLUMN historical_quarters_used INTEGER")
        logging.debug("Added column historical_quarters_used to earnings_upcoming")


def process_symbol_earnings_upcoming(symbol, db_path, config, current_date=None):
    """Process upcoming earnings data for a single symbol"""
    if not symbol or not isinstance(symbol, str):
        logging.error("Invalid symbol provided: {}".format(symbol))
        return False

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # Get current earnings_upcoming record
            cursor.execute("""
                SELECT earnings_date, earnings_time, expected_move_pct,
                       historical_avg_move_pct, move_difference_pct,
                       earnings_play_signal, earnings_alert, straddle_expected_move_pct
                FROM earnings_upcoming
                WHERE symbol = ?
            """, (symbol,))

            result = cursor.fetchone()
            if not result:
                logging.warning("No earnings_upcoming record found for {}".format(symbol))
                return False

            earnings_date, earnings_time, existing_expected_move, existing_historical_avg, \
            existing_move_diff, existing_signal, existing_alert, existing_straddle_move = result

            if not earnings_date:
                logging.debug("No earnings date found for {}".format(symbol))
                return False

            # Calculate earnings_days_ahead
            earnings_days_ahead = calculate_earnings_days_ahead(earnings_date, current_date)

            # Get historical average move (ALWAYS recalculate from latest earnings_moves data)
            # Returns recent-6Q and all-time averages; recent drives the signal.
            recent_quarters = config.get('recent_quarters', DEFAULT_RECENT_QUARTERS)
            hist_data = get_historical_avg_move(symbol, db_path, recent_quarters)
            if hist_data:
                historical_avg_move_pct = hist_data['recent']
                historical_avg_move_alltime_pct = hist_data['alltime']
                historical_quarters_used = hist_data['quarters_used']
            else:
                historical_avg_move_pct = None
                historical_avg_move_alltime_pct = None
                historical_quarters_used = 0

            # Calculate expected move from IV (FALLBACK — ~43% coverage due to iv_front_month gaps)
            expected_move_pct = get_expected_move_from_iv(symbol, earnings_days_ahead, db_path)

            # Calculate straddle-based expected move (PRIMARY METHOD — fills in as earnings approach)
            # Coverage: 96-100% within 30 days, lower for distant earnings (structural, not a bug)
            straddle_expected_move_pct = get_straddle_expected_move(symbol, earnings_date, db_path)

            # Calculate move difference (historical - expected) — absolute metric, kept for backward compat
            # Use STRADDLE method as primary, fallback to IV method
            # Positive = underpriced (historical moves more than expected)
            # Negative = overpriced (historical moves less than expected)
            if straddle_expected_move_pct and historical_avg_move_pct:
                move_difference_pct = historical_avg_move_pct - straddle_expected_move_pct
            elif expected_move_pct and historical_avg_move_pct:
                move_difference_pct = historical_avg_move_pct - expected_move_pct
            else:
                move_difference_pct = existing_move_diff

            # Calculate relative underpricing — PRIMARY signal metric (added 2026-02-10, 6Q recency 2026-04-13)
            # Formula: (recent_6Q_avg - expected) / expected * 100
            # Answers: "By what % is the market underpricing this stock's recent earnings move pattern?"
            # Uses straddle (preferred) or IV-based expected move as denominator.
            # A 3% absolute diff on a 10% expected move = 30% relative underpricing (interesting!)
            # A 3% absolute diff on a 50% expected move = 6% relative underpricing (meh)
            #
            # If BOTH methods return None, relative_underpricing stays None → signal = UNKNOWN.
            # This happens for ~48% of the universe but almost entirely for earnings 31+ days out.
            # Within 0-30 days, 96-100% of symbols have at least one method populated.
            relative_underpricing_pct = None
            if straddle_expected_move_pct and historical_avg_move_pct and straddle_expected_move_pct > 0:
                relative_underpricing_pct = ((historical_avg_move_pct - straddle_expected_move_pct) / straddle_expected_move_pct) * 100
            elif expected_move_pct and historical_avg_move_pct and expected_move_pct > 0:
                relative_underpricing_pct = ((historical_avg_move_pct - expected_move_pct) / expected_move_pct) * 100

            # Determine earnings play signal from relative underpricing
            earnings_play_signal = determine_earnings_play_signal(relative_underpricing_pct, config)

            # Get open interest for alert determination
            total_open_interest = get_open_interest_for_symbol(symbol, db_path)

            # Determine if earnings alert should be triggered
            earnings_alert = should_trigger_earnings_alert(relative_underpricing_pct, total_open_interest, config)

            # Prepare update data
            update_data = {
                'earnings_days_ahead': earnings_days_ahead,
                'expected_move_pct': expected_move_pct,
                'straddle_expected_move_pct': straddle_expected_move_pct,
                'historical_avg_move_pct': historical_avg_move_pct,
                'historical_avg_move_alltime_pct': historical_avg_move_alltime_pct,
                'historical_quarters_used': historical_quarters_used,
                'move_difference_pct': move_difference_pct,
                'relative_underpricing_pct': relative_underpricing_pct,
                'earnings_play_signal': earnings_play_signal,
                'earnings_alert': 1 if earnings_alert else 0,
                'updated_at': now_eastern().strftime('%Y-%m-%d %H:%M:%S')
            }

            # Clean decimal formatting
            update_data = clean_database_row(update_data)

            # Update the record
            # COALESCE for expected_move_pct and straddle_expected_move_pct:
            # On earnings day, days_ahead=0 makes the IV formula return None,
            # overwriting the valid value from the day before. COALESCE preserves
            # the last good value when the new calculation returns NULL.
            cursor.execute("""
                UPDATE earnings_upcoming
                SET earnings_days_ahead = ?,
                    expected_move_pct = COALESCE(?, expected_move_pct),
                    straddle_expected_move_pct = COALESCE(?, straddle_expected_move_pct),
                    historical_avg_move_pct = ?,
                    historical_avg_move_alltime_pct = ?,
                    historical_quarters_used = ?,
                    move_difference_pct = ?,
                    relative_underpricing_pct = ?,
                    earnings_play_signal = ?,
                    earnings_alert = ?,
                    updated_at = ?
                WHERE symbol = ?
            """, (
                update_data['earnings_days_ahead'],
                update_data['expected_move_pct'],
                update_data['straddle_expected_move_pct'],
                update_data['historical_avg_move_pct'],
                update_data['historical_avg_move_alltime_pct'],
                update_data['historical_quarters_used'],
                update_data['move_difference_pct'],
                update_data['relative_underpricing_pct'],
                update_data['earnings_play_signal'],
                update_data['earnings_alert'],
                update_data['updated_at'],
                symbol
            ))

            conn.commit()

            # Log results
            if earnings_alert:
                signal_emoji = {'WATCH': '\U0001f7e1', 'BUY': '\U0001f7e0', 'STRONG BUY': '\U0001f534'}
                emoji = signal_emoji.get(earnings_play_signal, '\u26aa')
                logging.info("   {} {} \u2014 Rel underpricing: {:.1f}%, Signal: {}, OI: {:,}, Days: {}".format(
                    emoji,
                    symbol,
                    relative_underpricing_pct or 0,
                    earnings_play_signal,
                    total_open_interest,
                    earnings_days_ahead or 0
                ))
            else:
                logging.debug("Updated {}: Rel underpricing: {:.1f}%, Signal: {}, OI: {:,}".format(
                    symbol,
                    relative_underpricing_pct or 0,
                    earnings_play_signal,
                    total_open_interest
                ))

            return True

    except (sqlite3.Error, ValueError, TypeError) as e:
        logging.error("Error processing symbol {}: {}".format(symbol, e))
        return False

def get_symbols_to_process(db_path, symbol=None):
    """Get list of symbols to process from earnings_upcoming.

    Only returns symbols with earnings_date >= today (Eastern time).
    Past-due rows are left in the table for the weekly refresh to archive,
    but are never recalculated — their near-zero straddle values produce
    absurd underpricing numbers and false STRONG BUY signals.
    """
    today_str = now_eastern().strftime('%Y-%m-%d')
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            if symbol:
                cursor.execute("""
                    SELECT symbol FROM earnings_upcoming
                    WHERE symbol = ? AND earnings_date >= ?
                """, (symbol, today_str))
            else:
                cursor.execute("""
                    SELECT symbol
                    FROM earnings_upcoming
                    WHERE earnings_date IS NOT NULL
                      AND earnings_date >= ?
                    ORDER BY earnings_date ASC, symbol ASC
                """, (today_str,))

            symbols = [row[0] for row in cursor.fetchall()]
            return symbols

    except (sqlite3.Error, ValueError, TypeError) as e:
        logging.error("Error getting symbols to process: {}".format(e))
        return []

def update_expected_moves():
    """Wrapper function for programmatic calling from ei_main.py

    Returns:
        dict: Update statistics
    """
    db_path = get_database_path()
    config = load_config()
    current_date = now_eastern().strftime('%Y-%m-%d')

    # Ensure schema is current (idempotent — one PRAGMA check per run)
    with sqlite3.connect(db_path) as conn:
        _ensure_earnings_upcoming_schema(conn.cursor())
        conn.commit()

    # Get all symbols to process (excludes past-due earnings)
    symbols = get_symbols_to_process(db_path)

    if not symbols:
        logging.info("   └─ No symbols found to process")
        return {'processed': 0, 'failed': 0, 'alerts': 0, 'alert_details': []}

    beautiful_log("Processing {} upcoming earnings events".format(len(symbols)), 'info')

    processed = 0
    failed = 0
    alerts = 0
    alert_details = []

    for symbol in symbols:
        try:
            success = process_symbol_earnings_upcoming(symbol, db_path, config, current_date)
            if success:
                processed += 1

                # Check if alert was triggered and capture details
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT earnings_alert, earnings_days_ahead,
                               relative_underpricing_pct, earnings_play_signal
                        FROM earnings_upcoming WHERE symbol = ?
                    """, (symbol,))
                    result = cursor.fetchone()
                    if result and result[0]:
                        alerts += 1
                        alert_details.append({
                            'symbol': symbol,
                            'days_ahead': result[1],
                            'relative_underpricing_pct': result[2],
                            'signal': result[3] or 'UNKNOWN',
                        })
            else:
                failed += 1
        except Exception as e:
            logging.error("Processing failed for {}: {}".format(symbol, e))
            failed += 1

    beautiful_log("Expected moves updated: {} processed, {} alerts, {} failed".format(
        processed, alerts, failed), 'success')

    return {'processed': processed, 'failed': failed, 'alerts': alerts, 'alert_details': alert_details}

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Process Upcoming Earnings Moves and Alerts')
    parser.add_argument('--symbol', type=str, help='Process single symbol (testing)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--no-interaction', action='store_true', help='Run without user prompts')

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    log_file = Path(__file__).parent / 'ei_moves_upcoming.log'

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding='utf-8')
        ]
    )

    print("Earnings Moves Upcoming Processor")

    try:
        db_path = get_database_path()
        config = load_config()
        current_date = now_eastern().strftime('%Y-%m-%d')

        # Validate symbol input if provided
        if args.symbol and not isinstance(args.symbol, str):
            print("Error: Invalid symbol provided")
            return 1

        # Get symbols to process
        if args.symbol:
            symbols = get_symbols_to_process(db_path, args.symbol.upper())
            print("Testing mode: {}".format(args.symbol))
        else:
            symbols = get_symbols_to_process(db_path)
            print("Processing {} symbols with upcoming earnings".format(len(symbols)))

        if not symbols:
            print("No symbols found to process")
            return 0

        # Ensure schema is current (idempotent — one PRAGMA check per run)
        with sqlite3.connect(db_path) as conn:
            _ensure_earnings_upcoming_schema(conn.cursor())
            conn.commit()

        if not args.no_interaction and not args.symbol:
            input("\nPress Enter to begin processing...")

        # Process symbols
        processed = 0
        failed = 0
        alerts_triggered = 0

        for i, symbol in enumerate(symbols):
            print("[{}/{}] Processing {}...".format(i + 1, len(symbols), symbol))

            try:
                success = process_symbol_earnings_upcoming(symbol, db_path, config, current_date)
                if success:
                    processed += 1

                    # Check if alert was triggered
                    with sqlite3.connect(db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT earnings_alert FROM earnings_upcoming WHERE symbol = ?", (symbol,))
                        result = cursor.fetchone()
                        if result and result[0]:
                            alerts_triggered += 1
                else:
                    failed += 1

            except (sqlite3.Error, ValueError, TypeError) as e:
                logging.error("Processing failed for {}: {}".format(symbol, e))
                failed += 1

            # Progress update every 25 symbols
            if (i + 1) % 25 == 0:
                print("Progress: {}/{} symbols, {} processed, {} failed".format(
                    i + 1, len(symbols), processed, failed))

        logging.info("Earnings processing: {} processed, {} failed, {} alerts triggered".format(
            processed, failed, alerts_triggered))

        return 0

    except Exception as e:
        print("\nProcessing failed: {}".format(e))
        logging.error("Processing error: {}".format(e))
        return 1

if __name__ == "__main__":
    exit(main())