#!/usr/bin/env python3
"""
Earnings Play: Post-Earnings Calculator (ei_post_earnings_calc.py)
------------------------------------------------------------------
Calculate post-earnings metrics for events at T+3 (3 days after earnings).

Calculates:
1. Price Moves: 1day, 2day, 3day, 5day, max_intraday, direction
2. IV Changes: buildup%, collapse%, recovery%, crush_severity
   - Primary source: option_symbol_summary (direct IV lookup)
   - Fallback: earnings_snapshots (if populated)
   - Uses iv_front_month (consistently populated vs iv_30dte which has NULLs)
3. Expected Move: IV-based 1-day expected move at time of earnings
   - NOTE: This is the 1-day expected move for comparison with move_1day_pct.
     Different from expected_move_pct in earnings_upcoming which uses DTE.
4. Move vs Expected: abs(actual_1day_move) / expected_move * 100
   - >100 = moved MORE than expected, <100 = moved LESS
5. Sector Effects: correlation, IV arbitrage, expected moves for peers

Writes to:
- earnings_moves (primary symbol metrics)
- earnings_sector_effects (peer sympathy & arbitrage signals)

Part of: Earnings Intelligence System (PRD 0003)
Author: Ben (with Claude)
Date: 2025-10-10 (IV direct lookup + expected move: 2026-02-10)
"""

import os
import sys
import sqlite3
import logging
import math
from datetime import datetime, timedelta

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

from decimal_formatter import clean_database_row
from log_utils import beautiful_log


def compute_move_vs_historical(actual_abs, hist_pct):
    """Compute (move_vs_historical_pct, signal_accuracy) given actuals + hist baseline.

    Pure helper extracted from EarningsPostCalculator._update_event_outcome so that
    backfills (e.g. tools/backfill_earnings_events_derived.py) can reuse the exact
    production logic instead of re-implementing thresholds and risking drift.

    Args:
        actual_abs: abs(move_1day_pct), or None
        hist_pct: historical_avg_move_pct, or None/0

    Returns:
        tuple (move_vs_historical_pct, signal_accuracy). Both None if inputs incomplete.
    """
    if actual_abs is None or not hist_pct or hist_pct <= 0:
        return (None, None)
    move_vs_historical = (actual_abs / hist_pct) * 100
    if move_vs_historical >= 100:
        signal_accuracy = 'CONFIRMED'
    elif move_vs_historical >= 80:
        signal_accuracy = 'CLOSE'
    elif move_vs_historical >= 60:
        signal_accuracy = 'OVER'
    else:
        signal_accuracy = 'WAY OFF'
    return (move_vs_historical, signal_accuracy)


def compute_straddle_outcome(actual_abs, straddle_pct):
    """Compute (move_vs_straddle_pct, straddle_outcome) given actuals + straddle baseline.

    Pure helper paired with compute_move_vs_historical. Straddle outcome is a trade
    outcome (PROFIT/FLAT/LOSS) — separate from signal_accuracy (CONFIRMED/CLOSE/OVER/WAY OFF)
    which is a signal-quality metric.

    Args:
        actual_abs: abs(move_1day_pct), or None
        straddle_pct: straddle_expected_move_pct, or None/0

    Returns:
        tuple (move_vs_straddle_pct, straddle_outcome). Both None if inputs incomplete.
    """
    if actual_abs is None or not straddle_pct or straddle_pct <= 0:
        return (None, None)
    move_vs_straddle = (actual_abs / straddle_pct) * 100
    if move_vs_straddle >= 110:
        straddle_outcome = 'PROFIT'
    elif move_vs_straddle >= 95:
        straddle_outcome = 'FLAT'
    else:
        straddle_outcome = 'LOSS'
    return (move_vs_straddle, straddle_outcome)


def _migrate_earnings_moves_schema(db_path):
    """Add new columns to earnings_moves if they don't exist (idempotent).

    Migration history:
    - Oct 2025: Original schema (event_id, symbol, move_1/2/3/5day_pct, etc.)
    - Feb 2026: Added earnings_date column
    - Apr 2026: Added OHLC-based peaks, BMO/AMC-aware baseline, expected move
                from snapshots, pre/post earnings swing analysis
    """
    new_columns = [
        ('earnings_date', 'TEXT'),
        # BMO/AMC-aware baseline
        ('pre_earnings_close', 'REAL'),
        # Pre-earnings peaks (T-7 to T-1/T0 depending on BMO/AMC)
        ('pre_earnings_peak_up_pct', 'REAL'),
        ('pre_earnings_peak_down_pct', 'REAL'),
        ('pre_earnings_peak_up_day', 'INTEGER'),
        ('pre_earnings_peak_down_day', 'INTEGER'),
        ('pre_earnings_swing_pct', 'REAL'),
        # Post-earnings peaks (T0/T+1 to T+5 depending on BMO/AMC)
        ('post_earnings_peak_up_pct', 'REAL'),
        ('post_earnings_peak_down_pct', 'REAL'),
        ('post_earnings_peak_up_day', 'INTEGER'),
        ('post_earnings_peak_down_day', 'INTEGER'),
        ('post_earnings_swing_pct', 'REAL'),
        # Full window
        ('total_swing_pct', 'REAL'),
        # Expected move from straddle (captured in snapshots)
        ('expected_move_entry_pct', 'REAL'),
        ('expected_move_final_pct', 'REAL'),
    ]

    try:
        with sqlite3.connect(db_path, timeout=30) as conn:
            conn.execute("PRAGMA busy_timeout = 30000")
            cursor = conn.cursor()
            for col_name, col_type in new_columns:
                try:
                    cursor.execute('ALTER TABLE earnings_moves ADD COLUMN {} {}'.format(
                        col_name, col_type))
                    logging.info("Added column earnings_moves.{}".format(col_name))
                except sqlite3.OperationalError as e:
                    if 'duplicate column' not in str(e).lower():
                        raise
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_em_earnings_date ON earnings_moves(earnings_date)')
            conn.commit()
    except Exception as e:
        logging.warning("earnings_moves schema migration: {}".format(e))


def _migrate_earnings_events_outcome_columns(db_path):
    """Add denormalized outcome columns to earnings_events (idempotent).

    These provide at-a-glance historical view without JOINing earnings_moves.
    Written back after post-earnings calculation completes.

    Migration: Apr 2026
    """
    outcome_columns = [
        ('actual_move_1day_pct', 'REAL'),
        ('actual_max_move_pct', 'REAL'),
        ('move_vs_expected_pct', 'REAL'),
        ('iv_collapse_pct', 'REAL'),
        ('outcome_updated_at', 'TEXT'),
        ('move_vs_straddle_pct', 'REAL'),
        ('move_vs_historical_pct', 'REAL'),
        ('straddle_outcome', 'TEXT'),
        ('signal_accuracy', 'TEXT'),
        # SA Proposal 015: peak-exit outcome (mirrors *_pct/*outcome above
        # but uses actual_max_move_pct instead of actual_move_1day_pct).
        # Enables native peak-exit signal calibration.
        ('move_vs_straddle_max_pct', 'REAL'),
        ('straddle_outcome_max', 'TEXT'),
    ]

    try:
        with sqlite3.connect(db_path, timeout=30) as conn:
            conn.execute("PRAGMA busy_timeout = 30000")
            cursor = conn.cursor()
            for col_name, col_type in outcome_columns:
                try:
                    cursor.execute('ALTER TABLE earnings_events ADD COLUMN {} {}'.format(
                        col_name, col_type))
                    logging.info("Added column earnings_events.{}".format(col_name))
                except sqlite3.OperationalError as e:
                    if 'duplicate column' not in str(e).lower():
                        raise
            conn.commit()
    except Exception as e:
        logging.warning("earnings_events outcome migration: {}".format(e))


