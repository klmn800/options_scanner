"""
Reconstruct max_pain calculations for July 2025 using flow_options_scans data.

Uses the last scan of each day (most complete OI snapshot) to calculate max pain.
"""

import sqlite3
import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def calculate_max_pain(contracts):
    """
    Calculate max pain strike for a list of contracts.

    Args:
        contracts: List of tuples (strike, open_interest, option_type)

    Returns:
        float or None: Max pain strike price
    """
    if not contracts:
        return None

    # Get unique strikes to test
    strikes = sorted(set(float(c[0]) for c in contracts if c[0] is not None))

    if not strikes:
        return None

    min_pain = float('inf')
    max_pain_strike = None

    # Test each strike as potential closing price
    for test_strike in strikes:
        total_value = 0

        # Calculate intrinsic value of all options at this test price
        for strike, oi, option_type in contracts:
            if strike is None or oi is None:
                continue

            strike = float(strike)
            oi = int(oi) if oi else 0

            if oi == 0:
                continue

            if option_type.upper() == 'CALL':
                # Call intrinsic value = max(0, test_price - strike)
                intrinsic = max(0, test_strike - strike) * oi
            elif option_type.upper() == 'PUT':
                # Put intrinsic value = max(0, strike - test_price)
                intrinsic = max(0, strike - test_strike) * oi
            else:
                continue

            total_value += intrinsic

        # Find strike where total intrinsic value is minimized
        if total_value < min_pain:
            min_pain = total_value
            max_pain_strike = test_strike

    # Round to 2 decimal places
    if max_pain_strike is not None:
        return round(max_pain_strike, 2)
    return None


def reconstruct_max_pain(db_path, dates_to_process, dry_run=True):
    """
    Reconstruct max pain for specific dates using flow_options_scans.

    Args:
        db_path: Path to sector archive database
        dates_to_process: List of date strings (YYYY-MM-DD)
        dry_run: If True, only report what would be done
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    updates = []

    for trade_date in dates_to_process:
        logging.info(f"\nProcessing {trade_date}...")

        # Get all symbols for this date
        cursor.execute("""
            SELECT DISTINCT symbol
            FROM flow_options_scans
            WHERE trade_date = ?
            ORDER BY symbol
        """, (trade_date,))

        symbols = [row[0] for row in cursor.fetchall()]

        for symbol in symbols:
            # Get ALL scans for this date/symbol, then find last scan per contract in Python
            # This is much faster than correlated subquery on 877K rows
            cursor.execute("""
                SELECT strike, open_interest, option_type, expiration_date, scan_timestamp
                FROM flow_options_scans
                WHERE trade_date = ? AND symbol = ?
                  AND open_interest > 0
                  AND expiration_date >= ?
                ORDER BY strike, expiration_date, option_type, scan_timestamp DESC
            """, (trade_date, symbol, trade_date))

            all_scans = cursor.fetchall()

            # Keep only the last scan for each unique contract
            last_scans = {}
            for strike, oi, opt_type, exp_date, timestamp in all_scans:
                contract_key = (strike, exp_date, opt_type)
                if contract_key not in last_scans:
                    last_scans[contract_key] = (strike, oi, opt_type, exp_date)

            all_contracts = list(last_scans.values())

            if not all_contracts:
                logging.warning(f"  {symbol}: No contracts found")
                continue

            # Find nearest expiration
            expirations = sorted(set(c[3] for c in all_contracts if c[3]))

            if not expirations:
                logging.warning(f"  {symbol}: No valid expirations")
                continue

            nearest_expiry = expirations[0]

            # Filter to nearest expiration contracts
            expiry_contracts = [
                (c[0], c[1], c[2])
                for c in all_contracts
                if c[3] == nearest_expiry and c[1] > 0
            ]

            if not expiry_contracts:
                logging.warning(f"  {symbol}: No contracts at nearest expiry {nearest_expiry}")
                continue

            # Calculate max pain
            max_pain = calculate_max_pain(expiry_contracts)

            if max_pain is None:
                logging.warning(f"  {symbol}: Calculation failed")
                continue

            logging.info(f"  {symbol}: max_pain = ${max_pain} (expiry: {nearest_expiry}, {len(expiry_contracts)} contracts)")
            updates.append((max_pain, symbol, trade_date))

    # Summary
    logging.info(f"\n{'='*60}")
    logging.info(f"Summary:")
    logging.info(f"  Dates processed: {len(dates_to_process)}")
    logging.info(f"  Calculations completed: {len(updates)}")

    # Perform updates
    if updates:
        if dry_run:
            logging.info(f"\nDRY RUN - Would update {len(updates)} rows")
            logging.info("Run with --execute to apply changes")
        else:
            logging.info(f"\nUpdating {len(updates)} rows...")
            cursor.executemany("""
                UPDATE option_symbol_summary
                SET max_pain_by_friday = ?
                WHERE symbol = ? AND trade_date = ?
            """, updates)
            conn.commit()
            logging.info(f"Successfully updated {len(updates)} rows")

    conn.close()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Reconstruct July max pain from flow_options_scans')
    parser.add_argument('--db', required=True, help='Path to sector archive database')
    parser.add_argument('--execute', action='store_true', help='Actually perform updates (default is dry-run)')

    args = parser.parse_args()

    # Dates that need max_pain calculation
    # Including all weekdays for completeness and future intra-week analysis
    dates_to_process = [
        # Week 27 (July 7-11)
        '2025-07-07',  # Monday
        '2025-07-08',  # Tuesday
        '2025-07-09',  # Wednesday
        '2025-07-10',  # Thursday
        '2025-07-11',  # Friday
        # Week 28 (July 14-18)
        '2025-07-14',  # Monday
        '2025-07-15',  # Tuesday
        '2025-07-16',  # Wednesday
        '2025-07-17',  # Thursday (if exists)
        '2025-07-18',  # Friday
        # Week 29 (July 21-25)
        '2025-07-21',  # Monday
        '2025-07-22',  # Tuesday
        '2025-07-23',  # Wednesday
        '2025-07-24',  # Thursday
        '2025-07-25',  # Friday
        # Week 30 (July 28-Aug 1)
        '2025-07-28',  # Monday
        '2025-07-29',  # Tuesday
        '2025-07-30',  # Wednesday
        '2025-07-31',  # Thursday
        # (Friday 8/1 already has max_pain)
    ]

    reconstruct_max_pain(args.db, dates_to_process, dry_run=not args.execute)
