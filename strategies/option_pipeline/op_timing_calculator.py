#!/usr/bin/env python3
"""
OI Timing Calculator - Smart Money vs Retail Analysis

Calculates when Open Interest positioning was established and at what stock price.

Logic:
1. For each contract with significant OI (>1000)
2. Find when OI first exceeded 50% of current level (substantial positioning)
3. Get stock price on that date
4. Update option_contracts with oi_build_start_date and oi_build_start_price

Usage:
    python oid_timing_calculator.py --date 2025-10-02
    python oid_timing_calculator.py --backfill-days 30

Database Tables:
    Reads: option_contracts (time series), historical_prices (stock prices)
    Writes: option_contracts (updates oi_build_start_date, oi_build_start_price)
"""

import logging
import sqlite3
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from tools.timezone_utils import now_eastern, eastern_date_string
from tools.log_utils import beautiful_log

class OITimingCalculator:
    def __init__(self, db_path='data/datalake.db'):
        """Initialize calculator with database connection."""
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def calculate_timing_for_contract(self, contract_hash, symbol, trade_date):
        """
        Calculate OI timing for a single contract.

        Args:
            contract_hash: Unique contract identifier
            symbol: Stock symbol
            trade_date: Date to analyze (latest date for this contract)

        Returns:
            tuple: (oi_build_start_date, oi_build_start_price) or (None, None)
        """
        cursor = self.conn.cursor()

        # Get time series for this contract (all historical rows)
        cursor.execute("""
            SELECT trade_date, open_interest
            FROM option_contracts
            WHERE contract_hash = ?
            ORDER BY trade_date ASC
        """, (contract_hash,))

        rows = cursor.fetchall()

        if not rows or len(rows) < 2:
            return None, None

        # Current OI is the latest row (should match trade_date)
        current_oi = rows[-1]['open_interest']

        if current_oi <= 0:
            return None, None

        # Threshold: 50% of current OI (when positioning became substantial)
        threshold = current_oi * 0.50

        # Find first date when OI >= threshold
        oi_build_start_date = None
        for row in rows:
            if row['open_interest'] >= threshold:
                oi_build_start_date = row['trade_date']
                break

        if not oi_build_start_date:
            return None, None

        # Get stock price on that date
        cursor.execute("""
            SELECT close_price
            FROM historical_prices
            WHERE symbol = ? AND trade_date = ?
        """, (symbol, oi_build_start_date))

        price_result = cursor.fetchone()
        oi_build_start_price = price_result['close_price'] if price_result else None

        return oi_build_start_date, oi_build_start_price

    def process_date(self, trade_date):
        """
        Process all contracts for a given date.

        Args:
            trade_date: Date to process (YYYY-MM-DD)

        Returns:
            dict: Statistics about processing
        """
        cursor = self.conn.cursor()

        print("")
        beautiful_log("Processing {}".format(trade_date), 'info')

        # Get all contracts with significant OI on this date
        try:
            cursor.execute("""
                SELECT contract_hash, symbol, open_interest
                FROM option_contracts
                WHERE trade_date = ?
                AND open_interest > 1000
                ORDER BY symbol, open_interest DESC
            """, (trade_date,))

            contracts = cursor.fetchall()
        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "malformed" in error_msg or "corrupt" in error_msg:
                logging.critical("OI Timing: DATABASE CORRUPTION in option_contracts for {}: {}".format(trade_date, e))
                logging.critical("OI Timing: Run: python data/health/repair_option_contracts.py")
                return {'total': 0, 'updated': 0, 'skipped': 0}
            raise  # Re-raise non-corruption DatabaseErrors

        total_contracts = len(contracts)

        logging.info(f"Found {total_contracts} contracts with OI > 1000")

        processed = 0
        updated = 0
        skipped = 0

        for contract in contracts:
            contract_hash = contract['contract_hash']
            symbol = contract['symbol']

            # Calculate timing
            oi_build_start_date, oi_build_start_price = self.calculate_timing_for_contract(
                contract_hash, symbol, trade_date
            )

            processed += 1

            if oi_build_start_date and oi_build_start_price:
                # Update the option_contracts row
                cursor.execute("""
                    UPDATE option_contracts
                    SET
                        oi_build_start_date = ?,
                        oi_build_start_price = ?
                    WHERE contract_hash = ? AND trade_date = ?
                """, (oi_build_start_date, oi_build_start_price, contract_hash, trade_date))

                updated += 1
            else:
                skipped += 1

            # Progress indicator every 1000 contracts
            if processed % 1000 == 0:
                logging.info(f"  Progress: {processed}/{total_contracts} contracts ({updated} updated, {skipped} skipped)")

        # Commit changes
        self.conn.commit()

        beautiful_log("Completed {}: {} contracts updated, {} skipped".format(trade_date, updated, skipped), 'success')

        return {
            'total': total_contracts,
            'updated': updated,
            'skipped': skipped
        }

    def backfill_days(self, days=30):
        """
        Backfill OI timing for the last N days.

        Args:
            days: Number of days to backfill (default: 30)
        """
        cursor = self.conn.cursor()

        # Get list of dates to process
        cursor.execute("""
            SELECT DISTINCT trade_date
            FROM option_contracts
            WHERE trade_date >= date('now', ?)
            ORDER BY trade_date DESC
        """, (f'-{days} days',))

        dates = [row['trade_date'] for row in cursor.fetchall()]

        print(f"\nOI Timing Backfill - {days} days ({len(dates)} trading days)")

        total_stats = {'total': 0, 'updated': 0, 'skipped': 0}

        for date in dates:
            stats = self.process_date(date)
            total_stats['total'] += stats['total']
            total_stats['updated'] += stats['updated']
            total_stats['skipped'] += stats['skipped']

        print(f"\nTotal contracts processed: {total_stats['total']}")
        print(f"Successfully updated: {total_stats['updated']}")
        print(f"Skipped (insufficient data): {total_stats['skipped']}")
        if total_stats['total'] > 0:
            print(f"Success rate: {total_stats['updated']/total_stats['total']*100:.1f}%")

    def close(self):
        """Close database connection."""
        self.conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Calculate OI timing (smart money vs retail analysis)',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--date', help='Process specific date (YYYY-MM-DD)')
    parser.add_argument('--backfill-days', type=int, help='Backfill last N days (e.g., 30)')
    parser.add_argument('--db', default='data/datalake.db', help='Database path')

    args = parser.parse_args()

    if not args.date and not args.backfill_days:
        parser.error("Must specify either --date or --backfill-days")

    # Initialize calculator
    calc = OITimingCalculator(db_path=args.db)

    try:
        if args.backfill_days:
            calc.backfill_days(args.backfill_days)
        elif args.date:
            calc.process_date(args.date)
    finally:
        calc.close()


if __name__ == "__main__":
    main()
