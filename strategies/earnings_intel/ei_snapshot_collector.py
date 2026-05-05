#!/usr/bin/env python3
"""
Earnings Intelligence: Snapshot Collector (ei_snapshot_collector.py)
-------------------------------------------------------------------
Collect daily end-of-day snapshots for upcoming earnings events.

Captures OHLC, IV, OI, and volume for:
- Primary symbol (the one with earnings)
- Top 4 peer symbols in same industry

Window: 7 days before earnings through ~3 trading days after (T-7 to T+5 calendar)

Data alignment: Each morning, captures the PREVIOUS complete trading day's data.
On the morning of 4/2, we create a snapshot for 4/1 using 4/1's end-of-day data.
This ensures all fields (OHLC, IV, OI, volume) are from the same complete day.

Sources (both keyed on data_date):
- historical_prices: OHLC + stock volume
- option_symbol_summary: IV, OI, put_call_ratio, option volume

Part of: Earnings Intelligence System (PRD 0003)
Author: Ben (with Claude)
Date: 2025-10-10 (rewritten 2026-04: yesterday alignment, OHLC, dual-source window)
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

from decimal_formatter import clean_database_row
from log_utils import beautiful_log


class SnapshotCollector:
    """Collect end-of-day IV/price snapshots for earnings events"""

    def __init__(self, db_path=None):
        """Initialize collector

        Args:
            db_path: Path to database (default: data/datalake.db)
        """
        if not db_path:
            db_path = os.path.join(project_root, 'data', 'datalake.db')

        self.db_path = db_path

        # Statistics tracking
        self.stats = {
            'data_date': None,
            'events_in_window': 0,
            'events_processed': 0,
            'snapshots_created': 0,
            'snapshots_skipped': 0,
            'errors': 0
        }

        logging.debug("Snapshot collector initialized")

    def _ensure_schema(self, cursor):
        """Ensure earnings_snapshots table has the current schema.

        Migration history:
        - Oct 2025: Original schema with event_id NOT NULL FK (table stayed empty)
        - Feb 2026: Rewired to use earnings_upcoming, added earnings_date column
        - Apr 2026: Added OHLC (open/high/low) and option_volume for complete
                    end-of-day snapshots. Existing rows backfilled separately.
        - Apr 2026: Added straddle_expected_move_pct — captures the current
                    straddle-based expected move from earnings_upcoming at each
                    snapshot, creating a time series for entry vs final comparison.
        """
        cursor.execute("PRAGMA table_info(earnings_snapshots)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'earnings_date' not in columns:
            # Fresh install or pre-Feb-2026 schema — create from scratch
            logging.info("Creating earnings_snapshots table (fresh install)")
            cursor.execute("DROP TABLE IF EXISTS earnings_snapshots")
            cursor.execute("""
            CREATE TABLE earnings_snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                earnings_date DATE NOT NULL,
                event_id INTEGER,
                snapshot_date DATE NOT NULL,
                days_from_earnings INTEGER,
                snapshot_type TEXT,
                open_price REAL,
                high_price REAL,
                low_price REAL,
                close_price REAL,
                volume INTEGER,
                option_volume INTEGER,
                iv_30dte REAL,
                iv_front_month REAL,
                iv_45dte REAL,
                total_open_interest INTEGER,
                put_call_ratio REAL,
                is_primary_symbol BOOLEAN,
                straddle_expected_move_pct REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, earnings_date, snapshot_date)
            )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_symbol ON earnings_snapshots(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_date ON earnings_snapshots(symbol, snapshot_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_days_from ON earnings_snapshots(days_from_earnings)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_earnings_date ON earnings_snapshots(earnings_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_type ON earnings_snapshots(snapshot_type)")
            logging.info("Schema created — earnings_snapshots with OHLC + option_volume")
            return

        # Migration: Add OHLC + option_volume columns (Apr 2026)
        if 'open_price' not in columns:
            logging.info("Adding OHLC and option_volume columns to earnings_snapshots")
            for col, col_type in [('open_price', 'REAL'), ('high_price', 'REAL'),
                                   ('low_price', 'REAL'), ('option_volume', 'INTEGER')]:
                try:
                    cursor.execute("ALTER TABLE earnings_snapshots ADD COLUMN {} {}".format(col, col_type))
                except sqlite3.OperationalError as e:
                    if 'duplicate column' not in str(e).lower():
                        raise
            logging.info("Schema migration complete — OHLC + option_volume added")

        # Migration: Add straddle_expected_move_pct (Apr 2026)
        if 'straddle_expected_move_pct' not in columns:
            try:
                cursor.execute("ALTER TABLE earnings_snapshots ADD COLUMN straddle_expected_move_pct REAL")
                logging.info("Schema migration complete — straddle_expected_move_pct added")
            except sqlite3.OperationalError as e:
                if 'duplicate column' not in str(e).lower():
                    raise

    def collect_daily_snapshots(self, data_date=None):
        """Collect snapshots for the most recent complete trading day.

        Args:
            data_date: Date to capture data for (YYYY-MM-DD).
                      Default: previous complete trading day (yesterday).

        Returns:
            dict: Collection statistics
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                self._ensure_schema(cursor)
                conn.commit()

                if not data_date:
                    data_date = self._get_data_date(cursor)

                if not data_date:
                    logging.error("No data date available - option_symbol_summary may be empty")
                    self.stats['errors'] += 1
                    return self.stats

                self.stats['data_date'] = data_date
                logging.debug("Collecting snapshots for data date: {}".format(data_date))

                events_in_window = self._get_events_in_window(cursor, data_date)

                if not events_in_window:
                    logging.info("No earnings events in snapshot window")
                    return self.stats

                self.stats['events_in_window'] = len(events_in_window)
                beautiful_log("Found {} events in snapshot window".format(len(events_in_window)), 'info')

                for event in events_in_window:
                    self._collect_snapshots_for_event(cursor, event, data_date)

                conn.commit()

                return self.stats

        except Exception as e:
            logging.error("Snapshot collection failed: {}".format(e))
            import traceback
            traceback.print_exc()
            self.stats['errors'] += 1
            return self.stats

    def _get_data_date(self, cursor):
        """Get the most recent complete trading day for snapshot data.

        After morning OP (Phase 1.1), option_symbol_summary has today's
        pre-market row. We want the previous complete trading day so all
        fields (OHLC, IV, volume) reflect actual end-of-day values.

        Returns:
            str: Previous complete trading day (YYYY-MM-DD) or None
        """
        cursor.execute("""
            SELECT DISTINCT trade_date FROM option_symbol_summary
            ORDER BY trade_date DESC LIMIT 2
        """)
        rows = cursor.fetchall()

        if len(rows) >= 2:
            return rows[1]['trade_date']  # Second most recent = yesterday
        elif len(rows) == 1:
            return rows[0]['trade_date']  # Only one date available
        return None

    def _get_events_in_window(self, cursor, data_date):
        """Get earnings events in snapshot window around data_date.

        Queries both earnings_upcoming (pre-earnings + active) and
        earnings_events (post-earnings archive) to ensure post-earnings
        snapshots continue even after ei_collector updates the upcoming
        date to the next quarter.

        Args:
            cursor: Database cursor
            data_date: Date being captured (previous complete trading day)

        Returns:
            list: Events with symbol, earnings_date, days_from_earnings

        Sign convention for days_from_earnings (= data_date - earnings_date):
            -7 = data is from 7 days before earnings (T-7)
             0 = data is from earnings day
            +3 = data is from 3 days after earnings (T+3)
        """
        query = """
        SELECT symbol, earnings_date,
               CAST(JULIANDAY(?) - JULIANDAY(earnings_date) AS INTEGER) as days_from_earnings
        FROM (
            SELECT eu.symbol, eu.earnings_date
            FROM earnings_upcoming eu
            WHERE JULIANDAY(?) - JULIANDAY(eu.earnings_date) BETWEEN -7 AND 5

            UNION

            SELECT ee.symbol, ee.earnings_date
            FROM earnings_events ee
            WHERE JULIANDAY(?) - JULIANDAY(ee.earnings_date) BETWEEN 0 AND 5
        ) combined
        ORDER BY earnings_date, symbol
        """

        cursor.execute(query, (data_date, data_date, data_date))
        return cursor.fetchall()

    def _collect_snapshots_for_event(self, cursor, event, data_date):
        """Collect snapshots for an event (primary + top 4 peers)

        Args:
            cursor: Database cursor
            event: Event record (symbol, earnings_date, days_from_earnings)
            data_date: Date being captured
        """
        primary_symbol = event['symbol']
        earnings_date = event['earnings_date']
        days_from_earnings = event['days_from_earnings']

        logging.debug("Collecting snapshots for {} (earnings: {}, T{:+d})".format(
            primary_symbol, earnings_date, days_from_earnings))

        peer_symbols = self._get_peer_symbols(cursor, primary_symbol, limit=4)

        self._collect_symbol_snapshot(
            cursor, earnings_date, primary_symbol, data_date, days_from_earnings,
            is_primary=True
        )

        for peer_symbol in peer_symbols:
            self._collect_symbol_snapshot(
                cursor, earnings_date, peer_symbol, data_date, days_from_earnings,
                is_primary=False
            )

        self.stats['events_processed'] += 1

    def _get_peer_symbols(self, cursor, primary_symbol, limit=4):
        """Get top peer symbols for a primary symbol

        Args:
            cursor: Database cursor
            primary_symbol: Primary symbol
            limit: Number of peers to return (default: 4)

        Returns:
            list: Peer symbol names
        """
        cursor.execute("""
            SELECT industry FROM industry_peer_mappings
            WHERE symbol = ? AND is_active = TRUE
        """, (primary_symbol,))
        row = cursor.fetchone()

        if not row:
            logging.debug("No industry found for {}".format(primary_symbol))
            return []

        cursor.execute("""
            SELECT symbol FROM industry_peer_mappings
            WHERE industry = ? AND symbol != ? AND is_active = TRUE
            ORDER BY is_industry_leader DESC, symbol
            LIMIT ?
        """, (row['industry'], primary_symbol, limit))
        return [r['symbol'] for r in cursor.fetchall()]

    def _collect_symbol_snapshot(self, cursor, earnings_date, symbol, data_date,
                                  days_from_earnings, is_primary):
        """Collect end-of-day snapshot for a single symbol.

        Pulls from two sources, both keyed on data_date:
        - historical_prices: OHLC + stock volume
        - option_symbol_summary: IV, OI, put/call ratio, option volume

        Args:
            cursor: Database cursor
            earnings_date: The earnings date this snapshot relates to
            symbol: Symbol to collect for
            data_date: Date of the data (previous complete trading day)
            days_from_earnings: Days from earnings (negative = before, positive = after)
            is_primary: True if primary symbol, False if peer
        """
        # event_id lookup (Proposal 020 Part B). Pre-earnings snapshots leave this
        # NULL because the event hasn't been archived in earnings_events yet —
        # the one-time backfill SQL fills those once the event lands. Post-earnings
        # snapshots get the canonical join key written immediately.
        event_id = None
        if days_from_earnings >= 0:
            cursor.execute("""
                SELECT event_id FROM earnings_events
                WHERE symbol = ? AND ABS(JULIANDAY(earnings_date) - JULIANDAY(?)) <= 3
                ORDER BY ABS(JULIANDAY(earnings_date) - JULIANDAY(?)) ASC
                LIMIT 1
            """, (symbol, earnings_date, earnings_date))
            ev_row = cursor.fetchone()
            if ev_row:
                event_id = ev_row['event_id']

        # OHLC + stock volume from historical_prices
        cursor.execute("""
            SELECT open_price, high_price, low_price, close_price, volume
            FROM historical_prices
            WHERE symbol = ? AND trade_date = ?
        """, (symbol, data_date))
        hp_row = cursor.fetchone()

        # IV + OI + option volume from option_symbol_summary
        cursor.execute("""
            SELECT iv_30dte, iv_front_month, iv_45dte,
                   total_open_interest, put_call_ratio, option_volume
            FROM option_symbol_summary
            WHERE symbol = ? AND trade_date = ?
        """, (symbol, data_date))
        os_row = cursor.fetchone()

        # Straddle expected move from earnings_upcoming (primary symbols only)
        straddle_expected = None
        if is_primary:
            cursor.execute("""
                SELECT straddle_expected_move_pct
                FROM earnings_upcoming WHERE symbol = ?
            """, (symbol,))
            eu_row = cursor.fetchone()
            if eu_row:
                straddle_expected = eu_row['straddle_expected_move_pct']

        if not hp_row and not os_row:
            logging.debug("No data available for {} on {}".format(symbol, data_date))
            self.stats['snapshots_skipped'] += 1
            return

        # Determine snapshot type
        if days_from_earnings < 0:
            snapshot_type = 'pre_earnings'
        elif days_from_earnings == 0:
            snapshot_type = 'earnings_day'
        else:
            snapshot_type = 'post_earnings'

        snapshot_record = {
            'symbol': symbol,
            'earnings_date': earnings_date,
            'event_id': event_id,
            'snapshot_date': data_date,
            'days_from_earnings': days_from_earnings,
            'snapshot_type': snapshot_type,
            'open_price': hp_row['open_price'] if hp_row else None,
            'high_price': hp_row['high_price'] if hp_row else None,
            'low_price': hp_row['low_price'] if hp_row else None,
            'close_price': hp_row['close_price'] if hp_row else None,
            'volume': hp_row['volume'] if hp_row else None,
            'iv_30dte': os_row['iv_30dte'] if os_row else None,
            'iv_front_month': os_row['iv_front_month'] if os_row else None,
            'iv_45dte': os_row['iv_45dte'] if os_row else None,
            'total_open_interest': os_row['total_open_interest'] if os_row else None,
            'put_call_ratio': os_row['put_call_ratio'] if os_row else None,
            'option_volume': os_row['option_volume'] if os_row else None,
            'is_primary_symbol': is_primary,
            'straddle_expected_move_pct': straddle_expected,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        clean_snapshot = clean_database_row(snapshot_record)

        # INSERT OR REPLACE so corrected data can overwrite stale rows
        # (e.g. backfill overwriting old NULL-price snapshots)
        insert_sql = """
        INSERT OR REPLACE INTO earnings_snapshots
        (symbol, earnings_date, event_id, snapshot_date, days_from_earnings, snapshot_type,
         open_price, high_price, low_price, close_price, volume, option_volume,
         iv_30dte, iv_front_month, iv_45dte,
         total_open_interest, put_call_ratio,
         is_primary_symbol, straddle_expected_move_pct, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        try:
            cursor.execute(insert_sql, (
                clean_snapshot['symbol'],
                clean_snapshot['earnings_date'],
                clean_snapshot.get('event_id'),
                clean_snapshot['snapshot_date'],
                clean_snapshot['days_from_earnings'],
                clean_snapshot['snapshot_type'],
                clean_snapshot.get('open_price'),
                clean_snapshot.get('high_price'),
                clean_snapshot.get('low_price'),
                clean_snapshot.get('close_price'),
                clean_snapshot.get('volume'),
                clean_snapshot.get('option_volume'),
                clean_snapshot.get('iv_30dte'),
                clean_snapshot.get('iv_front_month'),
                clean_snapshot.get('iv_45dte'),
                clean_snapshot.get('total_open_interest'),
                clean_snapshot.get('put_call_ratio'),
                clean_snapshot['is_primary_symbol'],
                clean_snapshot.get('straddle_expected_move_pct'),
                clean_snapshot['created_at']
            ))

            self.stats['snapshots_created'] += 1
            logging.debug("  Snapshot: {} ({} T{:+d})".format(
                symbol, 'primary' if is_primary else 'peer', days_from_earnings))

        except sqlite3.Error as e:
            logging.error("Error inserting snapshot for {} on {}: {}".format(
                symbol, data_date, e))
            self.stats['errors'] += 1

    def backfill_existing_snapshots(self):
        """Backfill OHLC + volume data for existing snapshots with NULL prices.

        Updates rows from the pre-Apr-2026 collector that had NULL close_price
        because it queried historical_prices for 'today' at 7 AM (before market
        open). Fills from historical_prices (OHLC + stock volume) and
        option_symbol_summary (option_volume) keyed on snapshot_date.

        Returns:
            dict: {'updated': int, 'skipped': int, 'errors': int}
        """
        stats = {'updated': 0, 'skipped': 0, 'errors': 0}

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Ensure new columns exist
                self._ensure_schema(cursor)
                conn.commit()

                # Find snapshots missing price data
                cursor.execute("""
                    SELECT snapshot_id, symbol, snapshot_date
                    FROM earnings_snapshots
                    WHERE close_price IS NULL
                    ORDER BY snapshot_date
                """)
                rows = cursor.fetchall()

                if not rows:
                    logging.info("No snapshots need backfill — all have close_price")
                    return stats

                beautiful_log("Backfilling {} snapshots with NULL prices".format(len(rows)), 'info')

                for row in rows:
                    try:
                        sid = row['snapshot_id']
                        symbol = row['symbol']
                        snap_date = row['snapshot_date']

                        # Get OHLC + stock volume
                        cursor.execute("""
                            SELECT open_price, high_price, low_price, close_price, volume
                            FROM historical_prices
                            WHERE symbol = ? AND trade_date = ?
                        """, (symbol, snap_date))
                        hp = cursor.fetchone()

                        # Get option volume
                        cursor.execute("""
                            SELECT option_volume
                            FROM option_symbol_summary
                            WHERE symbol = ? AND trade_date = ?
                        """, (symbol, snap_date))
                        os = cursor.fetchone()

                        if not hp and not os:
                            stats['skipped'] += 1
                            continue

                        cursor.execute("""
                            UPDATE earnings_snapshots SET
                                open_price = ?,
                                high_price = ?,
                                low_price = ?,
                                close_price = ?,
                                volume = ?,
                                option_volume = ?
                            WHERE snapshot_id = ?
                        """, (
                            hp['open_price'] if hp else None,
                            hp['high_price'] if hp else None,
                            hp['low_price'] if hp else None,
                            hp['close_price'] if hp else None,
                            hp['volume'] if hp else None,
                            os['option_volume'] if os else None,
                            sid
                        ))
                        stats['updated'] += 1

                    except Exception as e:
                        logging.error("Backfill error for snapshot {}: {}".format(sid, e))
                        stats['errors'] += 1

                conn.commit()
                beautiful_log("Backfill complete: {} updated, {} skipped, {} errors".format(
                    stats['updated'], stats['skipped'], stats['errors']), 'info')

                return stats

        except Exception as e:
            logging.error("Backfill failed: {}".format(e))
            stats['errors'] += 1
            return stats


def setup_logging(debug=False):
    """Set up logging configuration with UTF-8 encoding"""
    level = logging.DEBUG if debug else logging.INFO

    # Create logs directory
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, 'ei_snapshot_collector.log')

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

    parser = argparse.ArgumentParser(description='Earnings Intelligence: Snapshot Collector')
    parser.add_argument('--data-date', type=str,
                       help='Date to capture data for (YYYY-MM-DD, default: previous trading day)')
    parser.add_argument('--backfill', action='store_true',
                       help='Backfill existing snapshots with NULL prices from historical_prices')
    parser.add_argument('--no-interaction', action='store_true',
                       help='Run without user prompts')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')

    args = parser.parse_args()

    # Reconfigure stdout for UTF-8 encoding (Windows)
    sys.stdout.reconfigure(encoding='utf-8')

    setup_logging(args.debug)

    if args.backfill:
        print("Earnings Intelligence: Snapshot Backfill")
        print("Filling NULL prices from historical_prices + option_symbol_summary")

        if not args.no_interaction:
            input("\nPress Enter to begin...")

        collector = SnapshotCollector()
        results = collector.backfill_existing_snapshots()
        print("\nBackfill results:")
        print("   Updated: {}".format(results['updated']))
        print("   Skipped: {}".format(results['skipped']))
        print("   Errors: {}".format(results['errors']))
        return 1 if results['errors'] > 0 else 0

    print("Earnings Intelligence: Snapshot Collector")
    print("Collecting end-of-day snapshots for earnings events (T-7 to T+5)")

    if not args.no_interaction:
        input("\nPress Enter to begin...")

    try:
        collector = SnapshotCollector()
        results = collector.collect_daily_snapshots(args.data_date)

        if results['errors'] > 0:
            print("Collection completed with {} errors".format(results['errors']))
            print("   Snapshots created: {}".format(results['snapshots_created']))
            print("   Events in window: {}".format(results['events_in_window']))
            return 1
        else:
            print("Collection completed successfully!")
            print("   Data date: {}".format(results['data_date']))
            print("   Snapshots created: {}".format(results['snapshots_created']))
            print("   Events in window: {}".format(results['events_in_window']))
            return 0

    except KeyboardInterrupt:
        print("\nCollection cancelled by user")
        return 130
    except Exception as e:
        print("\nCollection failed: {}".format(e))
        logging.error("Collection error: {}".format(e))
        import traceback
        traceback.print_exc()

        # AUTOFIX INTEGRATION: Queue error even in standalone mode
        from tools.autofix import queue_error
        queue_error(
            error_type='earnings_snapshot_standalone_error',
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