class PostEarningsCalculator:
    """Calculate post-earnings metrics for completed earnings events"""

    def __init__(self, db_path=None):
        """Initialize calculator

        Args:
            db_path: Path to database (default: data/datalake.db)
        """
        if not db_path:
            db_path = os.path.join(project_root, 'data', 'datalake.db')

        self.db_path = db_path

        # Ensure schema is up to date
        _migrate_earnings_moves_schema(db_path)
        _migrate_earnings_events_outcome_columns(db_path)

        # Statistics tracking
        self.stats = {
            'trade_date': None,
            'events_ready': 0,
            'moves_calculated': 0,
            'sector_effects_calculated': 0,
            'errors': 0
        }

        # Symbols whose earnings_moves rows were touched this run.
        # SA Proposal 016 Part B: refresh derived columns on earnings_events
        # for these symbols at end of run so historical_avg_move_pct cascade
        # stays in sync with the new earnings_moves data.
        self.touched_symbols = set()

        logging.debug("Post-earnings calculator initialized")

    def recalculate_all(self, trade_date=None):
        """Recalculate metrics for ALL events in the T+3 to T+10 window,
        ignoring existing rows. Used to backfill after schema changes.

        Args:
            trade_date: Current trade date (default: latest from option_symbol_summary)

        Returns:
            dict: Calculation statistics
        """
        return self.calculate_post_earnings_metrics(
            trade_date=trade_date, force_recalculate=True)

    def backfill_event_outcomes(self):
        """Backfill earnings_events outcome columns from existing earnings_moves data.

        One-time operation to populate denormalized outcome columns for events
        that already have earnings_moves rows but lack outcome data.

        Returns:
            int: Number of events updated
        """
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute("PRAGMA busy_timeout = 30000")
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE earnings_events
                    SET actual_move_1day_pct = (
                            SELECT em.move_1day_pct FROM earnings_moves em
                            WHERE em.event_id = earnings_events.event_id),
                        actual_max_move_pct = (
                            SELECT em.max_intraday_move_pct FROM earnings_moves em
                            WHERE em.event_id = earnings_events.event_id),
                        move_vs_expected_pct = (
                            SELECT em.move_vs_expected_pct FROM earnings_moves em
                            WHERE em.event_id = earnings_events.event_id),
                        iv_collapse_pct = (
                            SELECT em.iv_collapse_pct FROM earnings_moves em
                            WHERE em.event_id = earnings_events.event_id),
                        outcome_updated_at = DATETIME('now')
                    WHERE EXISTS (
                        SELECT 1 FROM earnings_moves em
                        WHERE em.event_id = earnings_events.event_id
                    )
                    AND actual_move_1day_pct IS NULL
                """)
                updated = cursor.rowcount
                conn.commit()
                logging.info("Backfilled outcome data for {} earnings_events".format(updated))
                return updated
        except Exception as e:
            logging.error("Backfill event outcomes failed: {}".format(e))
            return 0

    def calculate_post_earnings_metrics(self, trade_date=None, force_recalculate=False):
        """Calculate metrics for events at T+3 (3 days after earnings)

        Args:
            trade_date: Current trade date (default: latest from option_symbol_summary)
            force_recalculate: If True, reprocess all events even if they have existing rows

        Returns:
            dict: Calculation statistics
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Step 1: Determine trade date
                if not trade_date:
                    trade_date = self._get_latest_trade_date(cursor)

                if not trade_date:
                    logging.error("No trade date available")
                    self.stats['errors'] += 1
                    return self.stats

                self.stats['trade_date'] = trade_date
                logging.debug("Calculating post-earnings metrics for trade date: {}".format(trade_date))

                # Step 2: Find events at T+3 (3 days after earnings)
                events_at_t3 = self._get_events_at_t3(
                    cursor, trade_date, force_recalculate=force_recalculate)

                if not events_at_t3:
                    logging.debug("No events at T+3 ready for calculation")
                    return self.stats

                self.stats['events_ready'] = len(events_at_t3)
                beautiful_log("Found {} events at T+3 ready for calculation".format(len(events_at_t3)), 'info')

                # Step 3: Calculate metrics for each event
                for event in events_at_t3:
                    self._calculate_event_metrics(cursor, event)

                conn.commit()

                # Step 4 (SA Proposal 016 Part B): refresh derived columns on
                # earnings_events for any symbol whose earnings_moves was just
                # written. Adding/recomputing a row shifts the recent-6Q hist
                # baseline for that symbol's other (later-dated) events, so
                # cascade columns (relative_underpricing_pct, earnings_play_signal,
                # move_vs_historical_pct, signal_accuracy) need a refresh.
                if self.touched_symbols:
                    try:
                        from tools.backfill_earnings_events_derived import run as refresh_derived
                        refresh_derived(
                            db_path=self.db_path,
                            symbols=sorted(self.touched_symbols),
                            apply=True,
                            quiet=True,
                        )
                    except Exception as e:
                        logging.warning("Derived-column refresh hook failed: {}".format(e))

                return self.stats

        except Exception as e:
            logging.error("Post-earnings calculation failed: {}".format(e))
            import traceback
            traceback.print_exc()
            self.stats['errors'] += 1
            return self.stats

    def _get_latest_trade_date(self, cursor):
        """Get the latest trade date from option_symbol_summary

        Args:
            cursor: Database cursor

        Returns:
            str: Latest trade date (YYYY-MM-DD) or None
        """
        query = "SELECT MAX(trade_date) as latest_date FROM option_symbol_summary"
        cursor.execute(query)
        row = cursor.fetchone()

        return row['latest_date'] if row and row['latest_date'] else None

    def _get_events_at_t3(self, cursor, trade_date, force_recalculate=False):
        """Get events ready for post-earnings calculation (T+3 or later).

        Finds earnings events where at least 3 calendar days have passed
        (enough for price/IV to settle) AND no earnings_moves row exists yet.
        This handles weekend gaps: Wednesday/Thursday earnings have T+3 on
        Sat/Sun, so the system picks them up on the next trading day (Monday).

        The NOT EXISTS check prevents reprocessing — once calculated, an event
        is never re-triggered. Uses INSERT OR REPLACE downstream as a safety
        net, but this query avoids unnecessary recalculation and log noise.

        Upper bound of 10 days prevents processing ancient events that were
        somehow missed; those should use the backfill scripts instead.

        Args:
            cursor: Database cursor
            trade_date: Current trade date
            force_recalculate: If True, skip NOT EXISTS check (reprocess all)

        Returns:
            list: Events ready for calculation
        """
        if force_recalculate:
            query = """
            SELECT ee.event_id, ee.symbol, ee.earnings_date
            FROM earnings_events ee
            WHERE JULIANDAY(?) - JULIANDAY(ee.earnings_date) BETWEEN 3 AND 10
            ORDER BY ee.symbol
            """
        else:
            query = """
            SELECT ee.event_id, ee.symbol, ee.earnings_date
            FROM earnings_events ee
            WHERE JULIANDAY(?) - JULIANDAY(ee.earnings_date) BETWEEN 3 AND 10
              AND NOT EXISTS (
                  SELECT 1 FROM earnings_moves em
                  WHERE em.event_id = ee.event_id
                    AND em.iv_collapse_pct IS NOT NULL
              )
            ORDER BY ee.symbol
            """

        cursor.execute(query, (trade_date,))
        return cursor.fetchall()

    def _calculate_event_metrics(self, cursor, event):
        """Calculate all metrics for a single event

        Args:
            cursor: Database cursor
            event: Event record (event_id, symbol, earnings_date)
        """
        event_id = event['event_id']
        symbol = event['symbol']
        earnings_date = event['earnings_date']

        logging.info("Calculating metrics for {} (earnings: {})".format(symbol, earnings_date))

        try:
            # Step 1: Calculate price moves (snapshots primary, historical_prices fallback)
            moves_data = self._calculate_price_moves(cursor, event_id, symbol, earnings_date)
            if not moves_data:
                moves_data = self._get_price_moves_from_historical(cursor, symbol, earnings_date)
                if moves_data:
                    logging.info("  Price moves from historical_prices fallback")
                else:
                    logging.warning("  No price data available for {} (snapshots or historical)".format(symbol))
            else:
                logging.debug("  Price moves from earnings_snapshots")

            # Step 2: Calculate IV changes
            # Try earnings_snapshots first (canonical source), fall back to direct OS lookup
            iv_data = self._calculate_iv_changes(cursor, event_id, symbol, earnings_date)
            if not iv_data:
                # Bypass empty earnings_snapshots — query option_symbol_summary directly
                iv_data = self._get_iv_from_option_summary(cursor, symbol, earnings_date)

            # Step 3: Expected move — prefer straddle from snapshots, fall back to IV
            # Use entry value (T-7) for move_vs_expected since that's when the trade
            # thesis existed. Final value (T-1/T0) stored separately for comparison.
            expected_move_pct = moves_data.get('expected_move_entry_pct')
            if not expected_move_pct:
                # Fallback: try reading from earnings_upcoming (may still have right date)
                cursor.execute("""
                    SELECT straddle_expected_move_pct FROM earnings_upcoming
                    WHERE symbol = ? AND earnings_date = ?
                """, (symbol, earnings_date))
                eu_row = cursor.fetchone()
                if eu_row and eu_row['straddle_expected_move_pct']:
                    expected_move_pct = eu_row['straddle_expected_move_pct']
                else:
                    # Last resort: IV-based reconstruction
                    expected_move_pct = self._get_expected_move_at_earnings(
                        cursor, symbol, earnings_date)

            # Step 4: Calculate move vs expected (using entry expected move)
            move_vs_expected_pct = None
            move_1day = moves_data.get('move_1day_pct')
            if expected_move_pct and expected_move_pct > 0 and move_1day is not None:
                # >100 means moved MORE than expected, <100 means moved LESS
                move_vs_expected_pct = (abs(move_1day) / expected_move_pct) * 100

            # Step 5: Merge and insert into earnings_moves
            moves_record = {**moves_data, **iv_data}
            moves_record['event_id'] = event_id
            moves_record['symbol'] = symbol
            moves_record['earnings_date'] = earnings_date
            moves_record['expected_move_pct'] = expected_move_pct
            moves_record['move_vs_expected_pct'] = move_vs_expected_pct
            moves_record['calculated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            self._insert_earnings_move(cursor, moves_record)
            self.stats['moves_calculated'] += 1
            self.touched_symbols.add(symbol)

            # Step 6: Calculate sector effects for peers
            # Pass iv_data so sector effects can access primary_iv_buildup_pct correctly
            self._calculate_sector_effects(cursor, event_id, symbol, earnings_date, moves_data, iv_data)

            # Step 7: Write outcome summary back to earnings_events
            self._update_event_outcome(cursor, event_id, moves_record)

        except Exception as e:
            logging.error("Error calculating metrics for {}: {}".format(symbol, e))
            self.stats['errors'] += 1

    def _calculate_price_moves(self, cursor, event_id, symbol, earnings_date):
        """Calculate price moves from earnings_snapshots using OHLC data.

        BMO/AMC-aware baseline:
        - BMO: baseline = T(-1) close, post-earnings starts at T0
        - AMC: baseline = T0 close, post-earnings starts at T+1
        - Unknown: treated as BMO (T(-1) close — safer, doesn't miss gap)

        Computes:
        - move_1/2/3day_pct: close-to-close relative to baseline
        - Pre-earnings peaks/swing from OHLC in pre-earnings window
        - Post-earnings peaks/swing from OHLC in post-earnings window
        - Total swing across full window
        - max_intraday_move_pct: biggest post-earnings reaction from baseline

        Args:
            cursor: Database cursor
            event_id: Event ID (unused, kept for signature compatibility)
            symbol: Symbol
            earnings_date: Earnings date

        Returns:
            dict: Price move metrics (empty if insufficient data)
        """
        # Get OHLC snapshots for primary symbol
        query = """
        SELECT days_from_earnings, open_price, high_price, low_price, close_price,
               straddle_expected_move_pct
        FROM earnings_snapshots
        WHERE earnings_date = ? AND symbol = ? AND is_primary_symbol = TRUE
        ORDER BY days_from_earnings
        """
        cursor.execute(query, (earnings_date, symbol))
        snapshots = cursor.fetchall()

        if not snapshots:
            logging.warning("No snapshots found for {}".format(symbol))
            return {}

        # Determine BMO/AMC for baseline
        cursor.execute("""
            SELECT earnings_time FROM earnings_events
            WHERE symbol = ? AND earnings_date = ?
        """, (symbol, earnings_date))
        time_row = cursor.fetchone()
        earnings_time = time_row['earnings_time'] if time_row else None
        is_amc = earnings_time and earnings_time.lower() == 'amc'

        # Build maps: days_from_earnings -> values
        close_map = {}
        high_map = {}
        low_map = {}
        expected_move_map = {}
        for s in snapshots:
            d = s['days_from_earnings']
            if s['close_price']:
                close_map[d] = s['close_price']
            if s['high_price']:
                high_map[d] = s['high_price']
            if s['low_price']:
                low_map[d] = s['low_price']
            if s['straddle_expected_move_pct']:
                expected_move_map[d] = s['straddle_expected_move_pct']

        # Determine baseline (pre-earnings close)
        if is_amc:
            baseline = close_map.get(0)  # AMC: T0 close is pre-earnings
            post_start = 1  # Reaction starts T+1
        else:
            baseline = close_map.get(-1)  # BMO/unknown: T(-1) close
            post_start = 0  # Reaction starts T0

        if not baseline:
            logging.warning("No baseline close for {} (BMO/AMC={})".format(
                symbol, earnings_time or 'unknown'))
            return {}

        moves = {'pre_earnings_close': baseline}

        # --- Close-to-close moves relative to baseline ---
        # move_Nday = Nth day after reaction starts
        for n, label in [(1, 'move_1day_pct'), (2, 'move_2day_pct'),
                          (3, 'move_3day_pct'), (5, 'move_5day_pct')]:
            day = post_start + n - 1  # reaction day 1 = post_start
            close_n = close_map.get(day)
            if close_n:
                moves[label] = ((close_n - baseline) / baseline) * 100

        # Direction from 1-day move
        if moves.get('move_1day_pct') is not None:
            moves['move_direction'] = 'up' if moves['move_1day_pct'] > 0 else 'down'

        # No close-to-close moves at all — let fallback handle it
        if not any(k.startswith('move_') and k.endswith('_pct') for k in moves
                   if k not in ('pre_earnings_close',)):
            return {}

        # --- Pre-earnings peaks from OHLC ---
        pre_end = 0 if is_amc else -1  # Last pre-earnings day (inclusive)
        pre_highs = [(d, high_map[d]) for d in high_map if d >= -7 and d <= pre_end]
        pre_lows = [(d, low_map[d]) for d in low_map if d >= -7 and d <= pre_end]

        if pre_highs:
            peak_day, peak_val = max(pre_highs, key=lambda x: x[1])
            moves['pre_earnings_peak_up_pct'] = ((peak_val - baseline) / baseline) * 100
            moves['pre_earnings_peak_up_day'] = peak_day

        if pre_lows:
            trough_day, trough_val = min(pre_lows, key=lambda x: x[1])
            moves['pre_earnings_peak_down_pct'] = ((trough_val - baseline) / baseline) * 100
            moves['pre_earnings_peak_down_day'] = trough_day

        if 'pre_earnings_peak_up_pct' in moves and 'pre_earnings_peak_down_pct' in moves:
            # Signed: positive = up-dominant, negative = down-dominant
            moves['pre_earnings_swing_pct'] = (
                moves['pre_earnings_peak_up_pct'] + moves['pre_earnings_peak_down_pct'])

        # --- Post-earnings peaks from OHLC ---
        post_highs = [(d, high_map[d]) for d in high_map if d >= post_start and d <= 5]
        post_lows = [(d, low_map[d]) for d in low_map if d >= post_start and d <= 5]

        if post_highs:
            peak_day, peak_val = max(post_highs, key=lambda x: x[1])
            moves['post_earnings_peak_up_pct'] = ((peak_val - baseline) / baseline) * 100
            moves['post_earnings_peak_up_day'] = peak_day

        if post_lows:
            trough_day, trough_val = min(post_lows, key=lambda x: x[1])
            moves['post_earnings_peak_down_pct'] = ((trough_val - baseline) / baseline) * 100
            moves['post_earnings_peak_down_day'] = trough_day

        if 'post_earnings_peak_up_pct' in moves and 'post_earnings_peak_down_pct' in moves:
            moves['post_earnings_swing_pct'] = (
                moves['post_earnings_peak_up_pct'] + moves['post_earnings_peak_down_pct'])

        # --- max_intraday_move_pct: biggest post-earnings reaction from baseline ---
        post_peaks = [v for k, v in moves.items()
                      if k in ('post_earnings_peak_up_pct', 'post_earnings_peak_down_pct')
                      and v is not None]
        if post_peaks:
            moves['max_intraday_move_pct'] = max(post_peaks, key=abs)

        # --- Total swing across full window (T-7 to T+5) ---
        all_highs = [v for v in high_map.values()]
        all_lows = [v for v in low_map.values()]
        if all_highs and all_lows and baseline:
            window_peak_up = ((max(all_highs) - baseline) / baseline) * 100
            window_peak_down = ((min(all_lows) - baseline) / baseline) * 100
            moves['total_swing_pct'] = window_peak_up + window_peak_down

        # --- Expected move from snapshots ---
        # Entry: earliest available (T-7 ideally)
        if expected_move_map:
            earliest_day = min(expected_move_map.keys())
            moves['expected_move_entry_pct'] = expected_move_map[earliest_day]
            # Final: closest to pre-earnings boundary
            final_day = max(d for d in expected_move_map if d <= pre_end) if \
                any(d <= pre_end for d in expected_move_map) else earliest_day
            moves['expected_move_final_pct'] = expected_move_map[final_day]

        return moves

    def _get_price_moves_from_historical(self, cursor, symbol, earnings_date):
        """Fallback: calculate price moves from historical_prices table.

        Used when earnings_snapshots has no data (pre-2026 events).
        BMO/AMC-aware: uses T(-1) close as baseline for BMO/unknown,
        T0 close for AMC.

        Args:
            cursor: Database cursor
            symbol: Stock symbol
            earnings_date: Earnings date string (YYYY-MM-DD)

        Returns:
            dict: Price move metrics matching _calculate_price_moves() format,
                  or empty dict if insufficient data
        """
        def _get_close_on_or_before(target_date):
            cursor.execute("""
                SELECT close_price FROM historical_prices
                WHERE symbol = ? AND trade_date <= ?
                ORDER BY trade_date DESC LIMIT 1
            """, (symbol, target_date))
            row = cursor.fetchone()
            return row['close_price'] if row else None

        def _get_close_on_or_after(target_date):
            cursor.execute("""
                SELECT close_price FROM historical_prices
                WHERE symbol = ? AND trade_date >= ?
                ORDER BY trade_date ASC LIMIT 1
            """, (symbol, target_date))
            row = cursor.fetchone()
            return row['close_price'] if row else None

        def _get_ohlc_on_or_after(target_date):
            cursor.execute("""
                SELECT open_price, high_price, low_price, close_price FROM historical_prices
                WHERE symbol = ? AND trade_date >= ?
                ORDER BY trade_date ASC LIMIT 1
            """, (symbol, target_date))
            return cursor.fetchone()

        # Determine BMO/AMC
        cursor.execute("""
            SELECT earnings_time FROM earnings_events
            WHERE symbol = ? AND earnings_date = ?
        """, (symbol, earnings_date))
        time_row = cursor.fetchone()
        earnings_time = time_row['earnings_time'] if time_row else None
        is_amc = earnings_time and earnings_time.lower() == 'amc'

        earnings_dt = datetime.strptime(earnings_date, '%Y-%m-%d')
        t_minus_1 = (earnings_dt - timedelta(days=1)).strftime('%Y-%m-%d')

        # Baseline: T(-1) for BMO/unknown, T0 for AMC
        if is_amc:
            baseline = _get_close_on_or_after(earnings_date)
            post_start_date = (earnings_dt + timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            baseline = _get_close_on_or_before(t_minus_1)
            post_start_date = earnings_date

        if not baseline:
            return {}

        moves = {'pre_earnings_close': baseline}

        # Close-to-close moves from baseline
        for n_days, label in [(1, 'move_1day_pct'), (2, 'move_2day_pct'),
                               (3, 'move_3day_pct'), (5, 'move_5day_pct')]:
            offset = (datetime.strptime(post_start_date, '%Y-%m-%d') +
                      timedelta(days=n_days - 1))
            close_n = _get_close_on_or_after(offset.strftime('%Y-%m-%d'))
            if close_n:
                moves[label] = ((close_n - baseline) / baseline) * 100

        # max_intraday_move_pct from post-earnings OHLC
        ohlc_t1 = _get_ohlc_on_or_after(post_start_date)
        if ohlc_t1 and baseline > 0:
            high_p = ohlc_t1['high_price']
            low_p = ohlc_t1['low_price']
            peaks = []
            if high_p:
                peaks.append(((high_p - baseline) / baseline) * 100)
            if low_p:
                peaks.append(((low_p - baseline) / baseline) * 100)
            if peaks:
                moves['max_intraday_move_pct'] = max(peaks, key=abs)
                moves['post_earnings_peak_up_pct'] = max(peaks)
                moves['post_earnings_peak_down_pct'] = min(peaks)

        # Direction
        if moves.get('move_1day_pct') is not None:
            moves['move_direction'] = 'up' if moves['move_1day_pct'] > 0 else 'down'

        return moves

    def _calculate_iv_changes(self, cursor, event_id, symbol, earnings_date):
        """Calculate IV changes from earnings_snapshots

        Args:
            cursor: Database cursor
            event_id: Event ID
            symbol: Symbol
            earnings_date: Earnings date

        Returns:
            dict: IV change metrics
        """
        # Get snapshots for primary symbol
        # Uses earnings_date (not event_id) — see _calculate_price_moves comment
        query = """
        SELECT snapshot_date, days_from_earnings, iv_30dte
        FROM earnings_snapshots
        WHERE earnings_date = ? AND symbol = ? AND is_primary_symbol = TRUE
        ORDER BY days_from_earnings
        """

        cursor.execute(query, (earnings_date, symbol))
        snapshots = cursor.fetchall()

        if not snapshots:
            return {}

        # Build IV map: days_from_earnings -> iv_30dte
        iv_map = {s['days_from_earnings']: s['iv_30dte'] for s in snapshots if s['iv_30dte']}

        # Get IV at key points — use fuzzy matching for post-earnings days
        # because exact day offsets skip weekends (e.g. Friday earnings has no
        # T+1 snapshot — next trading day is Monday = T+3 calendar days)
        positive_days = sorted(k for k in iv_map if k > 0)
        iv_at_t_minus_7 = iv_map.get(-7)  # 7 days before earnings
        iv_at_t_minus_1 = iv_map.get(-1)  # 1 day before earnings
        iv_at_t0 = iv_map.get(0)          # Day of earnings
        # First available post-earnings snapshot (T+1 weekday, T+3 Friday)
        iv_at_t_post = iv_map[positive_days[0]] if positive_days else None
        # Second available post-earnings snapshot for recovery calc
        iv_at_t_post2 = iv_map[positive_days[1]] if len(positive_days) >= 2 else None

        # Calculate IV metrics
        iv_metrics = {}

        # IV Buildup: T-7 to T-1 (how much IV increased before earnings)
        if iv_at_t_minus_7 and iv_at_t_minus_1:
            iv_metrics['iv_buildup_pct'] = ((iv_at_t_minus_1 - iv_at_t_minus_7) / iv_at_t_minus_7) * 100

        # IV Collapse: T-1 to first post-earnings day
        if iv_at_t_minus_1 and iv_at_t_post:
            iv_metrics['iv_collapse_pct'] = ((iv_at_t_post - iv_at_t_minus_1) / iv_at_t_minus_1) * 100

        # IV Recovery: first to second post-earnings day
        if iv_at_t_post and iv_at_t_post2:
            iv_metrics['iv_recovery_pct'] = ((iv_at_t_post2 - iv_at_t_post) / iv_at_t_post) * 100

        # IV Crush Severity (5-tier scale centered around ~45% typical post-earnings crush)
        if iv_metrics.get('iv_collapse_pct'):
            collapse = abs(iv_metrics['iv_collapse_pct'])
            if collapse > 65:
                iv_metrics['iv_crush_severity'] = 'severe'
            elif collapse >= 50:
                iv_metrics['iv_crush_severity'] = 'high'
            elif collapse >= 40:
                iv_metrics['iv_crush_severity'] = 'normal'
            elif collapse >= 25:
                iv_metrics['iv_crush_severity'] = 'mild'
            else:
                iv_metrics['iv_crush_severity'] = 'minimal'

        return iv_metrics

    def _get_iv_from_option_summary(self, cursor, symbol, earnings_date):
        """Get IV data points directly from option_symbol_summary.

        Bypasses earnings_snapshots (which may be empty) by querying
        option_symbol_summary directly for IV at key dates around earnings.

        Uses iv_front_month (7-21 DTE bucket) because it's consistently
        populated across all symbols, unlike iv_30dte which has many NULLs.

        Args:
            cursor: Database cursor
            symbol: Stock symbol
            earnings_date: Earnings date string (YYYY-MM-DD)

        Returns:
            dict: IV metrics (iv_buildup_pct, iv_collapse_pct, iv_recovery_pct,
                  iv_crush_severity) or empty dict if insufficient data
        """
        def _get_iv_at_date(cursor, symbol, date_expr, direction):
            """Helper to get iv_front_month near a target date.

            Args:
                direction: 'before' = last trading day <= target,
                          'after' = first trading day >= target
            """
            if direction == 'before':
                query = """
                    SELECT iv_front_month, trade_date FROM option_symbol_summary
                    WHERE symbol = ? AND trade_date < ?
                    AND iv_front_month IS NOT NULL AND iv_front_month > 0
                    ORDER BY trade_date DESC LIMIT 1
                """
            else:  # after
                query = """
                    SELECT iv_front_month, trade_date FROM option_symbol_summary
                    WHERE symbol = ? AND trade_date > ?
                    AND iv_front_month IS NOT NULL AND iv_front_month > 0
                    ORDER BY trade_date ASC LIMIT 1
                """
            cursor.execute(query, (symbol, date_expr))
            row = cursor.fetchone()
            return (row['iv_front_month'], row['trade_date']) if row else (None, None)

        # Get IV at 4 key points around earnings
        # T-7: ~7 calendar days before (use -5 to account for weekends)
        iv_t7, _ = _get_iv_at_date(cursor, symbol,
            "{:%Y-%m-%d}".format(datetime.strptime(earnings_date, '%Y-%m-%d') - timedelta(days=5)),
            'before')

        # T-1: last trading day before earnings
        iv_t1_before, _ = _get_iv_at_date(cursor, symbol, earnings_date, 'before')

        # T+1: first trading day after earnings
        iv_t1_after, _ = _get_iv_at_date(cursor, symbol, earnings_date, 'after')

        # T+3: ~3 trading days after earnings
        t_plus_3 = "{:%Y-%m-%d}".format(datetime.strptime(earnings_date, '%Y-%m-%d') + timedelta(days=3))
        iv_t3, _ = _get_iv_at_date(cursor, symbol, t_plus_3, 'after')

        iv_metrics = {}

        # IV Buildup: T-7 to T-1
        if iv_t7 and iv_t1_before:
            iv_metrics['iv_buildup_pct'] = ((iv_t1_before - iv_t7) / iv_t7) * 100

        # IV Collapse: T-1 to T+1
        if iv_t1_before and iv_t1_after:
            iv_metrics['iv_collapse_pct'] = ((iv_t1_after - iv_t1_before) / iv_t1_before) * 100

        # IV Recovery: T+1 to T+3
        if iv_t1_after and iv_t3:
            iv_metrics['iv_recovery_pct'] = ((iv_t3 - iv_t1_after) / iv_t1_after) * 100

        # IV Crush Severity (5-tier scale centered around ~45% typical post-earnings crush)
        if iv_metrics.get('iv_collapse_pct') is not None:
            collapse = abs(iv_metrics['iv_collapse_pct'])
            if collapse > 65:
                iv_metrics['iv_crush_severity'] = 'severe'
            elif collapse >= 50:
                iv_metrics['iv_crush_severity'] = 'high'
            elif collapse >= 40:
                iv_metrics['iv_crush_severity'] = 'normal'
            elif collapse >= 25:
                iv_metrics['iv_crush_severity'] = 'mild'
            else:
                iv_metrics['iv_crush_severity'] = 'minimal'

        if iv_metrics:
            logging.debug("  IV from option_summary for {}: buildup={}, collapse={}, severity={}".format(
                symbol,
                "{:.1f}%".format(iv_metrics['iv_buildup_pct']) if 'iv_buildup_pct' in iv_metrics else 'N/A',
                "{:.1f}%".format(iv_metrics['iv_collapse_pct']) if 'iv_collapse_pct' in iv_metrics else 'N/A',
                iv_metrics.get('iv_crush_severity', 'N/A')
            ))

        return iv_metrics

    def _get_expected_move_at_earnings(self, cursor, symbol, earnings_date):
        """Calculate what the expected move was at the time of earnings.

        Uses pre-earnings IV (day before) to compute the theoretical 1-day
        expected move. This is the 1-day expected move for comparison with
        move_1day_pct — different from the DTE-based expected_move_pct
        in earnings_upcoming.

        Lookup falls back from production DB → sector archive when production
        has no qualifying IV row. This matters because option_symbol_summary
        is Tier 2 (30-day MOVE) of the sector archive system: rows older than
        ~30 days are moved out of datalake.db into per-sector archive files.
        Without the archive fallback, expected_move_pct would be NULL for
        every event older than the rolling window — even though the IV
        history exists, just elsewhere.

        Args:
            cursor: Database cursor (against production datalake.db)
            symbol: Stock symbol
            earnings_date: Earnings date string (YYYY-MM-DD)

        Returns:
            float: Expected 1-day move percentage, or None
        """
        iv_before = self._get_iv_before_earnings(cursor, symbol, earnings_date)
        if iv_before is None:
            return None

        # 1-day expected move: IV * sqrt(1/365) * 100
        return iv_before * math.sqrt(1.0 / 365.0) * 100

    def _get_iv_before_earnings(self, cursor, symbol, earnings_date):
        """Find iv_front_month on the last trading day before earnings.

        Tries production DB first (~30-day rolling window), then the symbol's
        sector archive (~9 months back, depending on when the symbol joined).

        Args:
            cursor: Cursor against production datalake.db (used for the
                first query and to look up the archive_db assignment)
            symbol: Stock ticker
            earnings_date: YYYY-MM-DD

        Returns:
            float iv (decimal, e.g. 0.85 for 85%), or None
        """
        # Try production first (rolling 30-day window covers recent events)
        cursor.execute("""
            SELECT iv_front_month FROM option_symbol_summary
            WHERE symbol = ? AND trade_date < ?
            AND iv_front_month IS NOT NULL AND iv_front_month > 0
            ORDER BY trade_date DESC LIMIT 1
        """, (symbol, earnings_date))
        row = cursor.fetchone()
        if row and row['iv_front_month']:
            return row['iv_front_month']

        # Fallback to sector archive
        cursor.execute("SELECT archive_db FROM symbol_metadata WHERE symbol = ?", (symbol,))
        meta = cursor.fetchone()
        if not meta or not meta['archive_db']:
            return None

        archive_path = os.path.join(
            os.path.dirname(self.db_path), 'sector_archive', '{}.db'.format(meta['archive_db']))
        if not os.path.exists(archive_path):
            return None

        try:
            with sqlite3.connect(archive_path, timeout=30) as arc_conn:
                arc_conn.row_factory = sqlite3.Row
                arc_cur = arc_conn.cursor()
                arc_cur.execute("""
                    SELECT iv_front_month FROM option_symbol_summary
                    WHERE symbol = ? AND trade_date < ?
                    AND iv_front_month IS NOT NULL AND iv_front_month > 0
                    ORDER BY trade_date DESC LIMIT 1
                """, (symbol, earnings_date))
                arc_row = arc_cur.fetchone()
                if arc_row and arc_row['iv_front_month']:
                    return arc_row['iv_front_month']
        except sqlite3.Error as e:
            logging.debug("Archive IV lookup failed for {} ({}): {}".format(
                symbol, archive_path, e))
        return None

    def _insert_earnings_move(self, cursor, moves_record):
        """Insert earnings move record

        Args:
            cursor: Database cursor
            moves_record: Move record dictionary with price moves, IV metrics,
                         peak analysis, expected moves, and swing data
        """
        # Clean with decimal formatter
        clean_record = clean_database_row(moves_record)

        insert_sql = """
        INSERT OR REPLACE INTO earnings_moves
        (event_id, symbol, earnings_date,
         pre_earnings_close,
         move_1day_pct, move_2day_pct, move_3day_pct, move_5day_pct,
         max_intraday_move_pct, move_direction,
         pre_earnings_peak_up_pct, pre_earnings_peak_down_pct,
         pre_earnings_peak_up_day, pre_earnings_peak_down_day,
         pre_earnings_swing_pct,
         post_earnings_peak_up_pct, post_earnings_peak_down_pct,
         post_earnings_peak_up_day, post_earnings_peak_down_day,
         post_earnings_swing_pct,
         total_swing_pct,
         iv_buildup_pct, iv_collapse_pct, iv_recovery_pct, iv_crush_severity,
         expected_move_pct, expected_move_entry_pct, expected_move_final_pct,
         move_vs_expected_pct,
         calculated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        try:
            cursor.execute(insert_sql, (
                clean_record['event_id'],
                clean_record['symbol'],
                clean_record.get('earnings_date'),
                clean_record.get('pre_earnings_close'),
                clean_record.get('move_1day_pct'),
                clean_record.get('move_2day_pct'),
                clean_record.get('move_3day_pct'),
                clean_record.get('move_5day_pct'),
                clean_record.get('max_intraday_move_pct'),
                clean_record.get('move_direction'),
                clean_record.get('pre_earnings_peak_up_pct'),
                clean_record.get('pre_earnings_peak_down_pct'),
                clean_record.get('pre_earnings_peak_up_day'),
                clean_record.get('pre_earnings_peak_down_day'),
                clean_record.get('pre_earnings_swing_pct'),
                clean_record.get('post_earnings_peak_up_pct'),
                clean_record.get('post_earnings_peak_down_pct'),
                clean_record.get('post_earnings_peak_up_day'),
                clean_record.get('post_earnings_peak_down_day'),
                clean_record.get('post_earnings_swing_pct'),
                clean_record.get('total_swing_pct'),
                clean_record.get('iv_buildup_pct'),
                clean_record.get('iv_collapse_pct'),
                clean_record.get('iv_recovery_pct'),
                clean_record.get('iv_crush_severity'),
                clean_record.get('expected_move_pct'),
                clean_record.get('expected_move_entry_pct'),
                clean_record.get('expected_move_final_pct'),
                clean_record.get('move_vs_expected_pct'),
                clean_record['calculated_at']
            ))

            logging.info("  {} Earnings move: {} (1d: {:+.2f}%, peak: {:+.2f}%, exp: {:.2f}%)".format(
                chr(10003),
                clean_record['symbol'],
                clean_record.get('move_1day_pct') or 0,
                clean_record.get('max_intraday_move_pct') or 0,
                clean_record.get('expected_move_pct') or 0))

        except sqlite3.Error as e:
            logging.error("Error inserting earnings move for {}: {}".format(
                moves_record['symbol'], e))
            raise

    def _update_event_outcome(self, cursor, event_id, moves_record):
        """Write denormalized outcome summary back to earnings_events.

        Provides at-a-glance historical view without JOINing earnings_moves.
        Computes three comparison metrics:
          - move_vs_straddle_pct: abs(actual_1day) / straddle * 100 (close-exit trade outcome)
          - move_vs_straddle_max_pct: abs(actual_max) / straddle * 100 (peak-exit outcome, SA P015)
          - move_vs_historical_pct: abs(actual_1day) / historical_avg * 100 (signal accuracy)

        Args:
            cursor: Database cursor
            event_id: Event ID in earnings_events
            moves_record: Computed moves record (same dict used for earnings_moves INSERT)
        """
        try:
            # Get signal inputs from earnings_events for comparison calcs
            cursor.execute("""
                SELECT straddle_expected_move_pct, historical_avg_move_pct
                FROM earnings_events WHERE event_id = ?
            """, (event_id,))
            event_row = cursor.fetchone()

            actual_abs = abs(moves_record['move_1day_pct']) if moves_record.get('move_1day_pct') is not None else None
            actual_max_abs = abs(moves_record['max_intraday_move_pct']) if moves_record.get('max_intraday_move_pct') is not None else None

            straddle_pct = event_row['straddle_expected_move_pct'] if event_row else None
            move_vs_straddle, straddle_outcome = compute_straddle_outcome(actual_abs, straddle_pct)
            move_vs_straddle_max, straddle_outcome_max = compute_straddle_outcome(actual_max_abs, straddle_pct)

            hist_pct = event_row['historical_avg_move_pct'] if event_row else None
            move_vs_historical, signal_accuracy = compute_move_vs_historical(actual_abs, hist_pct)

            cursor.execute("""
                UPDATE earnings_events
                SET actual_move_1day_pct = ?,
                    actual_max_move_pct = ?,
                    move_vs_expected_pct = ?,
                    iv_collapse_pct = ?,
                    move_vs_straddle_pct = ?,
                    move_vs_straddle_max_pct = ?,
                    move_vs_historical_pct = ?,
                    straddle_outcome = ?,
                    straddle_outcome_max = ?,
                    signal_accuracy = ?,
                    outcome_updated_at = ?
                WHERE event_id = ?
            """, (
                moves_record.get('move_1day_pct'),
                moves_record.get('max_intraday_move_pct'),
                moves_record.get('move_vs_expected_pct'),
                moves_record.get('iv_collapse_pct'),
                move_vs_straddle,
                move_vs_straddle_max,
                move_vs_historical,
                straddle_outcome,
                straddle_outcome_max,
                signal_accuracy,
                moves_record.get('calculated_at'),
                event_id
            ))
        except sqlite3.Error as e:
            logging.warning("Could not update earnings_events outcome for event {}: {}".format(
                event_id, e))

    def _calculate_sector_effects(self, cursor, primary_event_id, primary_symbol,
                                   earnings_date, primary_moves, primary_iv_data=None):
        """Calculate sector effects for peer symbols

        Args:
            cursor: Database cursor
            primary_event_id: Primary event ID
            primary_symbol: Primary symbol
            earnings_date: Earnings date
            primary_moves: Primary symbol's calculated price moves
            primary_iv_data: Primary symbol's IV metrics (for iv_buildup_pct)
        """
        # Get peer symbols with snapshots
        # Uses earnings_date (not event_id) — see _calculate_price_moves comment
        peer_query = """
        SELECT DISTINCT symbol
        FROM earnings_snapshots
        WHERE earnings_date = ? AND symbol != ? AND is_primary_symbol = FALSE
        """

        cursor.execute(peer_query, (earnings_date, primary_symbol))
        peer_symbols = [row['symbol'] for row in cursor.fetchall()]

        if not peer_symbols:
            logging.debug("No peer data for {}".format(primary_symbol))
            return

        # Get industry
        industry_query = """
        SELECT industry FROM industry_peer_mappings
        WHERE symbol = ? AND is_active = TRUE
        """

        cursor.execute(industry_query, (primary_symbol,))
        industry_row = cursor.fetchone()
        industry = industry_row['industry'] if industry_row else None

        # Calculate effects for each peer
        for peer_symbol in peer_symbols:
            try:
                effect_data = self._calculate_peer_effect(
                    cursor, primary_event_id, primary_symbol, peer_symbol,
                    earnings_date, primary_moves, industry, primary_iv_data
                )

                self._insert_sector_effect(cursor, effect_data)
                self.stats['sector_effects_calculated'] += 1

            except Exception as e:
                logging.error("Error calculating sector effect for peer {}: {}".format(
                    peer_symbol, e))

    def _calculate_peer_effect(self, cursor, primary_event_id, primary_symbol,
                               peer_symbol, earnings_date, primary_moves,
                               industry, primary_iv_data=None):
        """Calculate sector effect for a single peer

        Args:
            cursor: Database cursor
            primary_event_id: Primary event ID
            primary_symbol: Primary symbol
            peer_symbol: Peer symbol
            earnings_date: Earnings date (used for snapshot lookup)
            primary_moves: Primary symbol's price moves
            industry: Industry name
            primary_iv_data: Primary symbol's IV metrics (for iv_buildup_pct)

        Returns:
            dict: Sector effect data
        """
        # Get peer's price moves from snapshots
        # Uses earnings_date (not event_id) — see _calculate_price_moves comment
        peer_query = """
        SELECT days_from_earnings, close_price, iv_30dte
        FROM earnings_snapshots
        WHERE earnings_date = ? AND symbol = ?
        ORDER BY days_from_earnings
        """

        cursor.execute(peer_query, (earnings_date, peer_symbol))
        peer_snapshots = cursor.fetchall()

        if not peer_snapshots:
            return None

        # Build peer price/IV maps
        peer_price_map = {s['days_from_earnings']: s['close_price']
                         for s in peer_snapshots if s['close_price']}
        peer_iv_map = {s['days_from_earnings']: s['iv_30dte']
                      for s in peer_snapshots if s['iv_30dte']}

        # Calculate peer move (1-day)
        peer_move_pct = None
        if 0 in peer_price_map and 1 in peer_price_map:
            peer_move_pct = ((peer_price_map[1] - peer_price_map[0]) / peer_price_map[0]) * 100

        # Calculate peer IV changes
        peer_iv_buildup = None
        if -7 in peer_iv_map and -1 in peer_iv_map:
            peer_iv_buildup = ((peer_iv_map[-1] - peer_iv_map[-7]) / peer_iv_map[-7]) * 100

        # IV arbitrage delta (primary IV buildup - peer IV buildup)
        # BUG FIX (2026-02-10): Was reading from primary_moves (price data) instead of IV data
        iv_arbitrage_delta = None
        primary_iv_buildup = (primary_iv_data or {}).get('iv_buildup_pct')
        if primary_iv_buildup and peer_iv_buildup:
            iv_arbitrage_delta = primary_iv_buildup - peer_iv_buildup

        # Build effect record
        effect_data = {
            'primary_event_id': primary_event_id,
            'primary_symbol': primary_symbol,
            'peer_symbol': peer_symbol,
            'industry': industry,
            'primary_iv_buildup_pct': primary_iv_buildup,
            'peer_iv_buildup_pct': peer_iv_buildup,
            'iv_arbitrage_delta': iv_arbitrage_delta,
            'primary_move_pct': primary_moves.get('move_1day_pct'),
            'peer_move_pct': peer_move_pct,
            'calculated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        return effect_data

    def _insert_sector_effect(self, cursor, effect_data):
        """Insert sector effect record

        Args:
            cursor: Database cursor
            effect_data: Sector effect dictionary
        """
        if not effect_data:
            return

        # Clean with decimal formatter
        # Preserve string fields — clean_database_row nullifies fields containing
        # "symbol" in the name (known gotcha, see MEMORY.md). Set them after cleaning.
        primary_symbol = effect_data['primary_symbol']
        peer_symbol = effect_data['peer_symbol']
        industry = effect_data.get('industry')
        calculated_at = effect_data['calculated_at']
        clean_data = clean_database_row(effect_data)
        clean_data['primary_symbol'] = primary_symbol
        clean_data['peer_symbol'] = peer_symbol
        clean_data['industry'] = industry
        clean_data['calculated_at'] = calculated_at

        insert_sql = """
        INSERT OR REPLACE INTO earnings_sector_effects
        (primary_event_id, primary_symbol, peer_symbol, industry,
         primary_iv_buildup_pct, peer_iv_buildup_pct, iv_arbitrage_delta,
         primary_move_pct, peer_move_pct, calculated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        try:
            cursor.execute(insert_sql, (
                clean_data['primary_event_id'],
                clean_data['primary_symbol'],
                clean_data['peer_symbol'],
                clean_data.get('industry'),
                clean_data.get('primary_iv_buildup_pct'),
                clean_data.get('peer_iv_buildup_pct'),
                clean_data.get('iv_arbitrage_delta'),
                clean_data.get('primary_move_pct'),
                clean_data.get('peer_move_pct'),
                clean_data['calculated_at']
            ))

            logging.debug("    ✓ Sector effect: {} → {} (IV arb: {:+.2f}%)".format(
                clean_data['primary_symbol'],
                clean_data['peer_symbol'],
                clean_data.get('iv_arbitrage_delta') or 0))

        except sqlite3.Error as e:
            logging.error("Error inserting sector effect: {}".format(e))
            raise



def setup_logging(debug=False):
    """Set up logging configuration with UTF-8 encoding"""
    level = logging.DEBUG if debug else logging.INFO

    # Create logs directory
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, 'ei_post_earnings_calc.log')

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding='utf-8')
        ]
    )


