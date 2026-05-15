#!/usr/bin/env python3
"""
Flow Monitor Baseline Generator (fm_baseline_generator.py)
---------------------------------------------------------
Calculates rolling option volume baselines from historical data.
Replaces stock volume baselines with option-specific statistics using robust median/MAD approach.

Key Features:
- Configurable rolling window for baseline calculations (default 21 days)
- Median of log1p(volume) instead of mean for robustness
- MAD (Median Absolute Deviation) * 1.4826 for standard deviation equivalent
- Separate vol/oi ratio statistics
- Bulk query approach: one scan of flow_daily_aggregates instead of per-symbol queries

Technical Notes:
- Uses log1p() transformation to handle zero volumes
- MAD multiplier 1.4826 makes it equivalent to standard deviation for normal distributions
- Groups by symbol and aggregates across all contracts daily

Reads: flow_daily_aggregates (pre-materialized per-symbol daily totals; P028)
Writes: symbol_baselines (INSERT OR REPLACE, batch)

Author: Ben (with assistance from Claude)
Date: 2025-06-27
"""

import os
import sys
import logging
import sqlite3
import statistics
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import math
from tools.timezone_utils import now_eastern, eastern_timestamp_string, eastern_isoformat, eastern_date_string
from tools.decimal_formatter import clean_database_row, format_ratio, format_score
from tools.log_utils import beautiful_log
from core.symbols_klmn800 import get_specialty_list

# MAG7 symbols for testing
MAG7_SYMBOLS = ['AAPL', 'AMZN', 'GOOGL', 'META', 'MSFT', 'NVDA', 'TSLA']


