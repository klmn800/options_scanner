#!/usr/bin/env python3
"""
Earnings Backfill: Dec 2025 - Feb 2026 (ei_backfill_dec_feb.py)
----------------------------------------------------------------
Recovers missing earnings_events and earnings_moves data for the Dec 2025 -
Feb 2026 earnings season. The old weekly collector had a bug where the fetcher
deleted past-date rows from earnings_upcoming BEFORE the archive could copy
them to earnings_events. Only 171 of ~600-700 expected events survived.

Three sequential passes:
  Pass 1: Fetch historical earnings from Finnhub → INSERT into earnings_events
  Pass 2: Calculate price moves from historical_prices → INSERT into earnings_moves
  Pass 3: Calculate IV metrics from option_symbol_summary → UPDATE earnings_moves

Idempotent — safe to re-run. Uses INSERT OR IGNORE and only updates NULL fields.

Usage:
    python strategies/earnings_intel/ei_backfill_dec_feb.py --no-interaction
    python strategies/earnings_intel/ei_backfill_dec_feb.py --dry-run
    python strategies/earnings_intel/ei_backfill_dec_feb.py --pass 1
    python strategies/earnings_intel/ei_backfill_dec_feb.py --symbols AAPL,NVDA,TSLA --verbose

Author: Ben (with Claude)
Date: 2026-03-02
"""

import os
import sys
import json
import time
import math
import sqlite3
import logging
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'tools'))

from core.finnhub_api import FinnhubAPI
from core.symbols_klmn800 import get_specialty_list, ETF_SYMBOLS
from tools.timezone_utils import now_eastern, eastern_isoformat
from tools.log_utils import beautiful_log
from tools.decimal_formatter import clean_database_row
from strategies.earnings_intel.ei_backfill_metrics import (
    get_iv_at_date, compute_iv_metrics, compute_expected_move
)

# Date range for backfill
BACKFILL_FROM = '2025-12-01'
BACKFILL_TO = '2026-02-28'

# ETFs to exclude (no earnings)
ETF_EXCLUSIONS = set(ETF_SYMBOLS) | {'JETS'}


def get_database_path():
    return project_root / 'data' / 'datalake.db'


def get_sector_archive_dir():
    return project_root / 'data' / 'sector_archive'


def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logs_dir = project_root / 'logs' / 'diagnostic'
    logs_dir.mkdir(parents=True, exist_ok=True)
    logfile = logs_dir / 'backfill_dec_feb_{}.log'.format(
        now_eastern().strftime('%Y-%m-%d'))

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(logfile), encoding='utf-8'),
        ]
    )


# ============================================================================
# Pass 1: Fetch Earnings Events from Finnhub
# ============================================================================

def pass1_fetch_events(db_path, api, symbols, dry_run=False):
    """Fetch historical earnings from Finnhub and insert into earnings_events.

    Queries each symbol for the Dec 2025 - Feb 2026 date range. Unlike the
    weekly collector (which takes only releases[0]), this iterates ALL releases
    since a symbol may have reported multiple times in the 3-month window.

    Finnhub returns epsActual/revenueActual for past dates, so we capture
    those and compute eps_surprise_pct.
    """
    beautiful_log("=== Pass 1: Fetch earnings events from Finnhub ===", level='phase')

    from_date = date.fromisoformat(BACKFILL_FROM)
    to_date = date.fromisoformat(BACKFILL_TO)

    records = []
    no_data_symbols = []
    errors = 0
    api_calls = 0
    total = len(symbols)

    for i, symbol in enumerate(symbols, 1):
        try:
            releases = api.get_earnings_calendar(from_date, to_date, symbol=symbol)
            api_calls += 1

            if releases:
                for release in releases:
                    earnings_date = release.get('date')
                    if not earnings_date:
                        continue
                    # Only keep dates in our target window
                    if earnings_date < BACKFILL_FROM or earnings_date > BACKFILL_TO:
                        continue

                    event = _transform_finnhub_to_event(symbol, release)
                    records.append(event)
            else:
                no_data_symbols.append(symbol)

        except Exception as e:
            errors += 1
            logging.warning("Finnhub fetch failed for {}: {}".format(symbol, e))

        if i % 50 == 0 or i == total:
            beautiful_log("  {}/{} symbols ({} events found, {} no data, {} errors)".format(
                i, total, len(records), len(no_data_symbols), errors), level='info')

    beautiful_log("  Fetch complete: {} events from {} symbols ({} API calls)".format(
        len(records), total - len(no_data_symbols) - errors, api_calls), level='info')

    if dry_run:
        beautiful_log("  [DRY RUN] Would insert {} events".format(len(records)), level='info')
        return {'events_found': len(records), 'inserted': 0, 'no_data': len(no_data_symbols),
                'errors': errors, 'api_calls': api_calls}

    # Batch insert
    inserted = _batch_insert_events(db_path, records)
    beautiful_log("  Inserted {} new events (existing rows preserved via INSERT OR IGNORE)".format(
        inserted), level='info')

    return {'events_found': len(records), 'inserted': inserted,
            'no_data': len(no_data_symbols), 'errors': errors, 'api_calls': api_calls}


