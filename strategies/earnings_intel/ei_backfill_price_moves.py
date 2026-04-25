#!/usr/bin/env python3
"""
Earnings Moves: Price Moves & Date Backfill (ei_backfill_price_moves.py)
------------------------------------------------------------------------
Migration script to populate NULL price move columns and denormalize
earnings_date on the 9,324 existing earnings_moves rows.

Three passes:
  Pass 1: Denormalize earnings_date from production earnings_events (~177 rows)
  Pass 2: Cross-archive denormalization from sector_archive/*.db (~9,147 rows)
  Pass 3: Backfill price moves from historical_prices for rows with earnings_date

Idempotent — safe to re-run. Only updates rows that still have NULLs.

Usage:
    python strategies/earnings_intel/ei_backfill_price_moves.py              # Execute all 3 passes
    python strategies/earnings_intel/ei_backfill_price_moves.py --dry-run    # Preview only
    python strategies/earnings_intel/ei_backfill_price_moves.py --pass 1     # Run specific pass
    python strategies/earnings_intel/ei_backfill_price_moves.py --pass 2     # Cross-archive only
    python strategies/earnings_intel/ei_backfill_price_moves.py --pass 3     # Price moves only

Author: Ben (with Claude)
Date: 2026-02-26
"""

import os
import sys
import sqlite3
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'tools'))

from decimal_formatter import clean_database_row


def get_database_path():
    return project_root / 'data' / 'datalake.db'


def get_sector_archive_dir():
    return project_root / 'data' / 'sector_archive'


def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )


# ============================================================================
# Pass 1: Denormalize earnings_date from production
# ============================================================================

def pass1_production_denormalize(db_path, dry_run=False):
    """Join earnings_moves.event_id → earnings_events.event_id in production.
    UPDATE earnings_moves SET earnings_date where currently NULL."""

    logging.info("=== Pass 1: Denormalize earnings_date from production earnings_events ===")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Ensure column exists
        try:
            cursor.execute('ALTER TABLE earnings_moves ADD COLUMN earnings_date TEXT')
            logging.info("  Added earnings_date column")
        except sqlite3.OperationalError:
            pass

        # Count before
        cursor.execute("SELECT COUNT(*) as c FROM earnings_moves WHERE earnings_date IS NULL")
        null_before = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM earnings_moves")
        total = cursor.fetchone()['c']
        logging.info("  Before: {}/{} rows missing earnings_date".format(null_before, total))

        if dry_run:
            # Preview: how many would match
            cursor.execute("""
                SELECT COUNT(*) as c FROM earnings_moves em
                JOIN earnings_events ee ON em.event_id = ee.event_id
                WHERE em.earnings_date IS NULL
            """)
            match_count = cursor.fetchone()['c']
            logging.info("  [DRY RUN] Would update {} rows from production earnings_events".format(match_count))
            return match_count

        # Execute update
        cursor.execute("""
            UPDATE earnings_moves
            SET earnings_date = (
                SELECT ee.earnings_date FROM earnings_events ee
                WHERE ee.event_id = earnings_moves.event_id
            )
            WHERE earnings_date IS NULL
            AND event_id IN (SELECT event_id FROM earnings_events)
        """)
        updated = cursor.rowcount
        conn.commit()

        cursor.execute("SELECT COUNT(*) as c FROM earnings_moves WHERE earnings_date IS NULL")
        null_after = cursor.fetchone()['c']

        logging.info("  Updated {} rows from production earnings_events".format(updated))
        logging.info("  Remaining NULL: {}/{}".format(null_after, total))

        return updated


# ============================================================================
# Pass 2: Cross-archive denormalization
# ============================================================================