class OptionBaselineGenerator:
    """Generates option volume baselines using robust statistics"""

    def __init__(self, db_path=None):
        """Initialize baseline generator with database path"""
        if db_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            db_path = os.path.join(project_root, 'data', 'datalake.db')

        self.db_path = db_path
        self.mad_multiplier = 1.4826  # Makes MAD equivalent to std dev for normal distribution

        logging.debug("Option Baseline Generator initialized")
        logging.debug("Database: {}".format(self.db_path))

    def generate_baselines(self, symbols=None, lookback_days=7, test_mode=False):
        """Generate option volume baselines for specified symbols

        Uses a single bulk query to fetch all daily aggregates, then computes
        baselines in Python and batch-writes results. Reads from flow_daily_aggregates
        (pre-materialized once per cycle) — decoupled from raw flow_options_scans retention.

        Args:
            symbols: List of symbols to process from KLMN 800 list
            lookback_days: Number of days to look back for baseline calculation
            test_mode: If True, only process MAG7 symbols and show detailed output

        Returns:
            dict: Results summary with processed symbols and statistics
        """
        if symbols is None:
            symbols = MAG7_SYMBOLS if test_mode else get_specialty_list('fm_scan')

        if test_mode:
            logging.info("TEST MODE: Processing MAG7 symbols only")
            symbols = MAG7_SYMBOLS

        results = {
            'symbols_processed': 0,
            'baselines_created': 0,
            'baselines_updated': 0,
            'errors': [],
            'before_after_samples': []
        }

        # Calculate date range
        end_date = eastern_date_string()
        start_date = (now_eastern() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

        beautiful_log("Processing {} symbols | Window: {} to {}".format(
            len(symbols), start_date, end_date), 'info')

        # --- Phase 1: Bulk query all daily aggregates ---
        query_start = time.time()
        beautiful_log("Querying flow_daily_aggregates...", 'info')

        try:
            bulk_data = self._fetch_all_daily_aggregates(start_date, end_date)
        except Exception as e:
            logging.error("Bulk query failed: {}".format(e))
            results['errors'].append("Bulk query failed: {}".format(e))
            results['success'] = False
            return results

        query_elapsed = time.time() - query_start
        total_rows = sum(len(v) for v in bulk_data.values())
        beautiful_log("Query complete: {:,} daily aggregates for {} symbols in {:.0f}s".format(
            total_rows, len(bulk_data), query_elapsed), 'success')

        # --- Phase 2: Compute baselines per symbol ---
        compute_start = time.time()
        symbol_set = set(symbols)
        baselines = {}
        no_data_symbols = []

        # Get before-values for test mode comparison
        before_map = {}
        if test_mode:
            before_map = self._get_all_current_baselines()

        for symbol in symbols:
            try:
                daily_rows = bulk_data.get(symbol, [])
                baseline = self._compute_baseline(daily_rows)

                if baseline:
                    baselines[symbol] = baseline

                    if test_mode and symbol in before_map:
                        results['before_after_samples'].append({
                            'symbol': symbol,
                            'before': before_map.get(symbol),
                            'sample_size': baseline['sample_size']
                        })
                else:
                    no_data_symbols.append(symbol)

            except Exception as e:
                error_msg = "Failed to compute baseline for {}: {}".format(symbol, str(e))
                logging.error(error_msg)
                results['errors'].append(error_msg)

        compute_elapsed = time.time() - compute_start
        beautiful_log("Baselines computed: {} symbols in {:.1f}s | {} skipped (no data)".format(
            len(baselines), compute_elapsed, len(no_data_symbols)), 'info')

        # --- Phase 3: Batch write all baselines ---
        if baselines:
            write_start = time.time()
            try:
                created, updated = self._store_all_baselines(baselines)
                results['baselines_created'] = created
                results['baselines_updated'] = updated
                results['symbols_processed'] = created + updated
                write_elapsed = time.time() - write_start
                beautiful_log("Written: {} created, {} updated in {:.1f}s".format(
                    created, updated, write_elapsed), 'success')
            except Exception as e:
                logging.error("Batch write failed: {}".format(e))
                results['errors'].append("Batch write failed: {}".format(e))

            # Populate after-values for test mode
            if test_mode and results['before_after_samples']:
                after_map = self._get_all_current_baselines()
                for sample in results['before_after_samples']:
                    sample['after'] = after_map.get(sample['symbol'])

        # Report no-data symbols
        if no_data_symbols:
            preview = ', '.join(no_data_symbols[:10])
            suffix = " (+{} more)".format(len(no_data_symbols) - 10) if len(no_data_symbols) > 10 else ""
            beautiful_log("{} symbols had no scan data: {}{}".format(
                len(no_data_symbols), preview, suffix), 'warning')

        # Total timing
        total_elapsed = time.time() - query_start
        beautiful_log("Total baseline generation: {:.0f}s".format(total_elapsed), 'info')

        # Show results summary only in test/CLI mode (orchestrator owns completion display)
        if test_mode:
            self._show_results_summary(results, test_mode)

        results['success'] = results['symbols_processed'] > 0
        return results

    def _fetch_all_daily_aggregates(self, start_date, end_date):
        """Fetch daily volume/OI aggregates for all symbols in one bulk query.

        Returns:
            dict: {symbol: [(trade_date, daily_volume, daily_oi, contract_count), ...]}
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT symbol, trade_date, daily_volume, daily_oi, contract_count
                FROM flow_daily_aggregates
                WHERE trade_date >= ?
                    AND trade_date <= ?
                ORDER BY symbol, trade_date
            ''', (start_date, end_date))

            result = defaultdict(list)
            for symbol, trade_date, vol, oi, count in cursor.fetchall():
                result[symbol].append((trade_date, vol, oi, count))
            return dict(result)

    def _compute_baseline(self, daily_rows):
        """Compute baseline statistics from pre-fetched daily aggregate rows.

        Pure computation — no database access.

        Args:
            daily_rows: List of (trade_date, daily_volume, daily_oi, contract_count) tuples

        Returns:
            dict: Baseline statistics or None if insufficient data (< 3 days)
        """
        if len(daily_rows) < 3:
            return None

        daily_volumes = []
        vol_oi_ratios = []
        daily_totals = []

        for trade_date, daily_volume, daily_oi, contract_count in daily_rows:
            daily_totals.append(float(daily_volume))
            log_volume = math.log1p(float(daily_volume))
            daily_volumes.append(log_volume)

            if daily_oi > 0:
                vol_oi_ratio = format_ratio(float(daily_volume) / float(daily_oi))
                vol_oi_ratios.append(vol_oi_ratio)

        volume_median = statistics.median(daily_volumes)
        volume_mad = self._calculate_mad(daily_volumes) * self.mad_multiplier
        volume_total_daily = statistics.median(daily_totals)

        if vol_oi_ratios:
            vol_oi_median = statistics.median(vol_oi_ratios)
            vol_oi_mad = self._calculate_mad(vol_oi_ratios) * self.mad_multiplier
        else:
            vol_oi_median = 1.0
            vol_oi_mad = 0.3

        return {
            'volume_median': volume_median,
            'volume_mad': volume_mad,
            'volume_total_daily': volume_total_daily,
            'vol_oi_median': vol_oi_median,
            'vol_oi_mad': vol_oi_mad,
            'sample_size': len(daily_rows),
        }

    def _calculate_mad(self, values):
        """Calculate Median Absolute Deviation"""
        if not values:
            return 0.0
        median = statistics.median(values)
        absolute_deviations = [abs(x - median) for x in values]
        return statistics.median(absolute_deviations)

    def _get_all_current_baselines(self):
        """Get all current baseline values (for test mode before/after comparison).

        Returns:
            dict: {symbol: {volume_mean, volume_std, vol_oi_mean, vol_oi_std, sample_size}}
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT symbol, volume_mean, volume_std, vol_oi_mean, vol_oi_std, sample_size
                    FROM symbol_baselines
                ''')
                result = {}
                for row in cursor.fetchall():
                    result[row[0]] = {
                        'volume_mean': row[1],
                        'volume_std': row[2],
                        'vol_oi_mean': row[3],
                        'vol_oi_std': row[4],
                        'sample_size': row[5]
                    }
                return result
        except Exception as e:
            logging.error("Failed to get current baselines: {}".format(e))
            return {}

    def _store_all_baselines(self, baselines):
        """Batch write all baselines in a single connection and transaction.

        Args:
            baselines: dict of {symbol: baseline_data}

        Returns:
            tuple: (created_count, updated_count)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # One-time column migration check
            cursor.execute("PRAGMA table_info(symbol_baselines)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'volume_total_daily' not in columns:
                beautiful_log("Adding volume_total_daily column to symbol_baselines", 'info')
                cursor.execute('ALTER TABLE symbol_baselines ADD COLUMN volume_total_daily REAL')

            # Get existing symbols + created_at for tracking and preservation
            cursor.execute('SELECT symbol, created_at FROM symbol_baselines')
            existing = {row[0]: row[1] for row in cursor.fetchall()}

            created = 0
            updated = 0
            now = eastern_isoformat()

            for symbol, data in baselines.items():
                is_new = symbol not in existing
                if is_new:
                    created += 1
                    created_at = now
                else:
                    updated += 1
                    created_at = existing[symbol] or now

                cleaned = clean_database_row(data)

                cursor.execute('''
                    INSERT OR REPLACE INTO symbol_baselines
                    (symbol, volume_mean, volume_std, vol_oi_mean, vol_oi_std,
                     volume_total_daily, sample_size, last_updated, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol,
                    cleaned['volume_median'],
                    cleaned['volume_mad'],
                    cleaned['vol_oi_median'],
                    cleaned['vol_oi_mad'],
                    cleaned['volume_total_daily'],
                    cleaned['sample_size'],
                    now,
                    created_at,
                ))

            conn.commit()
            return created, updated

    def _show_results_summary(self, results, test_mode):
        """Display results summary (CLI/test mode only)"""
        logging.info("\n" + "="*60)
        logging.info("OPTION BASELINE GENERATION RESULTS")
        logging.info("="*60)
        logging.info("Symbols processed: {}".format(results['symbols_processed']))
        logging.info("New baselines created: {}".format(results['baselines_created']))
        logging.info("Existing baselines updated: {}".format(results['baselines_updated']))

        if results['errors']:
            logging.warning("Errors encountered: {}".format(len(results['errors'])))
            for error in results['errors'][:3]:
                logging.warning("  {}".format(error))

        # Show before/after comparison for test mode
        if test_mode and results['before_after_samples']:
            logging.info("\nBEFORE/AFTER COMPARISON (showing scale correction):")
            logging.info("-" * 60)

            for sample in results['before_after_samples'][:3]:
                symbol = sample['symbol']
                before = sample.get('before')
                after = sample.get('after')

                logging.info("Symbol: {}".format(symbol))
                if before and after:
                    before_vol_linear = math.expm1(before['volume_mean']) if before['volume_mean'] else 0
                    after_vol_linear = math.expm1(after['volume_mean']) if after['volume_mean'] else 0

                    logging.info("  BEFORE: Vol={:.0f} (std={:.2f}), Vol/OI={:.2f} (std={:.2f}), n={}".format(
                        before_vol_linear, before['volume_std'] or 0,
                        before['vol_oi_mean'] or 0, before['vol_oi_std'] or 0,
                        before['sample_size'] or 0))
                    logging.info("  AFTER:  Vol={:.0f} (mad={:.2f}), Vol/OI={:.2f} (mad={:.2f}), n={}".format(
                        after_vol_linear, after['volume_std'] or 0,
                        after['vol_oi_mean'] or 0, after['vol_oi_std'] or 0,
                        sample['sample_size']))

                    if before_vol_linear > 0 and after_vol_linear > 0:
                        scale_ratio = before_vol_linear / after_vol_linear
                        logging.info("  SCALE CORRECTION: {:.1f}x reduction (stock vs option volumes)".format(scale_ratio))
                else:
                    logging.info("  NEW BASELINE (no previous data)")
                logging.info("")


