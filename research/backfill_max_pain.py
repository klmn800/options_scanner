"""
Backfill max pain calculations for historical data in sector archives.

This script calculates max_pain_by_friday for any rows in option_symbol_summary
where it's currently NULL but we have option_contracts data available.
"""

import sqlite3
import sys
import logging
from decimal import Decimal

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
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
    strikes = sorted(set(float(c[0]) for c in contracts))

    if not strikes:
        return None

    min_pain = float('inf')
    max_pain_strike = None

    # Test each strike as potential closing price
    for test_strike in strikes:
        total_value = 0

        # Calculate intrinsic value of all options at this test price
        for strike, oi, option_type in contracts:
            strike = float(strike)
            oi = int(oi) if oi else 0

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


def backfill_max_pain(db_path, dry_run=True):
    """
    Backfill max pain for missing data.

    Args:
        db_path: Path to sector archive database
        dry_run: If True, only report what would be done
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Find all symbol/date combinations missing max_pain
    cursor.execute("""
        SELECT DISTINCT symbol, trade_date
        FROM option_symbol_summary
        WHERE max_pain_by_friday IS NULL
        ORDER BY trade_date, symbol
    """)

    missing = cursor.fetchall()
    logging.info(f"Found {len(missing)} rows with missing max_pain_by_friday")

    if not missing:
        logging.info("No missing data to backfill")
        conn.close()
        return

    updates = []
    skipped = []

    for symbol, trade_date in missing:
        # Get contracts for this symbol/date
        cursor.execute("""
            SELECT strike, open_interest, option_type, expiration_date
            FROM option_contracts
            WHERE symbol = ? AND trade_date = ?
              AND open_interest > 0
              AND expiration_date >= ?
        """, (symbol, trade_date, trade_date))

        all_contracts = cursor.fetchall()

        if not all_contracts:
            logging.debug(f"No contracts for {symbol} on {trade_date}")
            skipped.append((symbol, trade_date, "No contracts"))
            continue

        # Find nearest expiration
        expirations = sorted(set(c[3] for c in all_contracts if c[3]))

        if not expirations:
            logging.debug(f"No valid expirations for {symbol} on {trade_date}")
            skipped.append((symbol, trade_date, "No expirations"))
            continue

        nearest_expiry = expirations[0]

        # Filter to contracts for nearest expiration
        expiry_contracts = [
            (c[0], c[1], c[2])
            for c in all_contracts
            if c[3] == nearest_expiry and c[1] > 0
        ]

        if not expiry_contracts:
            logging.debug(f"No contracts at nearest expiry for {symbol} on {trade_date}")
            skipped.append((symbol, trade_date, "No contracts at expiry"))
            continue

        # Calculate max pain
        max_pain = calculate_max_pain(expiry_contracts)

        if max_pain is None:
            logging.debug(f"Could not calculate max pain for {symbol} on {trade_date}")
            skipped.append((symbol, trade_date, "Calculation failed"))
            continue

        logging.info(f"{symbol} {trade_date}: max_pain = ${max_pain} (expiry: {nearest_expiry}, {len(expiry_contracts)} contracts)")
        updates.append((max_pain, symbol, trade_date))

    # Summary
    logging.info(f"\nSummary:")
    logging.info(f"  Total missing: {len(missing)}")
    logging.info(f"  Can calculate: {len(updates)}")
    logging.info(f"  Cannot calculate: {len(skipped)}")

    if skipped:
        logging.info(f"\nSkipped reasons:")
        skip_reasons = {}
        for _, _, reason in skipped:
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
        for reason, count in skip_reasons.items():
            logging.info(f"  {reason}: {count}")

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

    parser = argparse.ArgumentParser(description='Backfill max pain calculations')
    parser.add_argument('--db', required=True, help='Path to sector archive database')
    parser.add_argument('--execute', action='store_true', help='Actually perform updates (default is dry-run)')

    args = parser.parse_args()

    backfill_max_pain(args.db, dry_run=not args.execute)
