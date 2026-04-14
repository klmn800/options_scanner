#!/usr/bin/env python3
"""
Tradier Historical Data Daily Update (tradier_historical_backfill.py)
-------------------------------------------------------------------
Daily historical price updates for KLMN 800 symbols using Tradier API.
Replaces deprecated FMP API implementation.

Features:
- Daily update mode (last 5 trading days to catch weekends)
- Individual symbol processing with proper rate limiting
- Calculates derived fields (change_amount, change_percent)
- Simple error handling and logging
- ~759 API calls at 120/min = ~6-7 minutes total

Author: Ben (migrated from FMP by Claude)
Date: 2025-11-17
"""

import sys
import sqlite3
import time
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def get_klmn_800_symbols():
    """Get KLMN 800 symbols"""
    try:
        from core.symbols_klmn800 import get_specialty_list
        return get_specialty_list('klmn_800')
    except ImportError:
        logging.error("Could not import KLMN 800 symbols")
        return []


def get_database_path():
    """Get path to datalake.db"""
    return Path(__file__).parent / 'datalake.db'


def fetch_historical_tradier(api_client, symbol, start_date, end_date):
    """Fetch historical data for single symbol using Tradier API

    Args:
        api_client: TradierAPI instance
        symbol: Stock ticker symbol
        start_date: Start date (YYYY-MM-DD format)
        end_date: End date (YYYY-MM-DD format)

    Returns:
        list: Historical data records, or empty list on error
    """
    try:
        response = api_client.get_historical_quotes(
            symbol,
            interval='daily',
            start_date=start_date,
            end_date=end_date
        )

        # Validate response structure
        if not response:
            logging.warning(f"Empty response for {symbol}")
            return []

        if not isinstance(response, dict):
            logging.warning(f"Non-dict response for {symbol}: type={type(response).__name__}, value={str(response)[:200]}")
            return []

        # Tradier response format: {"history": {"day": [...]}}
        if 'history' not in response:
            logging.warning(f"Missing 'history' key for {symbol}. Response keys: {list(response.keys())}, content: {str(response)[:200]}")
            return []

        history = response['history']

        if not history:
            logging.warning(f"Null/empty history for {symbol}")
            return []

        if not isinstance(history, dict):
            logging.warning(f"Non-dict history for {symbol}: type={type(history).__name__}, value={str(history)[:200]}")
            return []

        if 'day' not in history:
            logging.warning(f"Missing 'day' key for {symbol}. History keys: {list(history.keys())}, content: {str(history)[:200]}")
            return []

        day_data = history['day']

        # day can be either a list or a single dict
        if isinstance(day_data, list):
            return day_data
        elif isinstance(day_data, dict):
            return [day_data]
        else:
            logging.warning(f"Unexpected 'day' type for {symbol}: type={type(day_data).__name__}, value={str(day_data)[:200]}")
            return []

    except Exception as e:
        logging.warning(f"Exception for {symbol}: {type(e).__name__}: {e}")
        import traceback
        logging.debug(f"Traceback for {symbol}: {traceback.format_exc()}")
        return []


def calculate_change_fields(open_price, close_price):
    """Calculate change_amount and change_percent from OHLC data

    Args:
        open_price: Opening price
        close_price: Closing price

    Returns:
        tuple: (change_amount, change_percent)
    """
    if not open_price or open_price == 0:
        return 0, 0

    change_amount = close_price - open_price
    change_percent = (change_amount / open_price) * 100

    return round(change_amount, 2), round(change_percent, 2)


