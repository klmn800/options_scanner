#!/usr/bin/env python3
"""
Airline Play - Options-Level Tracking
Filter and track option contracts for airline stocks (±10% strike range, ≤60 DTE).

Purpose: Populate airline_options_tracking table with filtered data from:
- option_contracts (all contract-level metrics)
- earnings_upcoming (earnings proximity)

Filtering Criteria:
- Strike within ±10% of current underlying price
- Days to expiration ≤ 60
- Recalculated daily as prices move (natural drift)

Author: Ben & Claude
Date: 2025-10-01
"""

import sqlite3
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import sys

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.symbols_klmn800 import get_specialty_list
from tools.decimal_formatter import clean_database_row
from tools.timezone_utils import now_eastern
from tools.autofix import queue_error

# Configure logging with UTF-8 encoding
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def get_database_path() -> Path:
    """Get path to datalake.db"""
    return PROJECT_ROOT / 'data' / 'datalake.db'


def get_connection() -> sqlite3.Connection:
    """Get database connection"""
    db_path = get_database_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn


def get_airline_symbols() -> List[str]:
    """Get list of airline symbols to track"""
    return get_specialty_list('airline_play')


def get_strike_range_pct(symbol: str) -> float:
    """
    Get strike range percentage for a symbol.

    Primary airlines (DAL, UAL, AAL): ±10% (more liquid, wider coverage)
    Secondary airlines (LUV, JBLU, ALK, JETS): ±5% (less liquid, tighter coverage)

    Returns:
        Strike range percentage (0.05 for ±5%, 0.10 for ±10%)
    """
    PRIMARY_AIRLINES = ['DAL', 'UAL', 'AAL']

    if symbol in PRIMARY_AIRLINES:
        return 0.10  # ±10% for primary airlines
    else:
        return 0.05  # ±5% for secondary airlines


def calculate_strike_range(underlying_price: float, range_pct: float = 0.10) -> Tuple[float, float]:
    """
    Calculate ±10% strike range from underlying price.

    Args:
        underlying_price: Current stock price
        range_pct: Percentage range (default 0.10 for ±10%)

    Returns:
        Tuple of (lower_strike, upper_strike)
    """
    lower_strike = underlying_price * (1 - range_pct)
    upper_strike = underlying_price * (1 + range_pct)
    return lower_strike, upper_strike


def get_current_underlying_price(conn: sqlite3.Connection, symbol: str, trade_date: str) -> Optional[float]:
    """
    Get current underlying price for strike range calculation.

    First tries option_contracts, falls back to historical_prices close_price.
    """
    cursor = conn.cursor()

    # Try option_contracts first
    cursor.execute("""
        SELECT underlying_price
        FROM option_contracts
        WHERE symbol = ? AND trade_date = ? AND underlying_price IS NOT NULL
        LIMIT 1
    """, (symbol, trade_date))

    row = cursor.fetchone()
    if row and row['underlying_price']:
        return float(row['underlying_price'])

    # Fallback to historical_prices
    cursor.execute("""
        SELECT close_price
        FROM historical_prices
        WHERE symbol = ? AND trade_date = ?
    """, (symbol, trade_date))

    row = cursor.fetchone()
    if row and row['close_price']:
        return float(row['close_price'])

    return None