def _transform_finnhub_to_event(symbol, release):
    """Transform a Finnhub release dict into an earnings_events record."""
    earnings_date = release['date']
    earnings_dt = datetime.strptime(earnings_date, '%Y-%m-%d')

    # Fiscal quarter estimation (same logic as deprecated ei_backfill_events.py)
    month = earnings_dt.month
    if month in [1, 2, 3]:
        fiscal_quarter = 4
        fiscal_year = earnings_dt.year - 1
    elif month in [4, 5, 6]:
        fiscal_quarter = 1
        fiscal_year = earnings_dt.year
    elif month in [7, 8, 9]:
        fiscal_quarter = 2
        fiscal_year = earnings_dt.year
    else:
        fiscal_quarter = 3
        fiscal_year = earnings_dt.year

    # Finnhub provides actuals for past earnings
    estimated_eps = release.get('epsEstimate')
    actual_eps = release.get('epsActual')
    revenue_estimate = release.get('revenueEstimate')

    # Timing
    timing = release.get('hour', 'Unknown')

    # Compute EPS surprise
    eps_surprise_pct = None
    if estimated_eps is not None and actual_eps is not None and estimated_eps != 0:
        eps_surprise_pct = ((actual_eps - estimated_eps) / abs(estimated_eps)) * 100

    record = {
        'symbol': symbol,
        'earnings_date': earnings_date,
        'fiscal_year': fiscal_year,
        'fiscal_quarter': fiscal_quarter,
        'estimated_eps': estimated_eps,
        'actual_eps': actual_eps,
        'eps_surprise_pct': eps_surprise_pct,
        'earnings_time': timing,
        'source': 'finnhub_backfill',
        'is_backfilled': 1,
        'eps_estimate': estimated_eps,
        'revenue_estimate': revenue_estimate,
    }

    # Clean decimals (but set timestamps AFTER clean_database_row)
    cleaned = clean_database_row(record)
    cleaned['earnings_date'] = earnings_date  # Restore after clean
    cleaned['earnings_time'] = timing
    cleaned['source'] = 'finnhub_backfill'
    cleaned['symbol'] = symbol
    return cleaned