def pass2_cross_archive_denormalize(db_path, dry_run=False):
    """For rows still missing earnings_date: iterate sector archives to find
    earnings_events with matching event_ids."""

    logging.info("=== Pass 2: Cross-archive earnings_date denormalization ===")

    archive_dir = get_sector_archive_dir()
    if not archive_dir.exists():
        logging.warning("  Sector archive directory not found: {}".format(archive_dir))
        return 0

    archive_files = sorted(archive_dir.glob('*.db'))
    if not archive_files:
        logging.warning("  No sector archive databases found")
        return 0

    logging.info("  Found {} sector archives".format(len(archive_files)))

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get event_ids still missing earnings_date
        cursor.execute("""
            SELECT DISTINCT event_id FROM earnings_moves
            WHERE earnings_date IS NULL
        """)
        missing_event_ids = set(row['event_id'] for row in cursor.fetchall())
        logging.info("  {} event_ids still missing earnings_date".format(len(missing_event_ids)))

        if not missing_event_ids:
            logging.info("  Nothing to do — all rows have earnings_date")
            return 0

        total_updated = 0

        for archive_path in archive_files:
            sector_name = archive_path.stem

            try:
                archive_conn = sqlite3.connect(str(archive_path))
                archive_conn.row_factory = sqlite3.Row
                archive_cursor = archive_conn.cursor()

                # Check if earnings_events exists in this archive
                archive_cursor.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='earnings_events'
                """)
                if not archive_cursor.fetchone():
                    archive_conn.close()
                    continue

                # Query for matching event_ids
                # SQLite can't parameterize IN with large lists, so batch it
                matches = {}
                batch_size = 500
                event_id_list = list(missing_event_ids)

                for i in range(0, len(event_id_list), batch_size):
                    batch = event_id_list[i:i + batch_size]
                    placeholders = ','.join('?' * len(batch))
                    archive_cursor.execute("""
                        SELECT event_id, earnings_date FROM earnings_events
                        WHERE event_id IN ({})
                    """.format(placeholders), batch)

                    for row in archive_cursor.fetchall():
                        matches[row['event_id']] = row['earnings_date']

                archive_conn.close()

                if not matches:
                    continue

                if dry_run:
                    logging.info("  [DRY RUN] {}: {} matches".format(sector_name, len(matches)))
                    total_updated += len(matches)
                    continue

                # Apply updates to production
                sector_updated = 0
                for event_id, earnings_date in matches.items():
                    cursor.execute("""
                        UPDATE earnings_moves SET earnings_date = ?
                        WHERE event_id = ? AND earnings_date IS NULL
                    """, (earnings_date, event_id))
                    sector_updated += cursor.rowcount

                conn.commit()
                missing_event_ids -= set(matches.keys())

                if sector_updated > 0:
                    logging.info("  {}: matched {} event_ids, updated {} rows".format(
                        sector_name, len(matches), sector_updated))
                    total_updated += sector_updated

            except Exception as e:
                logging.error("  Error processing {}: {}".format(sector_name, e))

        # Final count
        cursor.execute("SELECT COUNT(*) as c FROM earnings_moves WHERE earnings_date IS NULL")
        still_null = cursor.fetchone()['c']
        logging.info("  Cross-archive total: updated {} rows".format(total_updated))
        logging.info("  Still missing earnings_date: {}".format(still_null))

        return total_updated


# ============================================================================
# Pass 3: Price moves backfill from historical_prices
# ============================================================================

def pass3_price_moves_backfill(db_path, dry_run=False):
    """For rows with earnings_date but NULL move_1day_pct: calculate price
    moves from historical_prices."""

    logging.info("=== Pass 3: Price moves backfill from historical_prices ===")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get eligible rows
        cursor.execute("""
            SELECT move_id, event_id, symbol, earnings_date
            FROM earnings_moves
            WHERE move_1day_pct IS NULL
            AND earnings_date IS NOT NULL
            ORDER BY earnings_date
        """)
        eligible = cursor.fetchall()
        logging.info("  {} rows eligible (have earnings_date, missing price moves)".format(len(eligible)))

        if not eligible:
            logging.info("  Nothing to backfill")
            return 0, 0

        if dry_run:
            logging.info("  [DRY RUN] Would attempt price move calculation for {} rows".format(len(eligible)))
            return len(eligible), 0

        filled = 0
        no_data = 0

        for i, row in enumerate(eligible, 1):
            symbol = row['symbol']
            earnings_date = row['earnings_date']
            move_id = row['move_id']

            moves = _calculate_price_moves(cursor, symbol, earnings_date)

            if moves and moves.get('move_1day_pct') is not None:
                clean = clean_database_row(moves)

                # Also compute move_vs_expected_pct if we have expected_move_pct
                cursor.execute("""
                    SELECT expected_move_pct FROM earnings_moves WHERE move_id = ?
                """, (move_id,))
                em_row = cursor.fetchone()
                move_vs_expected = None
                if em_row and em_row['expected_move_pct'] and em_row['expected_move_pct'] > 0:
                    move_vs_expected = (abs(clean.get('move_1day_pct', 0)) / em_row['expected_move_pct']) * 100
                    move_vs_expected = round(move_vs_expected, 2)

                cursor.execute("""
                    UPDATE earnings_moves SET
                        move_1day_pct = ?,
                        move_2day_pct = ?,
                        move_3day_pct = ?,
                        move_5day_pct = ?,
                        max_intraday_move_pct = ?,
                        move_direction = ?,
                        move_vs_expected_pct = COALESCE(?, move_vs_expected_pct)
                    WHERE move_id = ?
                """, (
                    clean.get('move_1day_pct'),
                    clean.get('move_2day_pct'),
                    clean.get('move_3day_pct'),
                    clean.get('move_5day_pct'),
                    clean.get('max_intraday_move_pct'),
                    clean.get('move_direction'),
                    move_vs_expected,
                    move_id,
                ))
                filled += 1
            else:
                no_data += 1

            if i % 500 == 0:
                conn.commit()
                logging.info("  Progress: {}/{} processed ({} filled, {} no data)".format(
                    i, len(eligible), filled, no_data))

        conn.commit()
        logging.info("  Backfilled price moves for {} of {} eligible rows".format(filled, len(eligible)))
        logging.info("  {} rows had insufficient historical_prices data".format(no_data))

        return filled, no_data


def _calculate_price_moves(cursor, symbol, earnings_date):
    """Calculate price moves from historical_prices for a single event.
    Mirrors PostEarningsCalculator._get_price_moves_from_historical()."""

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
# Validation
# ============================================================================

def validate(db_path):
    """Print before/after summary stats."""

    logging.info("=== Validation Report ===")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as c FROM earnings_moves")
        total = cursor.fetchone()['c']

        cursor.execute("SELECT COUNT(*) as c FROM earnings_moves WHERE earnings_date IS NOT NULL")
        with_date = cursor.fetchone()['c']

        cursor.execute("SELECT COUNT(*) as c FROM earnings_moves WHERE move_1day_pct IS NOT NULL")
        with_1d = cursor.fetchone()['c']

        cursor.execute("SELECT COUNT(*) as c FROM earnings_moves WHERE move_3day_pct IS NOT NULL")
        with_3d = cursor.fetchone()['c']

        cursor.execute("SELECT COUNT(*) as c FROM earnings_moves WHERE move_5day_pct IS NOT NULL")
        with_5d = cursor.fetchone()['c']

        cursor.execute("SELECT COUNT(*) as c FROM earnings_moves WHERE move_vs_expected_pct IS NOT NULL")
        with_vs_exp = cursor.fetchone()['c']

        cursor.execute("SELECT COUNT(*) as c FROM earnings_moves WHERE move_direction IS NOT NULL")
        with_dir = cursor.fetchone()['c']

        logging.info("  Total rows: {}".format(total))
        logging.info("  With earnings_date: {} ({:.1f}%)".format(with_date, with_date / total * 100 if total else 0))
        logging.info("  With move_1day_pct: {} ({:.1f}%)".format(with_1d, with_1d / total * 100 if total else 0))
        logging.info("  With move_3day_pct: {} ({:.1f}%)".format(with_3d, with_3d / total * 100 if total else 0))
        logging.info("  With move_5day_pct: {} ({:.1f}%)".format(with_5d, with_5d / total * 100 if total else 0))
        logging.info("  With move_vs_expected_pct: {} ({:.1f}%)".format(with_vs_exp, with_vs_exp / total * 100 if total else 0))
        logging.info("  With move_direction: {} ({:.1f}%)".format(with_dir, with_dir / total * 100 if total else 0))


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Earnings Moves: Price Moves & Date Backfill')
    parser.add_argument('--dry-run', action='store_true', help='Preview without changes')
    parser.add_argument('--pass', type=int, choices=[1, 2, 3], dest='run_pass',
                       help='Run specific pass only (1=production, 2=archives, 3=price moves)')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')

    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    setup_logging(args.verbose)

    db_path = get_database_path()
    logging.info("Database: {}".format(db_path))
    logging.info("Mode: {}".format("DRY RUN" if args.dry_run else "EXECUTE"))

    # Validate before
    validate(db_path)
    print()

    # Run passes
    if args.run_pass is None or args.run_pass == 1:
        pass1_production_denormalize(db_path, args.dry_run)
        print()

    if args.run_pass is None or args.run_pass == 2:
        pass2_cross_archive_denormalize(db_path, args.dry_run)
        print()

    if args.run_pass is None or args.run_pass == 3:
        pass3_price_moves_backfill(db_path, args.dry_run)
        print()

    # Validate after
    validate(db_path)

    # SA Proposal 016 Part B: refresh derived columns on earnings_events.
    # Anything that recomputes earnings_moves can shift the historical_avg
    # baseline for downstream events. Run unscoped — this script can touch
    # arbitrary symbols.
    if not args.dry_run:
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from tools.backfill_earnings_events_derived import run as refresh_derived
            print()
            print("Refreshing earnings_events derived columns (SA P016 Part B)...")
            result = refresh_derived(db_path=db_path, apply=True, quiet=True)
            print("  events scanned: {}, signal-label changes: {}, applied: {}".format(
                result['total'], result['signal_changed'], result['applied']))
        except Exception as e:
            logging.warning("Derived-column refresh hook failed: {}".format(e))


if __name__ == "__main__":
    main()