def query_option_contracts_contracts(conn: sqlite3.Connection, symbol: str, trade_date: str,
                              lower_strike: float, upper_strike: float,
                              max_dte: int = 60) -> List[Dict[str, Any]]:
    """
    Query option_contracts for contracts matching filter criteria.

    Filters:
    - Symbol matches
    - Strike within range [lower_strike, upper_strike]
    - Days to expiration ≤ max_dte
    - Trade date matches

    Returns list of contract dictionaries with all option_contracts fields.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            contract_hash,
            symbol,
            strike,
            expiration_date,
            option_type,
            trade_date,
            underlying_price,
            COALESCE(dte, CAST(julianday(expiration_date) - julianday(trade_date) AS INTEGER)) as dte,
            moneyness,
            last_price,
            volume,
            volume_avg_5d,
            volume_avg_20d,
            volume_ratio_5d,
            volume_ratio_20d,
            volume_percentile_rank_20d,
            volume_change_1d,
            volume_change_5d,
            volume_ratio_5d_change_1d,
            open_interest,
            oi_change_1d,
            oi_change_5d,
            oi_change_10d,
            oi_change_pct_1d,
            oi_change_pct_5d,
            oi_change_pct_10d,
            oi_momentum_5d,
            delta,
            delta_change_1d,
            delta_change_5d,
            delta_momentum,
            delta_acceleration,
            gamma,
            gamma_change_1d,
            gamma_change_5d,
            gamma_momentum,
            theta,
            theta_change_1d,
            theta_change_5d,
            theta_momentum,
            theta_avg_5d,
            theta_daily_change_avg_5d,
            vega,
            vega_change_1d,
            vega_change_5d,
            iv,
            iv_change_1d,
            iv_change_5d,
            iv_change_20d,
            iv_change_pct_1d,
            iv_change_pct_5d,
            iv_change_pct_20d,
            iv_avg_5d,
            iv_avg_20d,
            iv_percentile_20day,
            iv_momentum_1d,
            iv_momentum_5d,
            created_at
        FROM option_contracts
        WHERE symbol = ?
        AND trade_date = ?
        AND strike BETWEEN ? AND ?
        AND CAST(julianday(expiration_date) - julianday(trade_date) AS INTEGER) <= ?
        ORDER BY expiration_date, strike
    """, (symbol, trade_date, lower_strike, upper_strike, max_dte))

    rows = cursor.fetchall()
    return [dict(row) for row in rows]


def calculate_earnings_proximity(conn: sqlite3.Connection, symbol: str, trade_date: str) -> Optional[int]:
    """
    Calculate days to next earnings from earnings_upcoming table.

    Returns: days_to_earnings (int) or None if no upcoming earnings
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            julianday(earnings_date) - julianday(?) as days_to_earnings
        FROM earnings_upcoming
        WHERE symbol = ?
        AND earnings_date >= ?
        ORDER BY earnings_date ASC
        LIMIT 1
    """, (trade_date, symbol, trade_date))

    row = cursor.fetchone()
    if row and row['days_to_earnings'] is not None:
        return int(row['days_to_earnings'])
    else:
        return None


def prepare_contract_row(contract_data: Dict[str, Any], days_to_earnings: Optional[int]) -> Dict[str, Any]:
    """
    Prepare contract row with earnings context and metadata.

    Args:
        contract_data: Raw contract data from option_contracts
        days_to_earnings: Days to next earnings

    Returns:
        Contract row ready for insertion
    """
    row = contract_data.copy()

    # Add earnings context
    row['days_to_earnings'] = days_to_earnings

    # Add metadata
    row['last_updated_timestamp'] = now_eastern().isoformat()

    return row


def batch_insert_contracts(conn: sqlite3.Connection, contracts: List[Dict[str, Any]]) -> int:
    """
    Batch insert/update contracts into airline_options_tracking table.

    Returns: Total number of rows affected
    """
    if not contracts:
        return 0

    total_rows = 0
    cursor = conn.cursor()

    for contract in contracts:
        # Apply decimal formatting
        cleaned = clean_database_row(contract)

        # Build column names and placeholders
        columns = list(cleaned.keys())
        placeholders = [f":{col}" for col in columns]

        # Build UPDATE clause (exclude primary keys)
        update_cols = [col for col in columns if col not in ('contract_hash', 'trade_date')]
        update_clause = ', '.join([f"{col} = excluded.{col}" for col in update_cols])

        sql = f"""
            INSERT INTO airline_options_tracking ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT(contract_hash, trade_date) DO UPDATE SET
                {update_clause},
                last_updated_timestamp = datetime('now')
        """

        cursor.execute(sql, cleaned)
        total_rows += cursor.rowcount

    return total_rows


