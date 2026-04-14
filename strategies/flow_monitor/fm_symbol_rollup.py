#!/usr/bin/env python3
"""
Flow Monitor Symbol Summary Rollup (fm_symbol_rollup.py)
-------------------------------------------------------
Populates flow_symbol_summary table with daily alert-focused metrics.
Selective processing: Only symbols with alert activity (alert_threshold_met = 1).

Features:
- Batch processing for memory efficiency
- Pre-computed rolling alert counts (5d, 20d)
- Idempotent operations (safe to re-run)
- Backfill support for historical dates

MIGRATION NOTE (2025-10-16):
- Renamed from options_symbol_summary → flow_symbol_summary
- Now processes ~50-100 alert symbols instead of all 800 symbols
- Stripped volume/OI/IV metrics (moved to option_symbol_summary)
- Added alert_count_5d and alert_count_20d pre-computation

Author: Ben (with assistance from Claude)
Date: 2025-10-16 (Major refactor for flow_symbol_summary)
"""

import os
import sys
import logging
import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path
from tools.timezone_utils import now_eastern, eastern_timestamp_string, eastern_isoformat, eastern_date_string
from tools.decimal_formatter import clean_database_row
from strategies.flow_monitor.fm_config import FMConfig, shutdown_event
from strategies.flow_monitor.fm_storage import FlowMonitorStorage


