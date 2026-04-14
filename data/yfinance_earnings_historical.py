#!/usr/bin/env python3
"""
yfinance Earnings Data Collector (yfinance_earnings_historical.py)
----------------------------------------------------------------
Collects earnings data using Yahoo Finance via yfinance for the full KLMN 800 universe.
No API key required, completely free, bypasses FMP rate limits.

Features:
- Historical earnings dates and EPS data
- Batch processing with progress tracking
- Error handling and automatic retries
- Compatible with existing database schema
- Full KLMN 800 universe support

Usage:
    python yfinance_earnings_historical.py --all-klmn
    python yfinance_earnings_historical.py --missing-klmn
    python yfinance_earnings_historical.py --symbols "AAPL,MSFT,GOOGL"

Author: Claude
Date: 2025-09-27 (Updated 2025-09-28)
"""

import os
import sys
import sqlite3
import logging
import argparse
import time
import json
from datetime import datetime, timedelta
from pathlib import Path

# Add tools directory to path for decimal formatter
sys.path.append(str(Path(__file__).parent.parent / 'tools'))
from decimal_formatter import clean_database_row

# Add core directory to path for KLMN symbols
sys.path.append(str(Path(__file__).parent.parent / 'core'))
from symbols_klmn800 import KLMN_800_SYMBOLS

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("Error: yfinance and pandas required. Run: pip install yfinance pandas")
    sys.exit(1)

def get_database_path():
    """Get path to datalake.db"""
    return Path(__file__).parent / 'datalake.db'

def get_missing_klmn_symbols():
    """Get KLMN 800 symbols that are missing earnings data"""
    # Filter out symbols that already have earnings data
    db_path = get_database_path()
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT symbol FROM temp_earnings_raw')
            existing_symbols = set(row[0] for row in cursor.fetchall())
    except:
        existing_symbols = set()

    missing_symbols = [s for s in KLMN_800_SYMBOLS if s not in existing_symbols]
    return missing_symbols

def get_all_klmn_symbols():
    """Get all KLMN 800 symbols for full collection (no filtering)"""
    return KLMN_800_SYMBOLS

