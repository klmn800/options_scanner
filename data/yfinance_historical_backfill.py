#!/usr/bin/env python3
"""
yfinance Historical Price Backfill (yfinance_historical_backfill.py)
------------------------------------------------------------------
Downloads 4 years of historical price data using Yahoo Finance via yfinance.
No API key required, completely free, bypasses FMP rate limits.

Features:
- 4 years of daily OHLC data (2021-2025)
- Batch processing with progress tracking
- Error handling and automatic retries
- Resume capability if interrupted
- Compatible with existing database schema

Usage:
    python yfinance_historical_backfill.py --symbols "AAPL,MSFT,GOOGL"
    python yfinance_historical_backfill.py --all-priority
    python yfinance_historical_backfill.py --resume

Author: Claude
Date: 2025-09-27
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

try:
    import yfinance as yf
except ImportError:
    print("Error: yfinance not installed. Run: pip install yfinance")
    sys.exit(1)

def get_database_path():
    """Get path to datalake.db"""
    return Path(__file__).parent / 'datalake.db'

def get_priority_symbols():
    """Get the 110 priority symbols list"""
    priority_symbols = [
        'CCL', 'JEF', 'MTN', 'LW', 'MKC', 'NKE', 'PAYX', 'CAG', 'STZ', 'FHN',
        'MS', 'PGR', 'PLD', 'PNC', 'PPG', 'REXR', 'SNV', 'SYF', 'BK', 'ELV',
        'IRDM', 'ISRG', 'KEY', 'MAN', 'MMC', 'MTB', 'PG', 'SNA', 'TRV', 'USB',
        'WAL', 'ALLY', 'AXP', 'CMA', 'FITB', 'HBAN', 'RF', 'SLB', 'TFC', 'AGNC',
        'CCK', 'WRB', 'ZION', 'ADC', 'AOS', 'BKR', 'DGX', 'DHR', 'ENPH', 'EWBC',
        'FCX', 'FI', 'GE', 'GM', 'GPC', 'HAL', 'KMB', 'KO', 'LMT', 'MCO',
        'NOC', 'NSC', 'PCAR', 'PHM', 'PKG', 'PM', 'RHI', 'RRC', 'SCCO', 'TXN',
        'VZ', 'AA', 'APH', 'BA', 'BPOP', 'BSX', 'CCI', 'CME', 'FAF', 'GEV',
        'GL', 'HLT', 'IBM', 'IPG', 'KMI', 'KNX', 'LII', 'LUV', 'LVS', 'MAT',
        'MOH', 'NEM', 'NTRS', 'ORLY', 'PEGA', 'QS', 'RJF', 'ROL', 'SLM', 'T',
        'TER', 'TMO', 'TRU', 'TSLA', 'VKTX', 'VLTO', 'AAL', 'ADT', 'BC', 'BX'
    ]
    return priority_symbols

def load_progress():
    """Load progress from JSON file"""
    progress_file = Path(__file__).parent / 'yfinance_progress.json'
    if progress_file.exists():
        try:
            with open(progress_file, 'r') as f:
                return json.load(f)
        except:
            pass

    return {
        'completed_symbols': [],
        'failed_symbols': [],
        'last_symbol': None,
        'total_records': 0,
        'start_time': None
    }

def save_progress(progress):
    """Save progress to JSON file"""
    progress_file = Path(__file__).parent / 'yfinance_progress.json'
    try:
        with open(progress_file, 'w') as f:
            json.dump(progress, f, indent=2)
    except Exception as e:
        logging.warning("Could not save progress: {}".format(e))

def fetch_historical_data(symbol, start_date, end_date, max_retries=3):
    """Fetch historical data from Yahoo Finance with retries"""
    for attempt in range(max_retries):
        try:
            logging.debug("Fetching {} data (attempt {}/{})".format(symbol, attempt + 1, max_retries))

            # Download data using yfinance
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)

            if hist.empty:
                logging.warning("No data returned for {} from Yahoo Finance".format(symbol))
                return []

            # Convert to our database format
            records = []
            for date, row in hist.iterrows():
                record = {
                    'symbol': symbol,
                    'trade_date': date.strftime('%Y-%m-%d'),
                    'open_price': row['Open'],
                    'high_price': row['High'],
                    'low_price': row['Low'],
                    'close_price': row['Close'],
                    'adj_close_price': row['Close'],  # Yahoo already provides adjusted close
                    'volume': int(row['Volume']) if not pd.isna(row['Volume']) else 0,
                    'change_amount': None,  # Calculate if needed
                    'change_percent': None,  # Calculate if needed
                    'vwap': None,  # Not available from Yahoo
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                records.append(record)

            logging.info("Successfully fetched {} records for {}".format(len(records), symbol))
            return records

        except Exception as e:
            logging.warning("Attempt {}/{} failed for {}: {}".format(attempt + 1, max_retries, symbol, e))
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                logging.error("All attempts failed for {}: {}".format(symbol, e))
                return []

    return []

def store_historical_data(symbol, records, db_path):
    """Store historical data in database"""
    if not records:
        return 0

    records_stored = 0
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # Delete existing data for this symbol first
            cursor.execute('DELETE FROM historical_prices WHERE symbol = ?', (symbol,))

            for record in records:
                # Apply decimal formatting
                clean_record = clean_database_row(record)

                cursor.execute('''
                    INSERT INTO historical_prices
                    (symbol, trade_date, open_price, high_price, low_price, close_price,
                     adj_close_price, volume, change_amount, change_percent, vwap, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    clean_record['symbol'],
                    clean_record['trade_date'],
                    clean_record['open_price'],
                    clean_record['high_price'],
                    clean_record['low_price'],
                    clean_record['close_price'],
                    clean_record['adj_close_price'],
                    clean_record['volume'],
                    clean_record['change_amount'],
                    clean_record['change_percent'],
                    clean_record['vwap'],
                    clean_record['created_at']
                ))
                records_stored += 1

            conn.commit()
            logging.info("Stored {} records for {}".format(records_stored, symbol))

    except Exception as e:
        logging.error("Database error storing {}: {}".format(symbol, e))
        return 0

    return records_stored

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='yfinance Historical Price Backfill')
    parser.add_argument('--symbols', type=str,
                       help='Comma-separated list of symbols to process')
    parser.add_argument('--all-priority', action='store_true',
                       help='Process all 110 priority symbols')
    parser.add_argument('--resume', action='store_true',
                       help='Resume interrupted collection')
    parser.add_argument('--start-date', type=str, default='2021-01-01',
                       help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default='2025-09-27',
                       help='End date (YYYY-MM-DD)')
    parser.add_argument('--run-in-background', action='store_true',
                       help='Run in background mode')

    args = parser.parse_args()

    # Setup logging
    log_file = Path(__file__).parent.parent / 'logs' / 'yfinance_historical.log'
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

    # Import pandas here after logging is set up
    try:
        import pandas as pd
        globals()['pd'] = pd
    except ImportError:
        logging.error("pandas not available - required for yfinance")
        return 1

    print("yfinance Historical Price Backfill")
    print("=" * 50)

    try:
        # Determine symbols to process
        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(',')]
            print("Processing specific symbols: {}".format(symbols))
        elif args.all_priority:
            symbols = get_priority_symbols()
            print("Processing all {} priority symbols".format(len(symbols)))
        else:
            print("Please specify --symbols or --all-priority")
            return 1

        # Load progress for resume
        progress = load_progress()
        if args.resume and progress['completed_symbols']:
            completed = set(progress['completed_symbols'])
            symbols = [s for s in symbols if s not in completed]
            print("Resuming: {} symbols remaining".format(len(symbols)))

        if not symbols:
            print("All symbols already completed!")
            return 0

        print("Date range: {} to {}".format(args.start_date, args.end_date))

        if not args.run_in_background:
            input("\nPress Enter to begin collection...")

        # Initialize progress
        if not args.resume:
            progress = {
                'completed_symbols': [],
                'failed_symbols': [],
                'last_symbol': None,
                'total_records': 0,
                'start_time': datetime.now().isoformat()
            }

        db_path = get_database_path()
        processed = 0
        failed = 0

        print("\nStarting historical data collection...")

        for i, symbol in enumerate(symbols):
            print("\n[{}/{}] Processing {}...".format(i + 1, len(symbols), symbol))

            try:
                # Fetch data from Yahoo Finance
                records = fetch_historical_data(symbol, args.start_date, args.end_date)

                if records:
                    # Store in database
                    stored = store_historical_data(symbol, records, db_path)
                    if stored > 0:
                        print("   Stored {} records".format(stored))
                        progress['completed_symbols'].append(symbol)
                        progress['total_records'] += stored
                        processed += 1
                    else:
                        progress['failed_symbols'].append(symbol)
                        failed += 1
                else:
                    print("   No data available")
                    progress['failed_symbols'].append(symbol)
                    failed += 1

                # Update progress
                progress['last_symbol'] = symbol
                save_progress(progress)

                # Brief pause to be respectful to Yahoo Finance
                time.sleep(0.1)

                # Progress update every 25 symbols
                if (i + 1) % 25 == 0:
                    print("Progress: {}/{} symbols, {} processed, {} failed".format(
                        i + 1, len(symbols), processed, failed))

            except KeyboardInterrupt:
                print("\nCollection interrupted. Use --resume to continue.")
                save_progress(progress)
                return 1

            except Exception as e:
                logging.error("Unexpected error processing {}: {}".format(symbol, e))
                progress['failed_symbols'].append(symbol)
                failed += 1
                continue

        print("\nCollection completed!")
        print("Symbols processed: {}".format(processed))
        print("Symbols failed: {}".format(failed))
        print("Total records collected: {}".format(progress['total_records']))

        # Clean up progress file
        progress_file = Path(__file__).parent / 'yfinance_progress.json'
        if progress_file.exists():
            progress_file.unlink()

        return 0

    except Exception as e:
        print("\nCollection failed: {}".format(e))
        logging.error("Collection error: {}".format(e))
        return 1

if __name__ == "__main__":
    exit(main())