def _batch_insert_events(db_path, records):
    """Batch INSERT OR IGNORE into earnings_events. Returns count inserted."""
    if not records:
        return 0

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    cursor = conn.cursor()

    # Ensure signal columns exist (idempotent migration from ei_collector.py)
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(earnings_events)")}
    for col in ['earnings_play_signal', 'relative_underpricing_pct', 'expected_move_pct',
                'straddle_expected_move_pct', 'historical_avg_move_pct',
                'historical_avg_move_alltime_pct', 'historical_quarters_used',
                'eps_estimate', 'revenue_estimate']:
        if col not in existing:
            if col == 'earnings_play_signal':
                col_type = 'TEXT'
            elif col == 'historical_quarters_used':
                col_type = 'INTEGER'
            else:
                col_type = 'REAL'
            cursor.execute("ALTER TABLE earnings_events ADD COLUMN {} {}".format(col, col_type))

    inserted = 0
    for rec in records:
        cursor.execute("""
            INSERT OR IGNORE INTO earnings_events
                (symbol, earnings_date, fiscal_year, fiscal_quarter,
                 estimated_eps, actual_eps, eps_surprise_pct,
                 earnings_time, source, is_backfilled,
                 eps_estimate, revenue_estimate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rec.get('symbol'), rec.get('earnings_date'),
            rec.get('fiscal_year'), rec.get('fiscal_quarter'),
            rec.get('estimated_eps'), rec.get('actual_eps'),
            rec.get('eps_surprise_pct'), rec.get('earnings_time'),
            rec.get('source'), rec.get('is_backfilled'),
            rec.get('eps_estimate'), rec.get('revenue_estimate'),
        ))
        inserted += cursor.rowcount

    conn.commit()
    conn.close()
    return inserted


# ============================================================================
# Pass 2: Calculate Price Moves from historical_prices
# ============================================================================

def pass2_calculate_price_moves(db_path, dry_run=False):
    """For newly inserted events without earnings_moves, calculate price moves
    from historical_prices and insert into earnings_moves."""

    beautiful_log("=== Pass 2: Calculate price moves from historical_prices ===", level='phase')

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Ensure earnings_date column exists on earnings_moves (idempotent migration)
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(earnings_moves)")}
    if 'earnings_date' not in existing:
        cursor.execute("ALTER TABLE earnings_moves ADD COLUMN earnings_date TEXT")

    # Get events in our range that don't have moves yet
    cursor.execute("""
        SELECT ee.event_id, ee.symbol, ee.earnings_date
        FROM earnings_events ee
        LEFT JOIN earnings_moves em ON ee.event_id = em.event_id
        WHERE ee.earnings_date >= ?
        AND ee.earnings_date <= ?
        AND em.move_id IS NULL
        ORDER BY ee.earnings_date
    """, (BACKFILL_FROM, BACKFILL_TO))
    events = cursor.fetchall()

    beautiful_log("  {} events need price moves".format(len(events)), level='info')

    if not events:
        beautiful_log("  Nothing to calculate", level='info')
        conn.close()
        return {'eligible': 0, 'filled': 0, 'no_data': 0}

    if dry_run:
        beautiful_log("  [DRY RUN] Would calculate moves for {} events".format(len(events)), level='info')
        conn.close()
        return {'eligible': len(events), 'filled': 0, 'no_data': 0}

    filled = 0
    no_data = 0

    for i, event in enumerate(events, 1):
        moves = _calculate_price_moves(cursor, event['symbol'], event['earnings_date'])

        if moves and moves.get('move_1day_pct') is not None:
            clean = clean_database_row(moves)
            now_ts = now_eastern().strftime('%Y-%m-%d %H:%M:%S')

            cursor.execute("""
                INSERT OR IGNORE INTO earnings_moves
                    (event_id, symbol, earnings_date,
                     move_1day_pct, move_2day_pct, move_3day_pct, move_5day_pct,
                     max_intraday_move_pct, move_direction,
                     calculated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event['event_id'], event['symbol'], event['earnings_date'],
                clean.get('move_1day_pct'), clean.get('move_2day_pct'),
                clean.get('move_3day_pct'), clean.get('move_5day_pct'),
                clean.get('max_intraday_move_pct'), clean.get('move_direction'),
                now_ts,
            ))
            filled += 1
        else:
            no_data += 1

        if i % 100 == 0:
            conn.commit()
            beautiful_log("  {}/{} processed ({} filled, {} no data)".format(
                i, len(events), filled, no_data), level='info')

    conn.commit()
    conn.close()

    beautiful_log("  Price moves: {} filled, {} insufficient data".format(filled, no_data), level='info')
    return {'eligible': len(events), 'filled': filled, 'no_data': no_data}