class SymbolSummaryBuilder:
    """Builds daily symbol summaries for alert-active symbols only"""

    def __init__(self, storage):
        self.storage = storage
        self.stats = {
            'symbols_processed': 0,
            'summaries_created': 0,
            'errors': 0
        }

    def populate_daily_summary(self, trade_date, symbols=None):
        """
        Main entry point for daily summary population

        Args:
            trade_date: Date string (YYYY-MM-DD)
            symbols: Optional list of symbols to process (default: alert-active symbols only)

        Returns:
            bool: Success status
        """
        start_time = time.time()
        logging.debug("Starting daily summary population for {}".format(trade_date))

        try:
            # Get symbols with alert activity on this date (SELECTIVE POPULATION)
            if symbols is None:
                active_symbols = self._get_alert_active_symbols(trade_date)
            else:
                active_symbols = symbols

            if not active_symbols:
                logging.warning("No alert-active symbols found for {}".format(trade_date))
                return True

            logging.debug("Processing {} alert-active symbols for {}".format(len(active_symbols), trade_date))

            # Process in batches of 50 for memory efficiency
            batch_size = 50
            total_summaries = []

            total_batches = (len(active_symbols) + batch_size - 1) // batch_size

            for i in range(0, len(active_symbols), batch_size):
                batch_symbols = active_symbols[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                batch_start = time.time()

                batch_summaries = []
                for symbol in batch_symbols:
                    try:
                        summary = self._calculate_summary(symbol, trade_date)
                        if summary:
                            batch_summaries.append(summary)
                            self.stats['summaries_created'] += 1
                        self.stats['symbols_processed'] += 1

                    except Exception as e:
                        logging.error("Failed to process symbol {}: {}".format(symbol, e))
                        self.stats['errors'] += 1
                        continue

                # Store batch
                if batch_summaries:
                    success = self._store_summaries(batch_summaries)
                    if success:
                        total_summaries.extend(batch_summaries)
                    else:
                        logging.error("Failed to store batch summaries")
                        return False

                batch_time = time.time() - batch_start
                logging.info("   Batch {}/{}: {} symbols -> {} summaries ({:.1f}s)".format(
                    batch_num, total_batches, len(batch_symbols), len(batch_summaries), batch_time))

            # Log completion stats
            total_time = time.time() - start_time
            self._log_completion_stats(trade_date, total_time)

            return True

        except Exception as e:
            logging.error("Daily summary population failed: {}".format(e))
            return False

    def _get_alert_active_symbols(self, trade_date):
        """
        Get symbols with active (non-expired) alerts

        SELECTIVE POPULATION: Only processes symbols with active alerts.
        This reduces processing from ~800 symbols to ~100-200 symbols per day.

        Changed from symbols with NEW alerts today to symbols with ANY active alerts.
        This ensures flow_symbol_summary stays current for discovery views - symbols
        with older but still-active alerts get daily rows with updated active_alert_count.

        CRITICAL: Queries flow_alerts table (not flow_options_scans) to capture
        ALL symbols that have active alerts, even if no new alerts generated today.
        """
        query = """
            SELECT DISTINCT symbol
            FROM flow_alerts
            WHERE expiration_date >= ?
              AND trade_date >= DATE(?, '-30 days')
            ORDER BY symbol
        """

        results = self.storage.query_with_params(query, (trade_date, trade_date))
        return [row['symbol'] for row in results]

    def _calculate_summary(self, symbol, trade_date):
        """
        Calculate focused alert summary for a symbol/date

        Args:
            symbol: Stock symbol
            trade_date: Date string

        Returns:
            dict: Summary data with 10 columns or None if no contracts
        """
        # Get contracts for final scan of the day
        contracts = self._get_final_scan_contracts(symbol, trade_date)
        if not contracts:
            logging.debug("No contracts found for {} on {}".format(symbol, trade_date))
            return None

        # Initialize summary
        summary = {
            'trade_date': trade_date,
            'symbol': symbol
        }

        # Calculate alert metrics (significance_score >= 3.5, v2 threshold since 2026-04)
        significant_contracts = [c for c in contracts if (c.get('significance_score') or 0) >= 3.5]

        summary.update({
            'significant_contract_count': len(significant_contracts),
            'max_significance_score': max(((c.get('significance_score') or 0) for c in contracts), default=0),
            'total_premium_tracked': sum((c.get('premium_value') or 0) for c in significant_contracts)
        })

        # Get alert counts from flow_alerts table
        alert_counts = self._get_alert_counts(symbol, trade_date)
        summary.update(alert_counts)

        # Calculate rolling alert time windows (5d, 20d)
        alert_time_windows = self._calculate_alert_time_windows(symbol, trade_date)
        summary.update(alert_time_windows)

        # Apply decimal formatting to all numeric values
        summary = clean_database_row(summary)

        return summary

    def _get_final_scan_contracts(self, symbol, trade_date):
        """Get contracts from the final scan of the trading day"""
        query = """
            SELECT
                symbol, strike, expiration_date, option_type,
                significance_score, premium_value
            FROM flow_options_scans
            WHERE symbol = ? AND trade_date = ?
                AND scan_timestamp = (
                    SELECT MAX(scan_timestamp)
                    FROM flow_options_scans
                    WHERE symbol = ? AND trade_date = ?
                )
        """

        return self.storage.query_with_params(query, (symbol, trade_date, symbol, trade_date))

    def _get_alert_counts(self, symbol, trade_date):
        """
        Get active and new alert counts for a symbol

        Args:
            symbol: Stock symbol
            trade_date: Current trade date

        Returns:
            dict: {'active_alert_count': int, 'new_alert_count': int, 'days_since_last_alert': int}
        """
        try:
            # Count active alerts (not expired)
            active_query = """
                SELECT COUNT(*) as count
                FROM flow_alerts
                WHERE symbol = ? AND expiration_date >= ?
            """
            active_result = self.storage.query_with_params(active_query, (symbol, trade_date))
            active_count = active_result[0]['count'] if active_result else 0

            # Count new alerts (created today)
            new_query = """
                SELECT COUNT(*) as count
                FROM flow_alerts
                WHERE symbol = ? AND trade_date = ?
            """
            new_result = self.storage.query_with_params(new_query, (symbol, trade_date))
            new_count = new_result[0]['count'] if new_result else 0

            # Get days since last alert
            last_alert_query = """
                SELECT MAX(trade_date) as last_alert_date
                FROM flow_alerts
                WHERE symbol = ? AND trade_date <= ?
            """
            last_alert_result = self.storage.query_with_params(last_alert_query, (symbol, trade_date))

            days_since_last_alert = None
            if last_alert_result and last_alert_result[0]['last_alert_date']:
                last_alert_date = last_alert_result[0]['last_alert_date']
                # Calculate days difference
                current_dt = datetime.strptime(trade_date, '%Y-%m-%d')
                last_alert_dt = datetime.strptime(last_alert_date, '%Y-%m-%d')
                days_since_last_alert = (current_dt - last_alert_dt).days

            return {
                'active_alert_count': active_count,
                'new_alert_count': new_count,
                'days_since_last_alert': days_since_last_alert
            }

        except Exception as e:
            logging.warning("Failed to get alert counts for {}: {}".format(symbol, e))
            return {
                'active_alert_count': 0,
                'new_alert_count': 0,
                'days_since_last_alert': None
            }

    def _calculate_alert_time_windows(self, symbol, trade_date):
        """
        Calculate pre-computed rolling alert counts

        Replaces expensive correlated subqueries in morning views with instant lookups.

        Args:
            symbol: Stock symbol
            trade_date: Current trade date

        Returns:
            dict: {'alert_count_5d': int, 'alert_count_20d': int}
        """
        try:
            # 5-day rolling alert count (last 5 days including current date)
            query_5d = """
                SELECT COUNT(*) as count
                FROM flow_alerts
                WHERE symbol = ?
                AND trade_date BETWEEN DATE(?, '-4 days') AND ?
            """
            result_5d = self.storage.query_with_params(query_5d, (symbol, trade_date, trade_date))
            alert_count_5d = result_5d[0]['count'] if result_5d else 0

            # 20-day rolling alert count (trend detection)
            query_20d = """
                SELECT COUNT(*) as count
                FROM flow_alerts
                WHERE symbol = ?
                AND trade_date BETWEEN DATE(?, '-19 days') AND ?
            """
            result_20d = self.storage.query_with_params(query_20d, (symbol, trade_date, trade_date))
            alert_count_20d = result_20d[0]['count'] if result_20d else 0

            return {
                'alert_count_5d': alert_count_5d,
                'alert_count_20d': alert_count_20d
            }

        except Exception as e:
            logging.warning("Failed to calculate alert time windows for {}: {}".format(symbol, e))
            return {
                'alert_count_5d': 0,
                'alert_count_20d': 0
            }

    def _store_summaries(self, summaries):
        """Store summaries in flow_symbol_summary table (10 columns)"""
        if not summaries:
            return True
        current_eastern_time = eastern_isoformat()

        # Use INSERT OR REPLACE to handle re-runs
        query = """
            INSERT OR REPLACE INTO flow_symbol_summary (
                trade_date, symbol,
                significant_contract_count, max_significance_score, total_premium_tracked,
                active_alert_count, new_alert_count, days_since_last_alert,
                alert_count_5d, alert_count_20d,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                     COALESCE((SELECT created_at FROM flow_symbol_summary
                              WHERE symbol=? AND trade_date=?), ?),
                     ?)
        """

        # Prepare batch parameters
        batch_params = []
        for summary in summaries:
            params = (
                summary['trade_date'],
                summary['symbol'],
                summary['significant_contract_count'],
                summary['max_significance_score'],
                summary['total_premium_tracked'],
                summary.get('active_alert_count', 0),
                summary.get('new_alert_count', 0),
                summary.get('days_since_last_alert'),
                summary.get('alert_count_5d', 0),
                summary.get('alert_count_20d', 0),
                summary['symbol'],  # For COALESCE lookup
                summary['trade_date'],  # For COALESCE lookup
                eastern_isoformat(),  # For created_at
                eastern_isoformat()   # For updated_at
            )
            batch_params.append(params)

        # Execute batch update
        success = self.storage.batch_update(query, batch_params)

        if success:
            logging.debug("Stored {} summaries successfully".format(len(summaries)))
        else:
            logging.error("Failed to store {} summaries".format(len(summaries)))

        return success

    def _log_completion_stats(self, trade_date, total_time):
        """Log completion statistics (debug-level; orchestrator owns the summary line)"""
        logging.debug("Flow symbol summary rollup: {}".format(trade_date))
        logging.debug("Symbols processed: {}".format(self.stats['symbols_processed']))
        logging.debug("Summaries created: {}".format(self.stats['summaries_created']))
        logging.debug("Errors encountered: {}".format(self.stats['errors']))
        logging.debug("Total processing time: {:.2f} seconds".format(total_time))

        if self.stats['symbols_processed'] > 0:
            avg_time = total_time / self.stats['symbols_processed']
            logging.debug("Average time per symbol: {:.3f} seconds".format(avg_time))

    def backfill_historical_summaries(self, start_date, end_date):
        """Backfill historical summaries for a date range"""
        logging.info("Starting backfill from {} to {}".format(start_date, end_date))

        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        current_dt = start_dt

        total_days = (end_dt - start_dt).days + 1
        processed_days = 0

        while current_dt <= end_dt:
            trade_date = current_dt.strftime('%Y-%m-%d')

            # Check if it's a trading day (simple check - has data)
            if self._is_trading_day(trade_date):
                logging.info("Backfilling {} ({}/{})".format(trade_date, processed_days + 1, total_days))
                success = self.populate_daily_summary(trade_date)

                if not success:
                    logging.error("Backfill failed for {}".format(trade_date))
                    return False

                processed_days += 1
            else:
                logging.debug("Skipping {} (no trading data)".format(trade_date))

            current_dt += timedelta(days=1)

        logging.info("Backfill complete: {} trading days processed".format(processed_days))
        return True

    def _is_trading_day(self, trade_date):
        """Check if date has any trading data"""
        query = "SELECT COUNT(*) as count FROM flow_options_scans WHERE trade_date = ?"
        result = self.storage.query_with_params(query, (trade_date,))
        return result[0]['count'] > 0 if result else False


def wait_for_enter():
    """Wait for user to press Enter before continuing"""
    input("\nPress Enter to continue...")


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Flow Monitor Symbol Summary Rollup")

    parser.add_argument('--date',
                        help='Specific date to process (YYYY-MM-DD)')
    parser.add_argument('--backfill', action='store_true',
                        help='Backfill historical summaries')
    parser.add_argument('--start-date',
                        help='Start date for backfill (YYYY-MM-DD)')
    parser.add_argument('--end-date',
                        help='End date for backfill (YYYY-MM-DD)')
    parser.add_argument('--symbols', nargs='+',
                        help='Specific symbols to process (default: alert-active only)')
    parser.add_argument('--test', action='store_true',
                        help='Test mode with limited symbols')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging')
    parser.add_argument('--no-interaction', action='store_true',
                        help='Skip interactive prompts')

    return parser.parse_args()


def setup_logging(debug=False):
    """Set up logging"""
    level = logging.DEBUG if debug else logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def main():
    """Main function"""
    print("Flow Monitor Symbol Summary Rollup")
    print("Populates flow_symbol_summary table with alert-focused metrics.")
    print("Selective processing: Only symbols with alert activity.")

    args = parse_arguments()

    if not args.no_interaction:
        wait_for_enter()

    try:
        # Parse arguments and setup
        setup_logging(args.debug)

        # Initialize components
        config = FMConfig()
        storage = FlowMonitorStorage(config)
        builder = SymbolSummaryBuilder(storage)

        # Determine operation mode
        if args.backfill:
            if not args.start_date or not args.end_date:
                logging.error("Backfill mode requires --start-date and --end-date")
                return 1

            success = builder.backfill_historical_summaries(args.start_date, args.end_date)

        elif args.date:
            symbols = args.symbols if not args.test else ['AAPL', 'TSLA', 'NVDA']  # Test symbols
            success = builder.populate_daily_summary(args.date, symbols)

        else:
            # Use current date
            current_date = eastern_date_string()
            symbols = args.symbols if not args.test else ['AAPL', 'TSLA', 'NVDA']  # Test symbols
            success = builder.populate_daily_summary(current_date, symbols)

        if success:
            print("\nFlow symbol summary rollup completed successfully!")
        else:
            print("\nFlow symbol summary rollup failed")
            return 1

    except KeyboardInterrupt:
        logging.warning("Operation cancelled by user")
        print("\nOperation cancelled by user. Exiting...")
        return 130
    except Exception as e:
        logging.error("Symbol summary rollup failed: {}".format(e))
        print("\nAn error occurred: {}".format(e))

        import traceback
        traceback.print_exc()

        return 1

    if not args.no_interaction:
        wait_for_enter()
    return 0


if __name__ == '__main__':
    exit(main())