def main():
    """Main function with CLI interface"""
    import argparse

    parser = argparse.ArgumentParser(description='Earnings Play: Post-Earnings Calculator')
    parser.add_argument('--trade-date', type=str,
                       help='Trade date to calculate for (YYYY-MM-DD, default: latest)')
    parser.add_argument('--recalculate', action='store_true',
                       help='Recalculate all events in window (ignore existing rows)')
    parser.add_argument('--backfill-outcomes', action='store_true',
                       help='Backfill earnings_events outcome columns from existing earnings_moves')
    parser.add_argument('--no-interaction', action='store_true',
                       help='Run without user prompts')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')

    args = parser.parse_args()

    # Reconfigure stdout for UTF-8 encoding (Windows)
    sys.stdout.reconfigure(encoding='utf-8')

    print("Earnings Play: Post-Earnings Calculator")
    if args.backfill_outcomes:
        print("Mode: BACKFILL earnings_events outcome columns")
    elif args.recalculate:
        print("Mode: RECALCULATE ALL (overwriting existing rows)")
    else:
        print("Calculating metrics for events at T+3")

    if not args.no_interaction:
        input("\nPress Enter to begin...")

    setup_logging(args.debug)

    try:
        # Initialize calculator
        calculator = PostEarningsCalculator()

        # Run backfill-outcomes mode
        if args.backfill_outcomes:
            updated = calculator.backfill_event_outcomes()
            print("Backfilled {} earnings_events with outcome data".format(updated))
            return 0

        # Run calculation
        if args.recalculate:
            results = calculator.recalculate_all(args.trade_date)
        else:
            results = calculator.calculate_post_earnings_metrics(args.trade_date)

        # Show results
        if results['errors'] > 0:
            print("✅ Calculation completed with {} errors".format(results['errors']))
            print("   Moves calculated: {}".format(results['moves_calculated']))
            print("   Sector effects: {}".format(results['sector_effects_calculated']))
            return 1
        else:
            print("✅ Calculation completed successfully!")
            print("   Trade date: {}".format(results['trade_date']))
            print("   Moves calculated: {}".format(results['moves_calculated']))
            print("   Sector effects: {}".format(results['sector_effects_calculated']))
            return 0

    except KeyboardInterrupt:
        print("\n⚠️ Calculation cancelled by user")
        return 130
    except Exception as e:
        print("\n❌ Calculation failed: {}".format(e))
        logging.error("Calculation error: {}".format(e))
        import traceback
        traceback.print_exc()

        # AUTOFIX INTEGRATION: Queue error even in standalone mode
        from tools.autofix import queue_error
        queue_error(
            error_type='earnings_calc_standalone_error',
            context={
                'error': str(e),
                'error_type': type(e).__name__,
                'traceback': traceback.format_exc(),
                'mode': 'standalone'
            },
            severity='ERROR'
        )

        return 1
    finally:
        if not args.no_interaction:
            input("\nPress Enter to exit...")


if __name__ == "__main__":
    sys.exit(main())