def fetch_earnings_data(symbol, max_retries=3):
    """Fetch earnings data from Yahoo Finance with retries"""
    for attempt in range(max_retries):
        try:
            logging.debug("Fetching {} earnings (attempt {}/{})".format(symbol, attempt + 1, max_retries))

            # Get earnings data using yfinance
            ticker = yf.Ticker(symbol)
            earnings_dates = ticker.earnings_dates

            if earnings_dates is None or earnings_dates.empty:
                logging.warning("No earnings data returned for {} from Yahoo Finance".format(symbol))
                return []

            # Convert to our database format
            records = []
            for date, row in earnings_dates.iterrows():
                # Only process actual earnings events, not meetings
                if pd.isna(row.get('Event Type')) or 'Earnings' not in str(row.get('Event Type')):
                    continue

                record = {
                    'symbol': symbol,
                    'earnings_date': date.strftime('%Y-%m-%d'),
                    'estimated_eps': row.get('EPS Estimate'),
                    'actual_eps': row.get('Reported EPS'),
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

                # Clean up None values
                for key, value in record.items():
                    if pd.isna(value):
                        record[key] = None

                records.append(record)

            logging.info("Successfully fetched {} earnings records for {}".format(len(records), symbol))
            return records

        except Exception as e:
            logging.warning("Attempt {}/{} failed for {}: {}".format(attempt + 1, max_retries, symbol, e))
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                logging.error("All attempts failed for {}: {}".format(symbol, e))
                return []

    return []

def store_earnings_data(symbol, records, db_path):
    """Store earnings data in database"""
    if not records:
        return 0

    records_stored = 0
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            for record in records:
                # Apply decimal formatting
                clean_record = clean_database_row(record)

                cursor.execute('''
                    INSERT OR REPLACE INTO temp_earnings_raw
                    (symbol, earnings_date, estimated_eps, actual_eps, created_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    clean_record['symbol'],
                    clean_record['earnings_date'],
                    clean_record['estimated_eps'],
                    clean_record['actual_eps'],
                    clean_record['created_at']
                ))
                records_stored += 1

            conn.commit()
            logging.info("Stored {} earnings records for {}".format(records_stored, symbol))

    except Exception as e:
        logging.error("Database error storing {}: {}".format(symbol, e))
        return 0

    return records_stored

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='yfinance Earnings Data Collector')
    parser.add_argument('--symbols', type=str,
                       help='Comma-separated list of symbols to process')
    parser.add_argument('--missing-priority', action='store_true',
                       help='Process the 92 priority symbols missing earnings data (DEPRECATED)')
    parser.add_argument('--missing-klmn', action='store_true',
                       help='Process KLMN 800 symbols missing earnings data')
    parser.add_argument('--all-klmn', action='store_true',
                       help='Process all KLMN 800 symbols (full collection)')
    parser.add_argument('--run-in-background', action='store_true',
                       help='Run in background mode')

    args = parser.parse_args()

    # Setup logging
    log_file = Path(__file__).parent.parent / 'logs' / 'yfinance_earnings.log'
    log_file.parent.mkdir(exist_ok=True)

    log_level = logging.INFO if not args.run_in_background else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file)
        ]
    )

    print("yfinance Earnings Data Collector")
    print("=" * 50)

    try:
        # Determine symbols to process
        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(',')]
            print("Processing specific symbols: {}".format(symbols))
        elif args.missing_klmn:
            symbols = get_missing_klmn_symbols()
            print("Processing {} missing KLMN 800 symbols".format(len(symbols)))
        elif args.all_klmn:
            symbols = get_all_klmn_symbols()
            print("Processing all {} KLMN 800 symbols (full collection)".format(len(symbols)))
        elif args.missing_priority:
            print("WARNING: --missing-priority is deprecated. Use --missing-klmn or --all-klmn instead.")
            symbols = get_missing_klmn_symbols()
            print("Processing {} missing KLMN 800 symbols".format(len(symbols)))
        else:
            print("Please specify --symbols, --missing-klmn, or --all-klmn")
            print("  --missing-klmn: Process only KLMN 800 symbols missing earnings data")
            print("  --all-klmn: Process all KLMN 800 symbols (full collection)")
            return 1

        if not symbols:
            print("No symbols to process!")
            return 0

        if not args.run_in_background:
            input("\nPress Enter to begin collection...")

        db_path = get_database_path()
        processed = 0
        failed = 0
        total_records = 0

        print("\nStarting earnings data collection...")

        for i, symbol in enumerate(symbols):
            print("\n[{}/{}] Processing {}...".format(i + 1, len(symbols), symbol))

            try:
                # Fetch data from Yahoo Finance
                records = fetch_earnings_data(symbol)

                if records:
                    # Store in database
                    stored = store_earnings_data(symbol, records, db_path)
                    if stored > 0:
                        print("   Stored {} earnings records".format(stored))
                        total_records += stored
                        processed += 1
                    else:
                        failed += 1
                else:
                    print("   No earnings data available")
                    failed += 1

                # Brief pause to be respectful to Yahoo Finance
                time.sleep(0.1)

                # Progress update every 25 symbols
                if (i + 1) % 25 == 0:
                    print("Progress: {}/{} symbols, {} processed, {} failed".format(
                        i + 1, len(symbols), processed, failed))

            except KeyboardInterrupt:
                print("\nCollection interrupted.")
                return 1

            except Exception as e:
                logging.error("Unexpected error processing {}: {}".format(symbol, e))
                failed += 1
                continue

        print("\nCollection completed!")
        print("Symbols processed: {}".format(processed))
        print("Symbols failed: {}".format(failed))
        print("Total earnings records collected: {}".format(total_records))

        return 0

    except Exception as e:
        print("\nCollection failed: {}".format(e))
        logging.error("Collection error: {}".format(e))
        return 1

if __name__ == "__main__":
    exit(main())