def process_symbol(conn: sqlite3.Connection, symbol: str, trade_date: str) -> Dict[str, Any]:
    """
    Process a single symbol's options for the given trade date.

    Returns: Dict with symbol, contracts_tracked, success status
    """
    try:
        # Get current underlying price for strike range calculation
        underlying_price = get_current_underlying_price(conn, symbol, trade_date)

        if not underlying_price:
            logger.warning(f"   └─ {symbol}: No underlying price found for {trade_date}")
            return {
                'symbol': symbol,
                'contracts_tracked': 0,
                'success': False,
                'error': 'No underlying price'
            }

        # Calculate strike range (±10% for primary, ±5% for secondary)
        range_pct = get_strike_range_pct(symbol)
        lower_strike, upper_strike = calculate_strike_range(underlying_price, range_pct)

        logger.debug(f"   └─ {symbol}: Price=${underlying_price:.2f}, Range: ${lower_strike:.2f}-${upper_strike:.2f} (±{range_pct*100:.0f}%)")

        # Query contracts within range and ≤60 DTE
        contracts = query_option_contracts_contracts(conn, symbol, trade_date, lower_strike, upper_strike)

        if not contracts:
            logger.info(f"   └─ {symbol}: No contracts found in range")
            return {
                'symbol': symbol,
                'contracts_tracked': 0,
                'success': True,
                'error': None
            }

        # Get earnings proximity (same for all contracts of this symbol)
        days_to_earnings = calculate_earnings_proximity(conn, symbol, trade_date)

        # Prepare contracts with earnings context
        prepared_contracts = [prepare_contract_row(c, days_to_earnings) for c in contracts]

        # Batch insert
        rows_affected = batch_insert_contracts(conn, prepared_contracts)

        logger.info(f"   └─ {symbol}: {len(contracts)} contracts tracked ({rows_affected} rows)")

        return {
            'symbol': symbol,
            'contracts_tracked': len(contracts),
            'success': True,
            'error': None
        }

    except Exception as e:
        logger.error(f"Airline options tracking failed for {symbol}: {e}")
        queue_error(
            error_type='airline_options_tracking_failed',
            context={
                'symbol': symbol,
                'trade_date': trade_date,
                'error': str(e),
                'exception_type': type(e).__name__
            },
            severity='ERROR'
        )
        return {
            'symbol': symbol,
            'contracts_tracked': 0,
            'success': False,
            'error': str(e)
        }


def run_options_tracking(trade_date: Optional[str] = None, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Main function to run options-level tracking for airline stocks.

    Args:
        trade_date: Date to process (YYYY-MM-DD). Defaults to yesterday.
        symbols: List of symbols to process. Defaults to all airline symbols.

    Returns:
        Dict with summary statistics
    """
    # Default to yesterday if not specified
    if trade_date is None:
        yesterday = now_eastern().date() - timedelta(days=1)
        trade_date = yesterday.strftime('%Y-%m-%d')

    # Default to all airline symbols if not specified
    if symbols is None:
        symbols = get_airline_symbols()

    logger.info(f"✈️  AIRLINE OPTIONS: Starting contract filtering for {trade_date}")
    logger.info(f"   └─ Processing {len(symbols)} airline symbols")

    start_time = datetime.now()
    conn = get_connection()

    # Process each symbol
    results = []
    total_contracts = 0
    successful = 0
    failed = 0

    for symbol in symbols:
        result = process_symbol(conn, symbol, trade_date)
        results.append(result)

        if result['success']:
            successful += 1
            total_contracts += result['contracts_tracked']
        else:
            failed += 1

    # Commit all changes
    conn.commit()
    conn.close()

    elapsed = (datetime.now() - start_time).total_seconds()

    logger.info(f"✈️  AIRLINE OPTIONS: Complete - {successful} successful, {failed} failed, {total_contracts} contracts, {elapsed:.1f}s")

    return {
        'trade_date': trade_date,
        'symbols_processed': successful,
        'symbols_failed': failed,
        'total_contracts_tracked': total_contracts,
        'elapsed_seconds': elapsed,
        'results': results
    }


def main():
    """Command-line interface"""
    parser = argparse.ArgumentParser(description='Airline Play - Options-Level Tracking')
    parser.add_argument('--date', type=str, help='Trade date (YYYY-MM-DD). Defaults to yesterday.')
    parser.add_argument('--symbol', type=str, help='Single symbol to process (for testing)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')

    args = parser.parse_args()

    # Set debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Parse symbol list
    symbols = [args.symbol.upper()] if args.symbol else None

    # Run tracking
    result = run_options_tracking(trade_date=args.date, symbols=symbols)

    # Exit with appropriate code
    if result['symbols_failed'] > 0:
        sys.exit(1)  # Indicate some failures occurred
    else:
        sys.exit(0)  # All successful


if __name__ == '__main__':
    main()