def materialize_daily_aggregate(db_path=None, trade_date=None):
    """Upsert today's flow_daily_aggregates row from flow_options_scans.

    Single bulk SQL — no per-symbol loop. Idempotent via ON CONFLICT DO UPDATE.
    Self-heals schema on fresh DB via embedded CREATE TABLE IF NOT EXISTS.
    Called once per post-market FM cycle by run_daily_aggregate_task.
    """
    if db_path is None:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        db_path = os.path.join(project_root, 'data', 'datalake.db')
    if trade_date is None:
        trade_date = eastern_date_string()

    schema_sql = """
        CREATE TABLE IF NOT EXISTS flow_daily_aggregates (
            symbol TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            daily_volume INTEGER NOT NULL,
            daily_oi INTEGER NOT NULL,
            contract_count INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (symbol, trade_date)
        );
        CREATE INDEX IF NOT EXISTS idx_fda_trade_date ON flow_daily_aggregates(trade_date);
    """

    upsert_sql = """
        INSERT INTO flow_daily_aggregates
            (symbol, trade_date, daily_volume, daily_oi, contract_count, updated_at)
        SELECT symbol, trade_date,
               COALESCE(SUM(volume), 0)        AS daily_volume,
               COALESCE(SUM(open_interest), 0) AS daily_oi,
               COUNT(*)                         AS contract_count,
               ?                                AS updated_at
        FROM flow_options_scans
        WHERE trade_date = ?
        GROUP BY symbol, trade_date
        HAVING daily_volume > 0
        ON CONFLICT(symbol, trade_date) DO UPDATE SET
            daily_volume   = excluded.daily_volume,
            daily_oi       = excluded.daily_oi,
            contract_count = excluded.contract_count,
            updated_at     = excluded.updated_at
    """

    with sqlite3.connect(db_path, timeout=30.0) as conn:
        conn.executescript(schema_sql)
        cursor = conn.cursor()
        cursor.execute(upsert_sql, (eastern_isoformat(), trade_date))
        rows_affected = cursor.rowcount
        conn.commit()

    logging.debug("flow_daily_aggregates: upserted {} rows for {}".format(rows_affected, trade_date))
    return rows_affected


def main():
    """Main function with CLI interface"""
    import argparse

    parser = argparse.ArgumentParser(description='Generate option volume baselines')
    parser.add_argument('--test', action='store_true',
                       help='Test mode: process MAG7 symbols only with detailed output')
    parser.add_argument('--symbols', nargs='+',
                       help='Specific symbols to process (space-separated)')
    parser.add_argument('--lookback', type=int, default=7,
                       help='Lookback window in days (default: 7)')
    parser.add_argument('--db-path',
                       help='Path to database file (optional)')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level')

    args = parser.parse_args()

    # Set up logging
    log_level = getattr(logging, args.log_level.upper())
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )

    try:
        generator = OptionBaselineGenerator(args.db_path)

        symbols = None
        if args.symbols:
            symbols = args.symbols

        results = generator.generate_baselines(
            symbols=symbols,
            lookback_days=args.lookback,
            test_mode=args.test
        )

        # Exit with appropriate code
        if results['errors']:
            logging.warning("Completed with {} errors".format(len(results['errors'])))
            return 1
        else:
            logging.info("Baseline generation completed successfully")
            return 0

    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        return 130
    except Exception as e:
        logging.error("Unexpected error: {}".format(e))
        return 1


if __name__ == '__main__':
    exit(main())