def _calculate_price_moves(cursor, symbol, earnings_date):
    """Calculate price moves from historical_prices.
    Reused from ei_backfill_price_moves.py."""

    def _get_close_on_or_after(sym, target):
        cursor.execute("""
            SELECT close_price FROM historical_prices
            WHERE symbol = ? AND trade_date >= ?
            ORDER BY trade_date ASC LIMIT 1
        """, (sym, target))
        r = cursor.fetchone()
        return r['close_price'] if r else None

    def _get_ohlc_on_or_after(sym, target):
        cursor.execute("""
            SELECT open_price, high_price, low_price FROM historical_prices
            WHERE symbol = ? AND trade_date >= ?
            ORDER BY trade_date ASC LIMIT 1
        """, (sym, target))
        return cursor.fetchone()

    earnings_dt = datetime.strptime(earnings_date, '%Y-%m-%d')

    price_t0 = _get_close_on_or_after(symbol, earnings_date)
    if not price_t0:
        return {}

    t1 = (earnings_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    t2 = (earnings_dt + timedelta(days=2)).strftime('%Y-%m-%d')
    t3 = (earnings_dt + timedelta(days=3)).strftime('%Y-%m-%d')
    t5 = (earnings_dt + timedelta(days=5)).strftime('%Y-%m-%d')

    price_t1 = _get_close_on_or_after(symbol, t1)
    price_t2 = _get_close_on_or_after(symbol, t2)
    price_t3 = _get_close_on_or_after(symbol, t3)
    price_t5 = _get_close_on_or_after(symbol, t5)

    moves = {}
    if price_t1:
        moves['move_1day_pct'] = ((price_t1 - price_t0) / price_t0) * 100
    if price_t2:
        moves['move_2day_pct'] = ((price_t2 - price_t0) / price_t0) * 100
    if price_t3:
        moves['move_3day_pct'] = ((price_t3 - price_t0) / price_t0) * 100
    if price_t5:
        moves['move_5day_pct'] = ((price_t5 - price_t0) / price_t0) * 100

    # max_intraday from T+1 OHLC
    ohlc = _get_ohlc_on_or_after(symbol, t1)
    if ohlc and ohlc['open_price'] and ohlc['open_price'] > 0:
        op = ohlc['open_price']
        hp = ohlc['high_price'] or op
        lp = ohlc['low_price'] or op
        moves['max_intraday_move_pct'] = max(abs(hp - op), abs(lp - op)) / op * 100

    if moves.get('move_1day_pct') is not None:
        moves['move_direction'] = 'up' if moves['move_1day_pct'] > 0 else 'down'

    return moves


# ============================================================================
# Pass 3: Calculate IV Metrics with Cross-Archive Lookup
# ============================================================================

def pass3_calculate_iv_metrics(db_path, dry_run=False):
    """For moves records missing IV data, look up iv_front_month from
    option_symbol_summary (production first, then sector archives) and compute
    IV metrics."""

    beautiful_log("=== Pass 3: Calculate IV metrics (with cross-archive lookup) ===", level='phase')

    archive_dir = get_sector_archive_dir()
    archive_paths = sorted(archive_dir.glob('*.db')) if archive_dir.exists() else []
    beautiful_log("  {} sector archive databases available".format(len(archive_paths)), level='info')

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get moves in our date range that are missing IV data
    cursor.execute("""
        SELECT move_id, event_id, symbol, earnings_date, move_1day_pct
        FROM earnings_moves
        WHERE earnings_date >= ?
        AND earnings_date <= ?
        AND iv_collapse_pct IS NULL
        ORDER BY earnings_date
    """, (BACKFILL_FROM, BACKFILL_TO))
    eligible = cursor.fetchall()

    beautiful_log("  {} moves records need IV metrics".format(len(eligible)), level='info')

    if not eligible:
        beautiful_log("  Nothing to calculate", level='info')
        conn.close()
        return {'eligible': 0, 'filled': 0, 'no_data': 0, 'archive_hits': 0}

    if dry_run:
        beautiful_log("  [DRY RUN] Would calculate IV for {} records".format(len(eligible)), level='info')
        conn.close()
        return {'eligible': len(eligible), 'filled': 0, 'no_data': 0, 'archive_hits': 0}

    filled = 0
    no_data = 0
    archive_hits = 0

    for i, row in enumerate(eligible, 1):
        symbol = row['symbol']
        earnings_date = row['earnings_date']
        move_id = row['move_id']
        move_1day_pct = row['move_1day_pct']

        # Try to compute IV metrics
        iv_metrics, source = _compute_iv_with_archives(
            cursor, symbol, earnings_date, archive_paths)

        if iv_metrics:
            if source != 'production':
                archive_hits += 1

            # Compute expected move from pre-earnings IV
            expected_move = _compute_expected_move_with_archives(
                cursor, symbol, earnings_date, archive_paths)

            # Compute move_vs_expected
            move_vs_expected = None
            if expected_move and expected_move > 0 and move_1day_pct is not None:
                move_vs_expected = (abs(move_1day_pct) / expected_move) * 100

            clean = clean_database_row({
                'iv_buildup_pct': iv_metrics.get('iv_buildup_pct'),
                'iv_collapse_pct': iv_metrics.get('iv_collapse_pct'),
                'iv_recovery_pct': iv_metrics.get('iv_recovery_pct'),
                'expected_move_pct': expected_move,
                'move_vs_expected_pct': move_vs_expected,
            })

            cursor.execute("""
                UPDATE earnings_moves SET
                    iv_buildup_pct = ?,
                    iv_collapse_pct = ?,
                    iv_recovery_pct = ?,
                    iv_crush_severity = ?,
                    expected_move_pct = ?,
                    move_vs_expected_pct = ?
                WHERE move_id = ?
            """, (
                clean.get('iv_buildup_pct'),
                clean.get('iv_collapse_pct'),
                clean.get('iv_recovery_pct'),
                iv_metrics.get('iv_crush_severity'),
                clean.get('expected_move_pct'),
                clean.get('move_vs_expected_pct'),
                move_id,
            ))
            filled += 1
        else:
            no_data += 1

        if i % 100 == 0:
            conn.commit()
            beautiful_log("  {}/{} processed ({} filled, {} no data, {} archive hits)".format(
                i, len(eligible), filled, no_data, archive_hits), level='info')

    conn.commit()
    conn.close()

    beautiful_log("  IV metrics: {} filled, {} no data, {} from archives".format(
        filled, no_data, archive_hits), level='info')
    return {'eligible': len(eligible), 'filled': filled,
            'no_data': no_data, 'archive_hits': archive_hits}


def _compute_iv_with_archives(cursor, symbol, earnings_date, archive_paths):
    """Compute IV metrics, falling back to sector archives for older data.

    Returns:
        tuple: (metrics_dict, source_label) or ({}, None)
    """
    # Try production first (uses ei_backfill_metrics.compute_iv_metrics)
    metrics = compute_iv_metrics(cursor, symbol, earnings_date)
    if metrics.get('iv_collapse_pct') is not None:
        return metrics, 'production'

    # Fall back to sector archives
    for archive_path in archive_paths:
        try:
            archive_conn = sqlite3.connect(str(archive_path), timeout=10)
            archive_conn.row_factory = sqlite3.Row
            archive_cursor = archive_conn.cursor()

            # Check if option_symbol_summary exists in this archive
            archive_cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='option_symbol_summary'")
            if not archive_cursor.fetchone():
                archive_conn.close()
                continue

            metrics = compute_iv_metrics(archive_cursor, symbol, earnings_date)
            archive_conn.close()

            if metrics.get('iv_collapse_pct') is not None:
                return metrics, archive_path.stem

        except Exception:
            try:
                archive_conn.close()
            except Exception:
                pass
            continue

    return {}, None


def _compute_expected_move_with_archives(cursor, symbol, earnings_date, archive_paths):
    """Compute expected move, falling back to sector archives."""
    # Try production
    result = compute_expected_move(cursor, symbol, earnings_date)
    if result is not None:
        return result

    # Fall back to sector archives
    for archive_path in archive_paths:
        try:
            archive_conn = sqlite3.connect(str(archive_path), timeout=10)
            archive_conn.row_factory = sqlite3.Row
            archive_cursor = archive_conn.cursor()

            archive_cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='option_symbol_summary'")
            if not archive_cursor.fetchone():
                archive_conn.close()
                continue

            result = compute_expected_move(archive_cursor, symbol, earnings_date)
            archive_conn.close()

            if result is not None:
                return result

        except Exception:
            try:
                archive_conn.close()
            except Exception:
                pass
            continue

    return None


# ============================================================================
# Validation Summary
# ============================================================================

def print_validation(db_path):
    """Print before/after validation summary."""
    beautiful_log("=== Validation Report ===", level='phase')

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # earnings_events
    cursor.execute("SELECT COUNT(*) as cnt FROM earnings_events")
    total_events = cursor.fetchone()['cnt']

    cursor.execute("""
        SELECT COUNT(*) as cnt FROM earnings_events
        WHERE earnings_date >= ? AND earnings_date <= ?
    """, (BACKFILL_FROM, BACKFILL_TO))
    dec_feb_events = cursor.fetchone()['cnt']

    cursor.execute("""
        SELECT COUNT(*) as cnt FROM earnings_events
        WHERE earnings_date >= ? AND earnings_date <= ? AND source = 'finnhub_backfill'
    """, (BACKFILL_FROM, BACKFILL_TO))
    backfilled_events = cursor.fetchone()['cnt']

    # earnings_moves
    cursor.execute("SELECT COUNT(*) as cnt FROM earnings_moves")
    total_moves = cursor.fetchone()['cnt']

    cursor.execute("""
        SELECT COUNT(*) as cnt FROM earnings_moves
        WHERE earnings_date >= ? AND earnings_date <= ?
    """, (BACKFILL_FROM, BACKFILL_TO))
    dec_feb_moves = cursor.fetchone()['cnt']

    cursor.execute("""
        SELECT COUNT(*) as cnt FROM earnings_moves
        WHERE earnings_date >= ? AND earnings_date <= ?
        AND move_1day_pct IS NOT NULL
    """, (BACKFILL_FROM, BACKFILL_TO))
    with_price = cursor.fetchone()['cnt']

    cursor.execute("""
        SELECT COUNT(*) as cnt FROM earnings_moves
        WHERE earnings_date >= ? AND earnings_date <= ?
        AND iv_collapse_pct IS NOT NULL
    """, (BACKFILL_FROM, BACKFILL_TO))
    with_iv = cursor.fetchone()['cnt']

    cursor.execute("""
        SELECT COUNT(*) as cnt FROM earnings_moves
        WHERE earnings_date >= ? AND earnings_date <= ?
        AND expected_move_pct IS NOT NULL
    """, (BACKFILL_FROM, BACKFILL_TO))
    with_expected = cursor.fetchone()['cnt']

    conn.close()

    beautiful_log("  earnings_events:", level='info')
    beautiful_log("    Total rows:               {}".format(total_events), level='info')
    beautiful_log("    Dec-Feb rows (all):        {}".format(dec_feb_events), level='info')
    beautiful_log("    Dec-Feb backfilled:        {}".format(backfilled_events), level='info')
    beautiful_log("    Dec-Feb pre-existing:      {}".format(dec_feb_events - backfilled_events), level='info')
    beautiful_log("", level='info')
    beautiful_log("  earnings_moves:", level='info')
    beautiful_log("    Total rows:               {}".format(total_moves), level='info')
    beautiful_log("    Dec-Feb rows:              {}".format(dec_feb_moves), level='info')
    beautiful_log("    With price moves:          {}".format(with_price), level='info')
    beautiful_log("    With IV metrics:           {}".format(with_iv), level='info')
    beautiful_log("    With expected move:        {}".format(with_expected), level='info')

    if dec_feb_events > 0:
        beautiful_log("", level='info')
        beautiful_log("  Coverage:", level='info')
        beautiful_log("    Price move coverage:       {:.1f}%".format(
            with_price / dec_feb_events * 100 if dec_feb_events else 0), level='info')
        beautiful_log("    IV coverage:               {:.1f}%".format(
            with_iv / dec_feb_events * 100 if dec_feb_events else 0), level='info')


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Backfill Dec 2025 - Feb 2026 earnings data')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without database changes')
    parser.add_argument('--pass', type=int, choices=[1, 2, 3], dest='run_pass',
                        help='Run specific pass only (1=events, 2=price_moves, 3=iv_metrics)')
    parser.add_argument('--symbols', type=str,
                        help='Comma-separated subset of symbols')
    parser.add_argument('--verbose', action='store_true',
                        help='Detailed logging')
    parser.add_argument('--no-interaction', action='store_true',
                        help='Run without user prompts')

    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    setup_logging(args.verbose)

    db_path = get_database_path()
    run_pass = args.run_pass

    beautiful_log("Earnings Backfill: Dec 2025 - Feb 2026", level='phase')
    beautiful_log("  Database: {}".format(db_path), level='info')
    beautiful_log("  Date range: {} to {}".format(BACKFILL_FROM, BACKFILL_TO), level='info')
    beautiful_log("  Mode: {}".format('DRY RUN' if args.dry_run else 'LIVE'), level='info')

    if run_pass:
        beautiful_log("  Running pass {} only".format(run_pass), level='info')

    # Determine symbols
    all_symbols = sorted(set(get_specialty_list('klmn_800')) - ETF_EXCLUSIONS)
    if args.symbols:
        subset = [s.strip().upper() for s in args.symbols.split(',')]
        symbols = [s for s in subset if s in set(all_symbols)]
        beautiful_log("  Symbols: {} (subset)".format(len(symbols)), level='info')
    else:
        symbols = all_symbols
        beautiful_log("  Symbols: {} stocks".format(len(symbols)), level='info')

    if not args.no_interaction and not args.dry_run:
        response = input("\nProceed? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Cancelled")
            return 0

    # Print baseline
    beautiful_log("", level='info')
    beautiful_log("--- Before ---", level='info')
    print_validation(db_path)

    # Pass 1: Fetch events
    if run_pass is None or run_pass == 1:
        beautiful_log("", level='info')

        # Load Finnhub API
        config_path = project_root / 'config.json'
        with open(str(config_path), 'r') as f:
            config = json.load(f)
        finnhub_config = config.get('finnhub', {})
        api_key = finnhub_config.get('api_key', '')
        if not api_key:
            logging.error("No Finnhub API key in config.json")
            return 1

        api = FinnhubAPI(
            api_key=api_key,
            base_url=finnhub_config.get('base_url', 'https://finnhub.io/api/v1'),
            rate_limit_per_minute=finnhub_config.get('rate_limit_per_minute', 60),
        )

        pass1_fetch_events(db_path, api, symbols, dry_run=args.dry_run)

    # Pass 2: Price moves
    if run_pass is None or run_pass == 2:
        beautiful_log("", level='info')
        pass2_calculate_price_moves(db_path, dry_run=args.dry_run)

    # Pass 3: IV metrics
    if run_pass is None or run_pass == 3:
        beautiful_log("", level='info')
        pass3_calculate_iv_metrics(db_path, dry_run=args.dry_run)

    # Print results
    beautiful_log("", level='info')
    beautiful_log("--- After ---", level='info')
    print_validation(db_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