def process_and_store_data(symbol, historical_data, db_path):
    """Process and store historical data for symbol

    Args:
        symbol: Stock ticker symbol
        historical_data: List of daily price records from Tradier
        db_path: Path to SQLite database

    Returns:
        int: Number of records inserted
    """
    if not historical_data:
        return 0

    records_inserted = 0
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        with sqlite3.connect(db_path, timeout=30.0) as conn:
            cursor = conn.cursor()

            for day_data in historical_data:
                try:
                    # Validate required fields
                    if not day_data.get('date') or not day_data.get('close'):
                        continue

                    # Extract Tradier fields
                    trade_date = day_data.get('date')
                    open_price = float(day_data.get('open', 0))
                    high_price = float(day_data.get('high', 0))
                    low_price = float(day_data.get('low', 0))
                    close_price = float(day_data.get('close', 0))
                    volume = int(day_data.get('volume', 0))

                    # Calculate derived fields
                    change_amount, change_percent = calculate_change_fields(open_price, close_price)

                    # Tradier doesn't provide adjusted close or VWAP - set to NULL
                    adj_close_price = None  # Not available from Tradier
                    vwap = None  # Not available from Tradier

                    cursor.execute('''
                        INSERT OR REPLACE INTO historical_prices
                        (symbol, trade_date, open_price, high_price, low_price, close_price,
                         adj_close_price, volume, change_amount, change_percent, vwap, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        symbol,
                        trade_date,
                        open_price,
                        high_price,
                        low_price,
                        close_price,
                        adj_close_price,
                        volume,
                        change_amount,
                        change_percent,
                        vwap,
                        current_time
                    ))
                    records_inserted += 1

                except (ValueError, TypeError, sqlite3.Error) as e:
                    logging.debug(f"Database error for {symbol} on {day_data.get('date')}: {e}")
                    continue

            conn.commit()

    except Exception as e:
        logging.error(f"Error storing data for {symbol}: {e}")

    return records_inserted


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Tradier Historical Data Daily Update')
    parser.add_argument('--no-interaction', action='store_true',
                       help='Run without user prompts (for automation)')
    parser.add_argument('--days-back', type=int, default=5,
                       help='Days back to fetch (default: 5 to cover weekends)')
    parser.add_argument('--backfill-2021', action='store_true',
                       help='Backfill historical data from 2021-01-01 to present')
    parser.add_argument('--symbols', type=str,
                       help='Comma-separated list of specific symbols to backfill')

    args = parser.parse_args()

    # Setup logging
    log_file = Path(__file__).parent.parent / 'logs' / 'tradier_historical_daily.log'
    log_file.parent.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding='utf-8')
        ]
    )

    try:
        # Initialize Tradier API client
        try:
            import json
            from core.tradier_api import TradierAPI

            config_path = Path(__file__).parent.parent / 'config.json'
            with open(config_path, 'r') as f:
                config = json.load(f)

            if not config.get('tradier', {}).get('api_key'):
                logging.error("Tradier API key not found in config")
                return 1

            api_client = TradierAPI(config['tradier']['api_key'])
            logging.info("Tradier API client initialized")

        except Exception as e:
            logging.error(f"Failed to initialize Tradier API: {e}")
            # Queue autofix error for API initialization failure
            try:
                from tools.autofix import queue_error
                queue_error(
                    error_type='tradier_backfill_init_failed',
                    context={
                        'error_message': str(e),
                        'config_path': str(config_path)
                    },
                    severity='CRITICAL'
                )
            except:
                pass  # Don't let autofix error block the error return
            return 1

        # Get symbols to process
        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(',')]
            logging.info(f"Processing specific symbols: {symbols}")
        else:
            symbols = get_klmn_800_symbols()
            if not symbols:
                logging.error("Failed to load symbols")
                return 1

        # Calculate date range
        end_date = datetime.now().date()
        if args.backfill_2021:
            start_date = datetime(2021, 1, 1).date()
            logging.info("BACKFILL MODE: Fetching from 2021-01-01 to present")
        else:
            start_date = end_date - timedelta(days=args.days_back)

        logging.info(f"Updating historical data for {len(symbols)} symbols")
        logging.info(f"Date range: {start_date} to {end_date}")
        logging.info(f"Estimated time: ~{len(symbols) * 0.5 / 60:.1f} minutes")

        # Process symbols individually
        db_path = get_database_path()
        total_records = 0
        api_calls = 0
        failed_symbols = []
        successful_symbols = []  # Track symbols that got data
        start_time = time.time()

        for i, symbol in enumerate(symbols):

            # Progress logging every 50 symbols
            if i > 0 and i % 50 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                eta = (len(symbols) - i) / rate if rate > 0 else 0
                logging.info(f"Progress: {i}/{len(symbols)} symbols ({rate:.1f}/sec, ETA: {eta/60:.1f}min)")

            # Fetch data from Tradier
            historical_data = fetch_historical_tradier(
                api_client,
                symbol,
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d')
            )
            api_calls += 1

            # Process and store
            if historical_data:
                records = process_and_store_data(symbol, historical_data, db_path)
                total_records += records
                if records == 0:
                    logging.warning(f"Symbol {symbol}: API returned data but 0 records inserted (data validation failed)")
                    failed_symbols.append(symbol)
                else:
                    successful_symbols.append(symbol)
            else:
                logging.warning(f"Symbol {symbol}: No data returned from Tradier API")
                failed_symbols.append(symbol)

            # Rate limiting: 120/min = 0.5s per call
            time.sleep(0.5)

        elapsed_total = time.time() - start_time

        # Calculate success metrics
        success_count = len(successful_symbols)
        success_rate = success_count / len(symbols) if len(symbols) > 0 else 0

        logging.info("Historical update completed!")
        logging.info(f"Symbols with data: {success_count}/{len(symbols)} ({success_rate:.1%})")
        logging.info(f"Total records updated: {total_records}")
        logging.info(f"API calls made: {api_calls}")
        logging.info(f"Total time: {elapsed_total/60:.1f} minutes")

        # Data quality check: if we got 0 records from all symbols, something is wrong
        if api_calls > 0 and total_records == 0:
            logging.error("Data quality issue: 0 records inserted from all API calls")
            from tools.autofix import queue_error
            queue_error(
                error_type='tradier_backfill_no_data',
                context={
                    'symbols_attempted': len(symbols),
                    'api_calls_made': api_calls,
                    'date_range': f"{start_date} to {end_date}",
                    'failed_symbols_count': len(failed_symbols)
                },
                severity='ERROR'
            )

        # Report failures if any
        if failed_symbols:
            failure_rate = len(failed_symbols) / len(symbols)

            # Display prominent failure box (not buried in logs)
            print("\n" + "="*70)
            print("⚠️  HISTORICAL BACKFILL FAILURES")
            print("="*70)
            print(f"Failed: {len(failed_symbols)}/{len(symbols)} symbols ({failure_rate:.1%})")
            print(f"Success: {success_count}/{len(symbols)} symbols ({success_rate:.1%})")
            print(f"Symbols: {', '.join(failed_symbols)}")
            print("="*70 + "\n")

            logging.warning(f"Failed symbols: {len(failed_symbols)}/{len(symbols)} ({failure_rate:.1%})")
            logging.warning(f"Failed symbol list: {', '.join(failed_symbols)}")

            # Trigger autofix if failures exceed threshold (>15%)
            if failure_rate > 0.15:
                from tools.autofix import queue_error
                queue_error(
                    error_type='tradier_backfill_high_failure_rate',
                    context={
                        'failed_symbols': len(failed_symbols),
                        'total_symbols': len(symbols),
                        'failure_rate': round(failure_rate, 3),
                        'api_calls_made': api_calls,
                        'records_updated': total_records,
                        'failed_symbol_sample': failed_symbols[:20]
                    },
                    severity='ERROR'
                )
                logging.info("Queued error for batch mode review: high failure rate detected")
                return 1  # Catastrophic failure
            else:
                # Partial success - failures below 15% threshold
                return 2  # Exit code 2 = partial success with warnings

        # Only return 0 if ZERO failures
        return 0

    except Exception as e:
        logging.error(f"Historical update failed: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    exit(main())
